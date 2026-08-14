# Insights h-bar 24-char label truncation still clips ~2 leading chars on long compound-word names

**Found:** 2026-08-13, during S5 Task 13 fix-round re-verification of the insights h-bar
label-clipping defect (`plate-insights-panel.tsx`, sidxz/cellar#71).

**Root cause:** the fix truncates y-axis category labels to 24 chars (incl. trailing "…") to fit
the existing fixed 140px left margin (24 chars / 140px were both explicit numbers from the fix
task, not independently chosen here). For labels containing long, non-space-separated words (e.g.
`hit_collection`), a 24-char string can still render wider than 140px in Plotly's default
axis-tick font. Measured live against the real dev seed: 3 of 5 bars on the "Top groups" chart
(`sac1-hit_collection-Hug…` etc., each ~152px rendered) overflow the chart SVG's left edge by
~13px (~2 characters), so `sac1-hit_collection-NaO…` visually reads as `c1-hit_collection-NaO…`.

**Impact:** minor cosmetic residual — the leading ~2 characters of the *widest* labels are
invisible without hovering (full name is always available via `customdata` + `hovertemplate`, and
this is a much smaller/less confusing clip than the original defect, which silently dropped the
entire meaningful org/type prefix with no truncation indicator at all). Not observed on "Storage
occupancy" in the current seed (its one bucket, "Unassigned", is short), but the same code path
would hit it for a sufficiently long location name.

**Fix direction:** either lower the cap (e.g. ~20–21 chars) or measure actual rendered text width
against the margin dynamically (canvas `measureText`) instead of a fixed character count. Left
as-is for this task since 24 chars / 140px margin were the task's explicit numbers — flagging for
a follow-up decision rather than unilaterally changing a prescribed value.
