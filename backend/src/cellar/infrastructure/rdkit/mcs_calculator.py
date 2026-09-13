"""Maximum common substructure via RDKit's ``rdFMCS``. Stateless."""

from __future__ import annotations

import structlog
from rdkit import Chem
from rdkit.Chem import rdFMCS

from cellar.domain.sar_analysis.mcs_types import McsResult

logger = structlog.get_logger(__name__)

#: Comparison settings for a *core*, not a generic substructure match.
#:
#: ``ringMatchesRingOnly`` + ``completeRingsOnly`` are what keep the answer
#: chemically meaningful: without them the MCS is free to match a ring atom to
#: a chain atom and to return a fragment of a ring, which no chemist would call
#: a shared core and which R-group decomposition cannot use. Elements and bond
#: orders match exactly. Fixed rather than exposed as request parameters until
#: a chemist asks for something else — every extra knob is another way for two
#: callers to get different answers from the same molecules.
_MATCH_KWARGS = {
    "ringMatchesRingOnly": True,
    "completeRingsOnly": True,
    "atomCompare": rdFMCS.AtomCompare.CompareElements,
    "bondCompare": rdFMCS.BondCompare.CompareOrder,
}

EMPTY_RESULT = McsResult(
    smarts="", core_smiles=None, num_atoms=0, num_bonds=0, timed_out=False, molecule_count=0
)


class RdkitMcsCalculator:
    """Compute the MCS of a set of SMILES.

    Unparseable SMILES are dropped (and counted out of ``molecule_count``)
    rather than failing the whole request — one bad row should not deny a
    chemist the answer for the other 22.
    """

    def compute(self, smiles: list[str], *, timeout_seconds: int) -> McsResult:
        mols: list[Chem.Mol] = []
        for smi in smiles:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                logger.warning("mcs_unparseable_smiles", smiles=smi)
                continue
            mols.append(mol)

        # One molecule is its own MCS; zero is nothing to answer about. Either
        # way FindMCS is not the right thing to ask.
        if len(mols) < 2:
            return McsResult(
                smarts="",
                core_smiles=Chem.MolToSmiles(mols[0]) if mols else None,
                num_atoms=mols[0].GetNumAtoms() if mols else 0,
                num_bonds=mols[0].GetNumBonds() if mols else 0,
                timed_out=False,
                molecule_count=len(mols),
            )

        result = rdFMCS.FindMCS(mols, timeout=timeout_seconds, **_MATCH_KWARGS)

        return McsResult(
            smarts=result.smartsString,
            core_smiles=_core_smiles(result.smartsString, mols),
            num_atoms=result.numAtoms,
            num_bonds=result.numBonds,
            # RDKit spells it `canceled`; the wire name says what it means to
            # the reader — the answer may be smaller than the true MCS.
            timed_out=bool(result.canceled),
            molecule_count=len(mols),
        )


def _core_smiles(smarts: str, mols: list[Chem.Mol]) -> str | None:
    """A plain SMILES for the matched substructure.

    Rendering the SMARTS query directly produces query syntax that
    ``MolFromSmiles`` cannot read back (``NC1:C(C(=O)O):C:N:...``), which is no
    use to depiction or to R-group decomposition. Writing the *matched atoms of
    a real molecule* instead gives a genuine, canonical SMILES.
    """
    if not smarts:
        return None
    query = Chem.MolFromSmarts(smarts)
    if query is None:
        return None
    for mol in mols:
        match = mol.GetSubstructMatch(query)
        if not match:
            continue
        try:
            fragment = Chem.MolFragmentToSmiles(mol, atomsToUse=list(match), canonical=True)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("mcs_core_smiles_failed", smarts=smarts, exc=str(exc))
            return None
        # Only hand back something a consumer can parse; a fragment written at
        # a ring cut can come back unreadable.
        return fragment if fragment and Chem.MolFromSmiles(fragment) is not None else None
    return None
