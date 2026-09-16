"""Pins the two registries in ``scripts/replicate.py`` to reality.

Both lists fail SILENTLY when they drift. A job table that falls out of ``JOB_TABLES``
leaves rows spinning forever on every replicated machine; a status string that no longer
exists in its domain enum writes a value the app cannot render. Neither raises at export
time, and neither is visible until someone else has already imported the bundle.

So the drift fails here instead.
"""

from __future__ import annotations

import pytest
from replicate import JOB_TABLES, SCRATCH_PREFIXES, WORKFLOWS_DIR

from cellar.infrastructure.persistence.sqlalchemy.base import Base

# Imported purely for the Base.metadata side effect — every model module has to be
# loaded before metadata.tables is complete.
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration import (  # noqa: F401
    bulk_registration_models,
    cdd_molecule_import_models,
)
from cellar.infrastructure.persistence.sqlalchemy.export import export_job_model  # noqa: F401
from cellar.infrastructure.persistence.sqlalchemy.inventory import (  # noqa: F401
    cdd_plate_import_models,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis import (  # noqa: F401
    models as sar_models,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis import (  # noqa: F401
    rgroup_decomposition_models,
    sar_activity_projection_models,
    umap_job_model,
)


@pytest.mark.parametrize("job", JOB_TABLES, ids=lambda j: j.table)
def test_job_table_names_a_real_table_and_columns(job) -> None:
    """A renamed table or column must fail here, not on someone's replicated machine."""
    table = Base.metadata.tables.get(job.table)
    assert table is not None, f"{job.table} is not a mapped table"
    assert "status" in table.c, f"{job.table} has no status column"
    if job.error_col:
        assert job.error_col in table.c, f"{job.table} has no {job.error_col} column"


@pytest.mark.parametrize("job", JOB_TABLES, ids=lambda j: j.table)
def test_job_statuses_exist_in_the_domain_enum(job) -> None:
    """The sweep must never write a status the aggregate does not define.

    This is the guard that caught bulk_registrations: BulkRegistrationStatus has no
    'failed' member, so the obvious uniform sweep would have written a status nothing
    in the app knows how to read.
    """
    known = {member.value for member in job.status_enum}
    assert set(job.live) <= known, f"{job.table}: unknown live statuses {set(job.live) - known}"
    assert job.failed in known, f"{job.table}: {job.failed!r} not in {job.status_enum.__name__}"
    assert job.failed not in job.live, f"{job.table}: sweeping into a live status loops forever"


def test_every_temporal_workflow_has_a_sweep_entry() -> None:
    """Adding a ninth workflow must update JOB_TABLES, not just this list.

    Derived from the directory rather than restated as a literal, so a new workflow
    file trips it without anyone remembering to edit a set here.
    """
    workflows = {p.stem for p in WORKFLOWS_DIR.glob("*.py")} - {"__init__"}
    covered = {job.workflow for job in JOB_TABLES}
    assert covered == workflows, (
        f"workflows with no JOB_TABLES entry: {workflows - covered or '{}'}; "
        f"entries naming no workflow: {covered - workflows or '{}'}"
    )


def test_scratch_prefixes_are_named_and_justified() -> None:
    """The deny-list is the only thing standing between a dev and a 3.4 GB bundle.

    Export walks the WHOLE storage root, so an entry here is a deliberate omission —
    each one owes a reason that gets printed to whoever imports the bundle.
    """
    assert {p.name for p in SCRATCH_PREFIXES} == {"cdd-exports", "bulk-imports"}
    for prefix in SCRATCH_PREFIXES:
        assert prefix.why.strip(), f"{prefix.name} must say why it is skipped"
