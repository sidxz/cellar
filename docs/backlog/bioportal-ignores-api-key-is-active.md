# BioPortal client keeps using a workspace key an admin has deactivated

**Status:** open · **Found:** 2026-10-09, reading `_resolve_api_key` during the protocol sp2-6 final verification. Not caused by that branch's behaviour; the resolution path predates it.

## Symptom

An admin sets the `bioportal` entry under Admin → API Keys to inactive (`ExternalApiKey.is_active = False`). Ontology search and `has_api_key` keep working with that workspace's key, so the toggle has no effect on BioPortal.

## Root cause

`backend/src/cellar/infrastructure/external/bioportal/client.py::_resolve_api_key` reads the secret straight from the `SecretProvider` (`f"{workspace_id}:bioportal"`) and never loads the `ExternalApiKey` registry row, so `is_active` is never consulted. The data-source import path does honour it (`get_data_source_for_import.py` rejects `key_entry is None or not key_entry.is_active`), so the two consumers of the same registry disagree.

## Fix direction

Decide what "inactive" should mean for BioPortal: most likely a deactivated workspace key is skipped and resolution falls through to the `BIOPORTAL_API_KEY` env var (or the "needs a key" error). The infrastructure client cannot reach the repository directly without inverting layers, so resolve the registry state in the application layer (or inject a small port that returns the secret only when the entry is active) rather than reading the repository inside the client. Add a test: inactive entry plus stored secret must not be used.
