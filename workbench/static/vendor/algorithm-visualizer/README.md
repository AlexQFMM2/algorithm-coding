# Algorithm Visualizer integration

Frontend source: https://github.com/algorithm-visualizer/algorithm-visualizer
Pinned commit: `18de2edf6b629e843ee4bcedfa2208d22b253f0f` (MIT).
Original license: `upstream/LICENSE`; retain it with source and built distribution.

Reused: Array1D/Array2D/Log tracer models; table and log renderers; layout models;
Player command chunking; VisualizationViewer object construction and replay.

Local changes:
- Replace circular barrel imports and subclass checks with direct imports and explicit layout/dimension getters.
- Isolated replay from Redux, GitHub, axios, the remote compiler, and the upstream app.
- Build only the array/log/layout subset using React and esbuild; dependency lock is committed.
- Replace SCSS/app theme dependencies with scoped CSS modules using existing theme tokens.
- Log output is plain text (upstream used HTML); arrays expose selection semantics.
- Native scrolling replaces mouse-only pan/zoom; layout uses the local modal container.
- Restrict accepted constructors/methods; permit teaching metadata after the line number in delay args.

The C++ `workbench/include/visualization.hpp` is an original, local-only command
writer. It does NOT vendor or derive implementation code from `tracers.cpp`,
whose checked upstream repository declares no license. JSON serialization uses
nlohmann/json v3.12.0 (MIT), vendored with its license and SHA256 manifest.

Build: `npm ci && npm run build` in this directory. Generated assets under
`workbench/static/vendor/algorithm-visualizer/` are committed. No Node process or
network connection is needed to run the application.
