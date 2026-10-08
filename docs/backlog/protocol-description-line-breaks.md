# Protocol descriptions lose their line breaks

**Found:** 2026-10-04, reviewing distilled protocols whose descriptions list the legacy protocols they absorb, one per line.

**Root cause:** the protocol Overview tab's Details card renders the description as normal-flow text, so newlines collapse and a list becomes one paragraph.

**Fix direction:** render the description with `white-space: pre-line` (or as Markdown, if the editor is meant to support it) in the Details card.
