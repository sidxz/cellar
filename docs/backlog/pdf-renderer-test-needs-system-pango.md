# `test_pdf_renders_a_small_report` fails on a bare macOS host

**Status:** open · **Found:** 2026-09-16, incidentally, while running the full unit
suite for an unrelated change (replication script). Not caused by that work.

## Symptom

```
tests/unit/application/export/renderers/test_pdf_renderer.py::test_pdf_renders_a_small_report
OSError: cannot load library 'libgobject-2.0-0': dlopen(libgobject-2.0-0, 0x0002) ...
  ctypes.util.find_library() did not manage to locate a library called 'libgobject-2.0-0'
```

`1 failed, 3391 passed`. Every other unit test passes.

## Root cause

WeasyPrint is a binding, not a pure-Python renderer: it dlopens the system GObject /
Pango / cairo stack at import time. `uv sync` installs the Python package but cannot
install those, so a Mac without `brew install pango` fails this one test. The Docker
image has them, which is why CI is green and only local runs see this.

## Why it is not just "install pango"

That is the fix for a developer who needs to work on PDF export. The repo-level problem
is that a unit test silently depends on a system library nobody is told about: it is not
in `make install`, not in the README, and the failure names a dylib rather than the
real requirement. The suite should either skip with a clear reason when the library is
absent, or the dependency should be declared where a developer will actually read it.

## Options

- `pytest.importorskip` / a `pytest.mark.skipif` on the WeasyPrint import, with a message
  naming `brew install pango`. Keeps `make test` green on a fresh checkout; costs real
  coverage silently on every dev machine that lacks it.
- Declare it in `make install` and the setup docs, and let the test keep failing loudly
  until it is installed. Honest, but makes a fresh checkout red.
- Move the test to `tests/integration/` where a system dependency is expected.

Third option looks closest to right — it is not really a unit test — but that is a call
for whoever owns export, not a drive-by fix.
