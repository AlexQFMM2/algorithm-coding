# Ace Editor

Vendored from `ace-builds@1.45.2` (BSD-3-Clause).

Upstream: https://github.com/ajaxorg/ace-builds

Only the minified core, C/C++ mode, search box, language tools, One Dark / GitHub Light Default
themes, static stylesheets and referenced image assets are included.
Files are copied without modification, preserving CSS asset paths.
The complete license is in `LICENSE`.

The app enables `useStrictCSP` and loads the CSS files directly, so Ace works
under the existing Content Security Policy without inline style sheets, CDN
requests, workers or a build step. Application-specific visual adjustments
live in `styles/workspace.css`, outside this directory.
