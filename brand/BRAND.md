# Teknakul — Brand & Theming

How the Teknakul brand is applied to the Sharkey instance, and the source assets.

## Applied 2026-07-20 (all data-driven — zero rebase cost)

Everything here is stored in the instance `meta` table via the admin API
(`admin/update-meta`), **not** in forked source. It survives every upstream Sharkey upgrade
untouched. This is the thinnest possible "branding overlay."

| Setting | Value |
|---|---|
| `name` / `shortName` | Teknakul |
| `description` | The professional network where somewhat-technical people become confident, AI-augmented operators of the Modern Workplace… |
| `themeColor` | `#12b5a5` (PWA/browser chrome + manifest `theme_color`) |
| `defaultDarkTheme` | accent `#12b5a5` on Sharkey dark base |
| `defaultLightTheme` | accent `#0e9c90` on Sharkey light base |
| `iconUrl` / `app512IconUrl` | `icon-512.png` (monogram) |
| `app192IconUrl` | `icon-192.png` |
| `logoImageUrl` | `wordmark.png` (teal wordmark, theme-safe) |
| `bannerUrl` / `backgroundImageUrl` | `banner.png` |
| `maintainerName` | Teknakul (Phoenixtekk) |

Assets were uploaded to the instance Drive; the live URLs are recorded server-side at
`/home/lacy/teknakul/brand/drive-urls.txt` (mode 600).

## Palette

| Token | Hex | Use |
|---|---|---|
| Teal (primary) | `#12b5a5` | Accent, theme color |
| Teal bright | `#2fe3cf` | Gradient top, highlights |
| Teal deep | `#0e9c90` | Gradient bottom, light-theme accent |
| Charcoal | `#0a1212` / `#0c1414` / `#101a1a` | Backgrounds, monogram tile |
| Ink text | `#eafaf8` | Wordmark on dark (banner) |
| Muted teal | `#7fb8b2` | Secondary text |

The teal-on-charcoal identity is deliberately distinct from Phoenixtekk's ember-on-charcoal
while keeping the dark, technical family feel — "calm, capable, AI-augmented."

## Source assets (this folder)

| File | What | Notes |
|---|---|---|
| `icon.svg` → `icon-512.png` / `icon-192.png` | Monogram: teal "T" + ascend chevron + node dot on charcoal | Font-free (rasterizes identically anywhere) |
| `wordmark.svg` → `wordmark.png` | "teknakul" in teal + monogram tile | Teal so it reads on light *and* dark themes |
| `banner.svg` → `banner.png` | Hero: charcoal-teal gradient, grid, glow, wordmark + tagline | Near-white wordmark (only shown on the dark banner) |

Rasterized via the Sharkey container's own `sharp` (Noto Sans for text). To regenerate: edit the
SVG, then render with `sharp(svg,{density:384}).png()`.

## Reproduce / re-apply

`admin/update-meta` with the fields above, authenticated by the root admin token at
`/home/lacy/teknakul/.admin-credentials` (mode 600). Re-upload PNGs via `drive/files/create` if the
Drive URLs ever change.

## Not done yet (deeper, source-level rebrand — optional)

Instance `name` covers the vast majority of user-facing text. A handful of "Sharkey"/"Misskey"
strings remain in the client (about page, some meta/OG defaults, PWA internals). Removing those
requires **forking the frontend and building our own image** — a heavier change reserved for later,
weighed against the rebase-maintenance cost. Data-driven branding above gets ~90% of the way with
zero maintenance.
