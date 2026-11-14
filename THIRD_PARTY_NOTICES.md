# Third-party notices

## Car manufacturer logos
`web/makes/` holds the logos of the manufacturers that appear in iRacing, copied from the Apex Overlays project
(`ui/static/assets/makes/`). There they were taken from the
[car-logos-dataset](https://github.com/filippofilip95/car-logos-dataset) (MIT License, © filippofilip95; thumbnails);
the Dallara, Oreca, Tatuus and Williams logos (not in that dataset) were supplied by the project owner.
Logos drawn in black or navy have their dark parts lightened here (and Genesis's white box removed), so they
read on dark backgrounds.
The logos themselves are trademarks of their respective owners and are shown only to identify each car's manufacturer.

The car-name matching in `apex/makes.py` is ported from Apex Overlays (`crates/core/src/lookup.rs`).

## Overlay fonts
The fonts offered under Widget Settings → All overlays & boards → Font are bundled in `web/fonts/overlay/`,
copied from the Apex Overlays project (`ui/static/assets/fonts/overlay/`; Latin and Latin Extended subsets,
from Google Fonts). Each is licensed under the [SIL Open Font License 1.1](https://openfontlicense.org); the
licence and copyright notice of each font is in `web/fonts/overlay/licenses/`:
Antonio, Archivo Narrow, Barlow Condensed, Big Shoulders Display, Chakra Petch, Exo 2, Fira Sans Condensed,
IBM Plex Sans Condensed, Inter, Kanit, Montserrat, Orbitron, Oswald, Rajdhani, Roboto Condensed,
Saira Semi Condensed, Sora, Space Grotesk, Teko and Titillium Web.
