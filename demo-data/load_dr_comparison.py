"""Demo loader — two dose-response protocols on one target, one compound set.

Seeds a cross-protocol comparison demo: the same compounds run in two assay
formats against InhA, each producing a fitted dose-response curve, so the
search grid can show both curve columns side by side.

Compounds and the first protocol's potencies are real ChEMBL InhA inhibitor
data. The second protocol's potencies are simulated from them (see prep in
``data/dr_comparison.json``).

Usage:
    cd backend && uv run python ../demo-data/load_dr_comparison.py

Env:
    WORKSPACE_ID, ORG_ID, USER_ID, TARGET_ID  (all required)
    DR_DEMO_DATA  (optional path to the compound JSON)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import uuid
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from returns.result import Failure  # noqa: E402

from loaders._context import DemoAuthContext  # noqa: E402

WORKSPACE_ID = uuid.UUID(os.environ["WORKSPACE_ID"])
ORG_ID = uuid.UUID(os.environ["ORG_ID"])
USER_ID = uuid.UUID(os.environ["USER_ID"])
TARGET_ID = uuid.UUID(os.environ["TARGET_ID"])
DATA_FILE = Path(
    os.environ.get("DR_DEMO_DATA", REPO_ROOT / "demo-data" / "data" / "dr_comparison.json")
)

AUTH = DemoAuthContext(user_id=USER_ID, workspace_id=WORKSPACE_ID)

# 10-point, 3-fold dilution from 100 uM. Protocol dose_unit is uM.
DOSES = [100.0 / (3**i) for i in range(10)]
ROWS = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [
    "A" + chr(c) for c in range(ord("A"), ord("Z") + 1)
]

PROTOCOLS = [
    {
        "key": "enzyme",
        "discriminator": "NADH oxidation",
        "description": (
            "InhA inhibition measured spectrophotometrically as NADH consumption "
            "with DD-CoA substrate. Compound set and potencies from ChEMBL."
        ),
        "ic50_field": "enzyme_ic50_uM",
        "hill_field": "hill",
        "top_field": "top",
        "run_date": date(2026, 9, 18),
        "seed": 11,
    },
    {
        "key": "format2",
        "discriminator": "DD-CoA fluorescence",
        "description": (
            "Orthogonal InhA format: fluorescence readout on the same compound set, "
            "run to confirm the spectrophotometric potencies."
        ),
        "ic50_field": "format2_ic50_uM",
        "hill_field": "hill2",
        "top_field": "top2",
        "run_date": date(2026, 10, 9),
        "seed": 22,
    },
]


def readout_definitions() -> list[dict]:
    """% Inhibition (fitted) plus the IC50 dose-response readout."""
    return [
        {
            "name": "% Inhibition",
            "data_type": "numeric",
            "unit": "%",
            "precision": 1,
            "display_order": 1,
        },
        {
            "name": "IC50",
            "data_type": "dose_response",
            "unit": "µM",
            "display_order": 2,
            "dose_response_config": {
                "curve_type": "ic50",
                "y_readout_name": "% Inhibition",
                "intercepts": [{"kind": "ic", "basis": "relative_percent", "level": 50.0}],
            },
        },
    ]


def unwrap(result, what: str):
    if isinstance(result, Failure):
        raise RuntimeError(f"{what} failed: {result.failure()}")
    return result.unwrap()


async def register_molecules(container, compounds: list[dict]) -> dict[str, uuid.UUID]:
    from cellar.application.chemical_registration.register_molecule import (
        ExternalId,
        RegisterMolecule,
        RegisterMoleculeCommand,
    )

    ids: dict[str, uuid.UUID] = {}
    new = 0
    for c in compounds:
        uc = container[RegisterMolecule]
        result = await uc(
            RegisterMoleculeCommand(
                workspace_id=WORKSPACE_ID,
                name=c["chembl_id"],
                smiles=c["smiles"],
                originating_org_id=ORG_ID,
                registered_by=USER_ID,
                external_ids=[ExternalId(identifier=c["chembl_id"], identifier_type="chembl_id")],
            ),
            auth=None,
        )
        outcome = unwrap(result, f"register {c['chembl_id']}")
        ids[c["chembl_id"]] = outcome.molecule.id
        new += 1 if outcome.is_new else 0
    print(f"  molecules          {len(ids):>4d} ({new} new)")
    return ids


async def create_batches(container, compounds, mol_ids) -> dict[str, uuid.UUID]:
    from cellar.application.inventory.create_batch import CreateBatch, CreateBatchCommand
    from cellar.application.inventory.get_batch import (
        ListBatchesByMolecule,
        ListBatchesByMoleculeQuery,
    )

    batch_ids: dict[str, uuid.UUID] = {}
    new = 0
    for c in compounds:
        mol_id = mol_ids[c["chembl_id"]]
        existing = unwrap(
            await container[ListBatchesByMolecule](
                ListBatchesByMoleculeQuery(workspace_id=WORKSPACE_ID, molecule_id=mol_id),
                auth=AUTH,
            ),
            "list batches",
        )
        if existing:
            batch_ids[c["chembl_id"]] = existing[0].id
            continue
        created = unwrap(
            await container[CreateBatch](
                CreateBatchCommand(
                    workspace_id=WORKSPACE_ID,
                    molecule_id=mol_id,
                    source="purchased",
                    chemist=USER_ID,
                    amount_value=5.0,
                    amount_unit="mg",
                    purity=95.0,
                ),
                auth=AUTH,
            ),
            f"batch {c['chembl_id']}",
        )
        batch_ids[c["chembl_id"]] = created.batch.id
        new += 1
    print(f"  batches            {len(batch_ids):>4d} ({new} new)")
    return batch_ids


async def create_protocol(container, spec: dict) -> uuid.UUID:
    """Reuse the protocol for this format if a previous run already made it."""
    from cellar.application.screening.create_protocol import (
        CreateProtocol,
        CreateProtocolCommand,
    )
    from cellar.application.screening.get_protocol import ListProtocols, ListProtocolsQuery
    from cellar.application.screening.manage_protocol import (
        PublishProtocol,
        PublishProtocolCommand,
    )

    listing = unwrap(
        await container[ListProtocols](ListProtocolsQuery(workspace_id=WORKSPACE_ID), auth=AUTH),
        "list protocols",
    )
    suffix = f"[{spec['discriminator']}]"
    found = [getattr(p, "protocol", p) for p in listing.items]
    existing = next((p for p in found if p.name.endswith(suffix)), None)
    if existing is not None:
        print(f"  protocol           {existing.name!r} (existing)")
        return existing.id

    protocol = unwrap(
        await container[CreateProtocol](
            CreateProtocolCommand(
                workspace_id=WORKSPACE_ID,
                protocol_type="biochemical",
                category="Enzyme inhibition",
                target_ids=[TARGET_ID],
                discriminator=spec["discriminator"],
                description=spec["description"],
                dose_unit="uM",
                readout_definitions=readout_definitions(),
            ),
            auth=AUTH,
        ),
        f"protocol {spec['discriminator']}",
    )
    unwrap(
        await container[PublishProtocol](
            PublishProtocolCommand(workspace_id=WORKSPACE_ID, protocol_id=protocol.id),
            auth=AUTH,
        ),
        "publish",
    )
    print(f"  protocol           {protocol.name!r}")
    return protocol.id


async def create_run(container, protocol_id: uuid.UUID, spec: dict) -> tuple[uuid.UUID, bool]:
    """Return (run_id, has_wells). Reuses an existing run for this protocol."""
    from cellar.application.screening.create_run import CreateRun, CreateRunCommand
    from cellar.application.screening.get_run import (
        ListRunsByProtocol,
        ListRunsByProtocolQuery,
    )
    from cellar.application.screening.manage_run import (
        CompleteRun,
        CompleteRunCommand,
        StartRun,
        StartRunCommand,
    )

    runs = unwrap(
        await container[ListRunsByProtocol](
            ListRunsByProtocolQuery(workspace_id=WORKSPACE_ID, protocol_id=protocol_id), auth=AUTH
        ),
        "list runs",
    )
    if runs:
        run = runs[0]
        return run.id, bool(run.wells)

    run = unwrap(
        await container[CreateRun](
            CreateRunCommand(
                workspace_id=WORKSPACE_ID,
                protocol_id=protocol_id,
                run_date=spec["run_date"],
                performed_at_org_id=ORG_ID,
                plate_format="384",
                notes=f"ChEMBL InhA demo set — {spec['discriminator']}",
            ),
            auth=AUTH,
        ),
        "run",
    )
    unwrap(
        await container[StartRun](
            StartRunCommand(workspace_id=WORKSPACE_ID, run_id=run.id), auth=AUTH
        ),
        "start run",
    )
    unwrap(
        await container[CompleteRun](
            CompleteRunCommand(workspace_id=WORKSPACE_ID, run_id=run.id), auth=AUTH
        ),
        "complete run",
    )
    return run.id, False


async def set_up_plate(container, run_id: uuid.UUID, compounds, mol_ids) -> None:
    from cellar.application.screening.plate_setup import (
        CompoundAssignment,
        SetUpRunPlate,
        SetUpRunPlateCommand,
    )

    assignments = [
        CompoundAssignment(
            molecule_ref=c["chembl_id"],
            well_positions=[f"{ROWS[i]}{col}" for col in range(1, len(DOSES) + 1)],
        )
        for i, c in enumerate(compounds)
    ]
    info = unwrap(
        await container[SetUpRunPlate](
            SetUpRunPlateCommand(
                workspace_id=WORKSPACE_ID,
                run_id=run_id,
                compound_assignments=assignments,
                concentration_series=DOSES,
            ),
            auth=AUTH,
        ),
        "plate setup",
    )
    print(f"  wells              {info['wells_created']:>4d}")
    if info.get("unresolved"):
        raise RuntimeError(f"unresolved compounds: {info['unresolved'][:5]}")


async def load_readouts(container, run_id, protocol_id, compounds, spec) -> None:
    """Hill-curve %inhibition per well, then let the engine fit the curves."""
    from cellar.application.screening.bulk_create_readout_data import (
        BulkCreateReadoutData,
        BulkCreateReadoutDataCommand,
        ReadoutDataItem,
    )
    from cellar.application.screening.get_protocol import GetProtocol, GetProtocolQuery
    from cellar.application.screening.get_run import GetRun, GetRunQuery
    from cellar.application.screening.readout_calculation_engine import (
        ReadoutCalculationEngine,
    )

    found = unwrap(
        await container[GetProtocol](
            GetProtocolQuery(workspace_id=WORKSPACE_ID, protocol_id=protocol_id), auth=None
        ),
        "get protocol",
    )
    protocol = getattr(found, "protocol", found)
    pct_rd = next(rd for rd in protocol.readout_definitions if rd.name == "% Inhibition")

    got = unwrap(
        await container[GetRun](GetRunQuery(workspace_id=WORKSPACE_ID, run_id=run_id), auth=None),
        "get run",
    )
    run = getattr(got, "run", got)
    by_batch = {}
    for c in compounds:
        by_batch[c["_batch_id"]] = c

    rng = random.Random(spec["seed"])
    items = []
    for well in run.wells:
        c = by_batch.get(well.batch_id)
        if c is None or well.dose is None:
            continue
        ic50 = c[spec["ic50_field"]]
        hill = c[spec["hill_field"]]
        top = c[spec["top_field"]]
        inhibition = top / (1.0 + (ic50 / well.dose) ** hill)
        inhibition += rng.gauss(0, 3.0)
        items.append(
            ReadoutDataItem(
                run_id=run_id,
                well_id=well.id,
                molecule_id=c["_molecule_id"],
                batch_id=well.batch_id,
                readout_definition_id=pct_rd.id,
                value_numeric=round(max(-8.0, min(108.0, inhibition)), 2),
                value_qualifier="=",
            )
        )

    result = unwrap(
        await container[BulkCreateReadoutData](
            BulkCreateReadoutDataCommand(workspace_id=WORKSPACE_ID, items=items), auth=None
        ),
        "bulk readouts",
    )
    print(f"  readout rows       {result.success_count:>4d} ({result.error_count} errors)")

    outcome = unwrap(
        await container[ReadoutCalculationEngine].compute_for_run(
            run_id, workspace_id=WORKSPACE_ID
        ),
        "curve fitting",
    )
    print(
        f"  curves fitted      {len(outcome.computed_readouts):>4d} "
        f"({len(outcome.fit_warnings)} warnings)"
    )


async def main() -> int:
    from cellar.infrastructure.di.container import create_container

    compounds = json.loads(DATA_FILE.read_text())
    container = create_container()

    print(f"\n  Dose-response comparison demo — {len(compounds)} compounds")
    print(f"  workspace {WORKSPACE_ID}\n")

    mol_ids = await register_molecules(container, compounds)
    batch_ids = await create_batches(container, compounds, mol_ids)
    for c in compounds:
        c["_batch_id"] = batch_ids[c["chembl_id"]]
        c["_molecule_id"] = mol_ids[c["chembl_id"]]

    for spec in PROTOCOLS:
        print(f"\n  [{spec['discriminator']}]")
        protocol_id = await create_protocol(container, spec)
        run_id, has_wells = await create_run(container, protocol_id, spec)
        if has_wells:
            print("  wells              (existing)")
        else:
            await set_up_plate(container, run_id, compounds, mol_ids)
        await load_readouts(container, run_id, protocol_id, compounds, spec)

    print("\n  done\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
