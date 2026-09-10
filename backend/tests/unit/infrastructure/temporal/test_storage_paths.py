"""Every on-disk write hangs off STORAGE_ROOT (the mounted volume in prod)."""

from pathlib import Path

from cellar.infrastructure.temporal.activities.file_parsing import save_upload_to_storage


def test_bulk_import_upload_is_saved_under_storage_root(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    saved = Path(save_upload_to_storage(b"a,b\n1,2\n", "upload.csv"))
    assert saved.read_bytes() == b"a,b\n1,2\n"
    assert saved.parent.parent == tmp_path / "bulk-imports"
