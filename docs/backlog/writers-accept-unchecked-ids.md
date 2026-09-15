# Writers accept ids they never check

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`). Dangling references don't need a delete; these writers can create them directly. Line numbers are at `13eb5c17`, from the analysis passes.

**Root cause:** references across aggregates carry no FK by design, so an unchecked id from the client is stored as given:

- **Campaigns** (`backend/src/cellar/application/research_organization/`):
  - `add_campaign_channel.py:106-121` and `add_results_from_runs.py:232-243` store `protocol_id` and `readout_definition_id` unchecked (only `mirror_protocol_channels.py:229-233` checks).
  - `add_result_row.py:94-98` stores `molecule_id` unchecked.
  - `create_campaign.py:66-73` stores `project_id` and the supersedes ids unchecked.
- **Screening data:**
  - `application/screening/bulk_create_readout_data.py:87-88` takes raw `molecule_id` and `batch_id`.
  - The manual curve endpoint (`interface/routes/readout_data.py:501-527`) does the same.
  - The fitter then copies those ids into new curves (`fit_dose_response.py:331-375`).
- **Synthesis:**
  - `application/chemical_registration/synthesis_routes.py` takes reagent `molecule_id` (:264), `product_molecule_id` (:282) and step `batch_id` (:326) unchecked.
  - `application/inventory/synthesis_requests.py` takes `project_id` and `parent_request_id` (:193-194) and `proposed_route_id` (:339-355) unchecked.
- **Attachments and favorites:** `application/attachment/upload_attachment.py:27-77` and `application/personalization/add_favorite.py:54-67` never check the target exists.

**Fix direction:** check each referenced id exists in the caller's workspace, returning `NotFoundError` as `MoveSample` and the plate storage-location fix do. Campaigns first, because their ids end up in published documents daikon reads.
