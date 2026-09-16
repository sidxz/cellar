# File storage — follow-ups after the STORAGE_ROOT fix (2026-09-09)

**Context:** `FsspecStorageClient` read `BASE_PATH` (default `./data/attachments`) while every
deploy sets `STORAGE_ROOT=/data/storage` and mounts the volume there, so attachments and export
downloads never reached the volume in prod (the image's `/app` is root-owned and the process runs
as `cellar`, so uploads failed with "Failed to upload file to storage"). Fixed on `feat/daikon-asks`:
one `StorageSettings.storage_root` for all writers, `ensure_storage_root()` at API + worker startup
(refuses to boot a production root that is not on a mounted volume).

## Not done, worth doing

1. **URL-based backend** (docu-store's `FsspecBlobStore` shape): `STORAGE_URL=file:///data/storage`
   or `s3://bucket/prefix` + `storage_options`, opened with `fsspec.open(url)`. Makes MinIO/S3 a
   config change (+ `s3fs`). Not needed while ned uses the shared NFS volume.
2. **Content hash on `Attachment`**: stream the upload in chunks and persist SHA-256 + size
   (docu-store's `StoredBlob`). Part 11-relevant integrity evidence; needs a nullable column.
3. **Verify on ned** after deploy: `ls /data/storage/attachments` should start filling; the
   backend log should show `storage.root_ready root=/data/storage production=True` at boot.
4. Dev machines: existing `backend/data/attachments` must be moved to
   `backend/data/storage/attachments` once (done on the author's machine).
