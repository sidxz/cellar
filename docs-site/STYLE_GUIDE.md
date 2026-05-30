# chemcellar Docs — Style Guide

This guide is the contract for everyone writing pages in `docs-site/`. Read it
before you write. The audience is **scientists & biochemists** (primary),
**portfolio managers**, and **students new to pharma**. Write so a motivated
student can follow, without boring an expert.

---

## 1. Voice & tone

- **Clear, friendly, second person.** Address the reader as "you". Use "we" only
  when describing what chemcellar does on the reader's behalf.
- **Active voice, present tense.** "Click **Register**" — not "the Register
  button should be clicked".
- **Short sentences.** One idea per sentence. Prefer plain words over jargon.
- **Define every domain term on first use** in a page, then link it to the
  glossary (see §6).
- **No hype, no marketing.** Describe what the feature does and how to use it.
- **Only document shipped features.** If a feature is not in
  `docs/implementation-status.md` as shipped, it belongs only on the **Roadmap**
  page (`reference/roadmap.mdx`), never in a how-to guide.

---

## 2. Page template

Every **guide** page follows this shape:

```mdx
# <Task title — verb-first, e.g. "Register a single molecule">

**Who this is for:** <one line — e.g. "Bench chemists registering new compounds.">

**What you'll accomplish:** <one line — the outcome the reader will have at the end.>

## Before you start
<prerequisites: permissions, a workspace, data you'll need. Optional.>

## Steps
1. First action — bold the **UI label** you click or the **field** you fill.
2. Next action…
3. …

## What happens next / Result
<what the reader should see; where the data went.>

## Related
- Links to concepts, related guides, glossary terms.
```

**Concept** pages are explanatory, not step-based. They still open with a
one-line "what you'll learn" and link out to the guides that use the concept.

**Reference** pages (glossary, standards, FAQ, roadmap) follow their own natural
structure.

Keep H1 to one per page. Use `##`/`###` for structure. Number steps; bullet
everything else.

---

## 3. Callouts (Nextra)

Import once per page that needs them:

```mdx
import { Callout } from 'nextra/components'
```

Use the right type:

- **Note** — neutral context the reader should keep in mind.
  ```mdx
  <Callout type="info">chemcellar canonicalizes every structure on registration.</Callout>
  ```
- **Tip** — a shortcut or best practice.
  ```mdx
  <Callout type="default" emoji="💡">Paste a list of SMILES to register in bulk.</Callout>
  ```
- **Warning** — a destructive or irreversible action, or a compliance caution.
  ```mdx
  <Callout type="warning">…</Callout>
  ```

### Compliance & data-lock cautions (required)

Whenever a step touches an audited, signed, or locked record, add a **warning**
callout. Standard phrasings:

- **Audit trail:** "This action is recorded in the append-only audit trail."
- **Electronic signature / 21 CFR Part 11:** "Approving this run applies an
  electronic signature under 21 CFR Part 11. You cannot edit the data afterward
  without a documented, audited change."
- **Data lock:** "Once a run is approved, its data is **locked**. Further edits
  require an administrator and create a new audit entry."

Never imply the reader can quietly undo a locked or signed action.

---

## 4. Screenshots (placeholders only in this pass)

We are **not** capturing real UI yet. Mark every spot where a screenshot belongs
with a blockquote placeholder, describing what the image will show:

```mdx
> 📷 *Screenshot: the Register dialog with the structure editor open and SMILES filled in.*
```

One placeholder per distinct view. Be specific enough that whoever captures the
image later knows exactly what to show.

---

## 5. Interactive widgets

Six client-only chemistry widgets are available globally in MDX (no import
needed). See `WIDGETS.md` for the full prop contract and copy-paste snippets.

When you embed a widget:

1. Introduce it in **one line** ("Try changing the SMILES below to see how the
   structure updates.").
2. Embed the widget.
3. Add a **"try it" caption** as italic text or a `<Callout type="default"
   emoji="🧪">` so readers know it's interactive.

```mdx
Paste any SMILES to render it:

<StructureViewer smiles="CC(=O)Oc1ccccc1C(=O)O" />

*Try it: replace the SMILES with your own compound.*
```

Do not embed more than two widgets per page — they are heavy.

---

## 6. Glossary linking

- The glossary lives at `reference/glossary.mdx`.
- **On a term's first appearance on a page**, link it:
  `[InChIKey](/reference/glossary#inchikey)`.
- Subsequent uses on the same page are plain text.
- Glossary anchors are the lowercase, hyphenated term (`#dose-response`,
  `#tanimoto`). When you introduce a new term in a concept page, make sure it
  also exists in the glossary; if it doesn't, add it.

---

## 7. Naming & terminology rules

- The product is **chemcellar** (lowercase wordmark) / "Cellar". Don't invent
  other names.
- **Never name competitor products.** When referring to other systems compounds
  are imported from, say **"an external screening platform"** or **"an external
  data source"**. Code-level integration/connector names are acceptable when
  technically necessary (e.g. a data-source connector identifier), but prose
  should stay generic.
- Use the domain's own vocabulary consistently: *molecule*, *batch*, *sample*,
  *protocol*, *run*, *plate*, *well*, *readout*, *project*, *collection*,
  *campaign* — as defined in `docs/domain-model/`.

---

## 8. Links & paths

- Internal links are absolute from the site root: `/concepts/dose-response`.
- The repository link everywhere is `https://github.com/sidxz/cellar`.
- Don't link to internal dev docs (`docs/…`) from user-facing pages.
