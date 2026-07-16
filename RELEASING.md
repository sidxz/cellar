# Releasing Cellar

The frontend and backend are versioned **independently** with **SemVer**, and
the **git tag is the single source of truth**. CI builds the image, injects the
version, and publishes a changelog + GitHub Release.

## Tag namespaces

| Component | Tag form          | Image                              |
|-----------|-------------------|------------------------------------|
| Backend   | `backend-vX.Y.Z`  | `ghcr.io/sidxz/cellar-backend:X.Y.Z` |
| Frontend  | `frontend-vX.Y.Z` | `ghcr.io/sidxz/cellar-frontend:X.Y.Z` |

Pushing a tag in one namespace builds, tags, and releases **only** that
component. Pushes to `main` still publish `:latest` and `:sha-<sha>` images for
whichever component changed.

## Choosing the bump (Conventional Commits)

Look at the commits since the component's previous tag:

| Commit type                         | Bump   |
|-------------------------------------|--------|
| `fix:`                              | patch  |
| `feat:`                             | minor  |
| `feat!:` / `BREAKING CHANGE:` footer | major  |

A backend **major** bump signals a breaking API change — the moment to check the
frontend is compatible.

## Cutting a release

1. Make sure `main` is green and pulled locally.
2. Pick the next version per the table above. Inspect what changed:
   ```bash
   # commits touching the backend since its last tag
   git log "$(git tag --list 'backend-v*' --sort=-creatordate | head -1)"..HEAD -- backend/
   ```
3. Tag and push:
   ```bash
   git tag backend-v1.4.0      # or frontend-v2.1.0
   git push origin backend-v1.4.0
   ```
4. CI (`.github/workflows/publish-images.yml`) then:
   - builds **only** that component and tags the image `1.4.0`, `1.4`, `1`;
   - injects `APP_VERSION` / `GIT_SHA` / `BUILD_DATE` into the image;
   - generates a `git-cliff` changelog scoped to that component since its
     previous tag and publishes a **GitHub Release** ("Backend v1.4.0").

## Where the version shows up

- **App footer:** `UI v<version>` (sidebar), from the baked image.
- **About card** (`/settings` → About): UI version + commit + build date, the
  live **API** version (fetched from `GET /version`), and the environment.
- **Backend `GET /version`:** unauthenticated JSON
  `{name, version, git_sha, build_date, environment}` — handy for `curl`/monitoring.

## Between releases

Builds between tags identify as the `git describe` form, e.g.
`1.4.0-128-g84e7848` — base tag, commits ahead, short sha. That is expected and
honest: it is not a clean release.

## Not the source of truth

`backend/pyproject.toml` and `frontend/package.json` carry a placeholder version
used only as a local-dev fallback. **Do not** treat them as authoritative — the
git tag is. There is nothing to bump in those files when releasing.
