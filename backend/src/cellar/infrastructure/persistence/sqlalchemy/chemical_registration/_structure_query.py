"""Structure-search SQL builders: exact, substructure, and similarity.

Owns the RDKit-cartridge SQL templates plus the algorithm/metric/threshold
resolution logic that drives the similarity path.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.sql import ColumnElement

from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from cellar.domain.sar_analysis.similarity_metric import Tanimoto, Tversky
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from cellar.infrastructure.rdkit.query_normalizer import aromatize_substructure_query

# Module-level singleton; tests can monkey-patch _default_registry if needed.
_default_registry = FingerprintRegistry.default()


def _structure_clause(criterion: dict[str, Any]) -> ColumnElement:
    # Accept new "kind" discriminator or legacy "search_type" alias.
    kind = criterion.get("kind") or criterion.get("search_type")

    if kind == "exact":
        inchi_key = criterion["inchi_key"]
        return MoleculeModel.inchi_key == inchi_key

    if kind == "substructure":
        return _substructure_clause(criterion)

    if kind == "similarity":
        return _similarity_clause(criterion)

    msg = f"Unknown structure kind: {kind!r}"
    raise ValueError(msg)


def _substructure_clause(criterion: dict[str, Any]) -> ColumnElement:
    query_text = criterion.get("smiles_or_smarts") or criterion.get("smarts")
    if not query_text:
        raise ValueError("substructure requires smiles_or_smarts (or legacy smarts)")
    generalized = bool(criterion.get("generalized", False))
    query_kind = criterion.get("query_kind")  # "smiles" | "smarts" | None

    # Cartridge functions qmol_from_smarts/mol_from_smiles take cstring, but
    # SQLAlchemy bindparams infer Python str -> VARCHAR. Explicit SQL CAST
    # to cstring is the only path that works under all driver scenarios.
    # The generalized (xqmol) path is structurally a SMILES path — the
    # cartridge's mol_to_xqmol works on a `mol`, not a `qmol`. Treat
    # untagged criteria with generalized=True as if they were tagged
    # SMILES (preserves the pre-query_kind contract for saved searches).
    effective_kind = query_kind
    if effective_kind is None and generalized:
        effective_kind = "smiles"

    if effective_kind == "smiles":
        # The cartridge would silently return zero rows for non-parseable
        # SMILES (atom-list or other SMARTS-only constructs); validate
        # Python-side so the chemist gets a clear 422 with the bad input.
        from rdkit.Chem import MolFromSmiles  # local import — keeps module light

        if MolFromSmiles(query_text) is None:
            raise ValueError(
                f"query_kind='smiles' but {query_text!r} is not a valid SMILES "
                "(atom lists / SMARTS primitives require query_kind='smarts')"
            )
        # Cartridge's mol_from_smiles handles aromaticity perception on
        # both sides, no Python-side normalization needed.
        bound_query = query_text
        if generalized:
            sql = "mol_from_smiles(smiles) @>> mol_to_xqmol(mol_from_smiles(CAST(:q AS cstring)))"
        else:
            sql = "mol_from_smiles(smiles) @> mol_from_smiles(CAST(:q AS cstring))"
    elif effective_kind == "smarts":
        # Trust the chemist's pattern literally. Atom lists, "any bond"
        # notation, and other SMARTS primitives would be silently
        # collapsed by an SMILES roundtrip.
        bound_query = query_text
        sql = "mol_from_smiles(smiles) @> qmol_from_smarts(CAST(:q AS cstring))"
    else:
        # Legacy untagged input (saved searches predating query_kind, or
        # third-party API callers) without generalized. Defensive
        # aromatization handles the dominant failure mode — Ketcher's
        # Kekulé SMARTS export [#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1 returning
        # zero hits against aromatic-perceived storage.
        bound_query = aromatize_substructure_query(query_text)
        sql = "mol_from_smiles(smiles) @> qmol_from_smarts(CAST(:q AS cstring))"
    return text(sql).bindparams(q=bound_query)


def _parse_metric(payload: dict[str, Any]) -> object:
    kind = payload.get("kind", "tanimoto")
    if kind == "tanimoto":
        return Tanimoto()
    if kind == "tversky":
        return Tversky(alpha=float(payload["alpha"]), beta=float(payload["beta"]))
    raise ValueError(f"Unknown metric kind: {kind!r}")


def _resolve_algorithm_and_metric(
    criterion: dict[str, Any],
) -> tuple[str, object, float]:
    """Resolve (algorithm_name, metric_obj, threshold) from a similarity criterion.

    Priority: explicit algorithm/metric/threshold override mode defaults.
    Mode shortcut resolves defaults; explicit fields always win.
    Legacy path (neither mode nor algorithm) falls back to morgan+tanimoto.
    """
    algorithm: str | None = criterion.get("algorithm")
    metric_payload: dict | None = criterion.get("metric")
    threshold: float | None = criterion.get("threshold")

    mode_value = criterion.get("mode")
    if mode_value is not None:
        mode = SearchMode(mode_value)
        defaults = MODE_DEFAULTS[mode]
        algorithm = algorithm or defaults.algorithm
        threshold = threshold if threshold is not None else defaults.threshold
        if metric_payload is None:
            metric = defaults.metric
        else:
            metric = _parse_metric(metric_payload)
    elif algorithm is not None:
        # Explicit algorithm — metric and threshold are required.
        if metric_payload is None:
            raise ValueError("similarity without mode requires explicit metric")
        if threshold is None:
            raise ValueError("similarity without mode requires explicit threshold")
        metric = _parse_metric(metric_payload)
    else:
        # Legacy fallback: no mode, no algorithm — use morgan/tanimoto defaults.
        algorithm = "morgan"
        metric = Tanimoto()
        threshold = threshold if threshold is not None else 0.7

    if not (0.0 <= float(threshold) <= 1.0):
        raise ValueError(f"threshold must be in [0,1], got {threshold}")

    return algorithm, metric, float(threshold)


def _compute_query_bytes(algorithm_name: str, smiles: str) -> bytes | None:
    """Compute Python-side fingerprint bytes for ``algorithm_name`` from ``smiles``.

    Returns bytes for ``"morgan"`` (the only algorithm whose stored column was
    written by Python, not the cartridge, so both sides must use the same format).
    Returns ``None`` for ``"fcfp"`` — the cartridge trigger uses
    ``featmorganbv_fp`` on both write and read sides, so bytes are compatible.

    Raises ``ValueError`` if ``smiles`` cannot be parsed.
    """
    if algorithm_name != "morgan":
        return None
    from rdkit.Chem import MolFromSmiles  # local import to keep module fast to import

    mol = MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Cannot parse SMILES for similarity query: {smiles!r}")
    return MorganAlgorithm().compute_bytes(mol)


def _scaffold_clause(criterion: dict[str, Any]) -> ColumnElement:
    """WHERE clause for {type: 'scaffold'} criteria.

    Supports two modes:
      - 'exact_match': molecules.bemis_murcko_smiles == canonical(input)
        Input is canonicalized via Bemis-Murcko computation so a paste of
        the full molecule normalizes to its scaffold (forgiving behavior).
      - 'acyclic_only': molecules.bemis_murcko_smiles == ''
        Matches the V2 'no scaffold' bucket (acyclic compounds; RDKit
        convention writes the empty string for these).

    Raises ValueError on unknown mode or unparseable scaffold_smiles.
    """
    from rdkit import Chem  # local import to keep module fast to import

    from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator

    mode = criterion.get("mode", "exact_match")

    if mode == "acyclic_only":
        return MoleculeModel.bemis_murcko_smiles == ""

    if mode == "exact_match":
        raw = criterion.get("scaffold_smiles")
        if not raw:
            msg = "scaffold criterion: 'exact_match' mode requires 'scaffold_smiles'"
            raise ValueError(msg)
        mol = Chem.MolFromSmiles(raw)
        if mol is None:
            msg = f"scaffold criterion: invalid SMILES {raw!r}"
            raise ValueError(msg)
        canonical = MurckoScaffoldCalculator().compute(mol)
        if canonical is None:
            msg = f"scaffold criterion: failed to compute scaffold for {raw!r}"
            raise ValueError(msg)
        if canonical == "":
            msg = (
                f"scaffold criterion: {raw!r} has no ring system — "
                "use mode='acyclic_only' to find acyclic compounds"
            )
            raise ValueError(msg)
        return MoleculeModel.bemis_murcko_smiles == canonical

    msg = f"scaffold criterion: unknown mode {mode!r} (allowed: exact_match, acyclic_only)"
    raise ValueError(msg)


def _similarity_clause(criterion: dict[str, Any]) -> ColumnElement:
    smiles = criterion["smiles"]
    algorithm_name, metric, threshold = _resolve_algorithm_and_metric(criterion)
    algo = _default_registry.get(algorithm_name)
    column = algo.column_name
    fn = algo.cartridge_query_fn
    radius_arg = ", 2" if fn == "featmorganbv_fp" else ""

    q_bytes = _compute_query_bytes(algorithm_name, smiles)

    if q_bytes is not None:
        # Morgan: Python-computed bytes must be passed via bfp_from_binary_text
        # so the query vector is in the same format as the stored morgan_bfp column.
        if isinstance(metric, Tanimoto):
            sql = f"{column} % bfp_from_binary_text(:sim_q_bytes)"
        elif isinstance(metric, Tversky):
            sql = (
                f"tversky_sml({column}, bfp_from_binary_text(:sim_q_bytes), "
                f"{metric.alpha}, {metric.beta}) >= {threshold}"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")
        return text(sql).bindparams(
            sa.bindparam("sim_q_bytes", value=q_bytes, type_=sa.LargeBinary)
        )
    else:
        # FCFP: cartridge function is consistent on both sides. mol_from_smiles
        # takes cstring; CAST(:sim_q AS cstring) handles the type coercion that
        # would otherwise fail under SQLAlchemy's String->VARCHAR inference.
        if isinstance(metric, Tanimoto):
            sql = f"{column} % {fn}(mol_from_smiles(CAST(:sim_q AS cstring)){radius_arg})"
        elif isinstance(metric, Tversky):
            sql = (
                f"tversky_sml({column}, "
                f"{fn}(mol_from_smiles(CAST(:sim_q AS cstring)){radius_arg}), "
                f"{metric.alpha}, {metric.beta}) >= {threshold}"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")
        return text(sql).bindparams(sim_q=smiles)
