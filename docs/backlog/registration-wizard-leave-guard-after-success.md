# Registration wizard warns "Leave site?" after the work is done

**Found:** 2026-10-01, in-app check of register-to-projects (feat/register-to-projects).

**Symptom:** on the Summary step — compound already registered, nothing left
unsaved — navigating away (reload, address bar, external link) still raises the
browser's "Leave site? Changes you made may not be saved" dialog.

**Root cause:** `registration-wizard.tsx` installs a `beforeunload` handler that
calls `e.preventDefault()` whenever `mode !== null`, i.e. from the moment a mode is
picked until `reset()`. It never looks at the step, so the Summary step (and the
bulk Processing step after the job is submitted) are guarded too.

**Fix direction:** guard only while there is unsubmitted input — Input/Preview/Batch
steps before submission — e.g. derive `hasUnsavedInput` from `currentStep` and
whether `singleResult` / `workflowId` exist. In-app links use the Next router and
are not affected; only full-page navigations are.
