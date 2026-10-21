# Opora tokens

`tokens.css` preserves the actual palette, Inter typography, radii, spacing and utilities from `prototype-src/helmet.html` at reference 028a0c3. Imported once by the application providers. Scope page content in `.dm`. The original four-circle brand and SVG paths are in `src/ui/Brand.tsx` and `Icon.tsx`; no school product skin is imported. Feature-specific CSS remains with each feature.

Inter is self-hosted from the pinned OD Google Fonts mirror. Five unchanged WOFF2 subsets (Cyrillic, Cyrillic-ext, Latin, Latin-ext, Greek), same family and 400-700 weights, no remote font request. Font tables confirm Inter Project Authors copyright and variable wght100-900 support. SIL OFL 1.1 and binary SHA256 provenance are in `fonts/`. Vite bundles only referenced font assets.
