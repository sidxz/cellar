# chemcellar docs site

User-facing documentation for **chemcellar** (Cellar), built with
[Nextra](https://nextra.site) (Next.js + MDX). This is a **standalone** pnpm
project; it does not import from `../frontend` at build time.

## Pinned versions

| Package | Version | Why |
|---|---|---|
| `nextra` / `nextra-theme-docs` | `4.6.1` | Latest stable Nextra (App Router). |
| `next` | `15.5.18` | Newest stable Next.js that Nextra 4 officially supports. The app uses Next 16; the docs site is pinned independently to avoid bleeding-edge incompatibility. |
| `react` / `react-dom` | `^19.1.0` | Matches the app and Nextra 4's peer range. |

Chemistry deps mirror `frontend/package.json`: `@rdkit/rdkit 2025.3.4-1.0.0`,
`ketcher-* ^3.12.0`, `plotly.js ^3.5.0`, `react-plotly.js ^2.6.0`.

## Develop

```bash
pnpm install   # also copies the RDKit WASM into public/ via postinstall
pnpm dev       # http://localhost:3000
pnpm build
```

## Layout

```
content/        # MDX pages + _meta.ts nav (the full IA)
components/      # RdkitProvider + 6 client-only chemistry widgets
app/             # Nextra App Router entry (layout + catch-all page)
mdx-components.tsx  # registers widgets globally for MDX
STYLE_GUIDE.md   # writing rules (read before authoring pages)
WIDGETS.md       # widget prop contract + embed snippets
```

## Authoring

Read `STYLE_GUIDE.md` and `WIDGETS.md` first. All six widgets are available in
any `.mdx` page without an import.
