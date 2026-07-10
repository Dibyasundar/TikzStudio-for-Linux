# TikZ Studio

A WYSIWYG desktop editor for TikZ/LaTeX diagrams on Linux, with **live
two-way synchronization** between a visual canvas and the TikZ source code.

## Install (Debian/Ubuntu)

```bash
sudo apt install ./tikzstudio_1.2.0_all.deb
```

This pulls in the dependencies automatically: `python3-pyqt6`,
`texlive-latex-base`, `texlive-pictures` (TikZ), `texlive-latex-extra`
(the `standalone` class) and `poppler-utils` (PNG export/preview).

Launch from the application menu (**TikZ Studio**) or run `tikzstudio`.

## Features

**Pre-compiled element library (left palette)**
- On first run the app pre-compiles the whole built-in catalog (~34
  elements from TikZ libraries: `shapes.geometric`, `shapes.symbols`,
  `shapes.misc`, `shapes.callouts`, `shapes.arrows`, decorated paths from
  `decorations.pathmorphing`/`pathreplacing`, and flowchart blocks) in a
  single pdflatex run, renders transparent thumbnails with pdftocairo,
  and caches everything in `~/.cache/tikzstudio/library`. Later launches
  load instantly from the cache; *Document ▸ Rebuild element library*
  re-compiles it.
- Click a palette element, then click the canvas to place it. Required
  TikZ libraries/packages are added to the preamble automatically. Placed
  elements are movable and round-trip through the code via a
  `% lib:<name>` marker; if you edit their code by hand they degrade
  gracefully to raw TikZ and still compile.
- **＋ Custom element…** lets you define your own: paste any TikZ snippet
  drawn around (0,0) (optionally with `@X@`,`@Y@` anchor placeholders —
  otherwise it is wrapped in a shifted scope automatically). It is
  test-compiled first; on success a thumbnail is rendered and the element
  appears in the palette permanently (marked ★).

**Visual canvas (left/center)**
- **Distinct arrowheads**: `->`/`<-`/`<->` render as classic open tips,
  `-Stealth` as a filled dart, `-Latex` as a filled triangle — on lines,
  Bézier curves, arcs and freehand plots, at both ends.
- **Reshape by dragging coordinates**: selecting a single element shows
  square handles on its defining points (rectangle corners, circle centre
  + radius, ellipse radii, every polygon/plot vertex, Bézier endpoints and
  control points with guide lines, arc centre/start/end, grid corners).
  Handles snap to the grid.
- **Precise positioning**: dragging snaps live to the grid; arrow keys
  nudge the selection — plain = 0.05 cm, Shift = one grid cell,
  Ctrl = 0.01 cm.
- **Scope grouping**: select several elements and press Ctrl+G to wrap
  them in a `\begin{scope}` — drag to move them together, set *Group
  scale* in Properties to resize the whole group (emitted as
  `[shift={...}, scale=...]`). Ctrl+Shift+G ungroups and bakes the
  transform into the coordinates. Scopes round-trip through the code
  editor and nest.
- Basic elements in the top toolbar: select/move, line, arrow, rectangle,
  circle, ellipse, polygon (click vertices, double-click to close), star,
  Bézier curve, freehand, arc, grid, text node, image.
- **Adjustable grid size** (toolbar, 0.05–5 cm): sets both the visible
  canvas grid and the snap step for precise drawing.
- Snap-to-grid, Ctrl+Wheel to zoom, drag to move elements,
  double-click a text node to edit its LaTeX content, Del to delete.
- Insert menu adds a **tree layout** template, **callout** template, and
  images (`\includegraphics`) — required TikZ libraries/packages are added
  to the preamble automatically.

**Code editor (right dock)**
- TikZ syntax highlighting and autocompletion (`Ctrl+Space`, or automatic
  after typing `\`).
- **Number scrubbing**: hold `Ctrl` and scroll the mouse wheel over any
  number to nudge it (0.25 steps; `Ctrl+Shift` = 1.0 steps).
- **Two-way sync**: draw on the canvas and the code updates; edit the code
  and the canvas updates (~0.7 s after you stop typing). Statements the
  visual parser doesn't understand are kept verbatim as *raw TikZ* — they
  still compile, they just aren't draggable on the canvas. Nothing you
  write by hand is ever lost.

**Multi-figure documents**
- Tabs above the canvas: one tab per `tikzpicture`. "＋ figure" adds
  another; standalone produces one PDF page per figure.

**Transparency**
- Fill/stroke transparency is reflected live on the canvas: the
  Properties dock has both *Opacity* (whole element) and *Fill opacity*
  (TikZ `fill opacity`), and colour mixes like `blue!20` plus
  `{rgb,255:...}` colours are rendered faithfully.

**Packages & standalone document**
- *Document ▸ Packages & libraries…* (`Ctrl+P`) manages
  `\documentclass[...]{standalone}` options, the `\usepackage` list
  (with quick-add buttons for amsmath, graphicx, pgfplots, …),
  `\usetikzlibrary` checkboxes, and an extra-preamble box for macros or
  `\definecolor`.
- *Document ▸ View full standalone source* shows the exact `.tex` that
  gets compiled.

**Working folder follows the file**
- Opening or saving a `.tex` makes its folder the figure's working
  directory: images there are inserted and stored with *relative* paths,
  shown on the canvas, and resolved at compile time (via TEXINPUTS), so
  the document stays portable alongside its images.

**Build, import, export**
- `F5` compiles with `pdflatex`; the *PDF preview & log* dock shows the
  real rendered pages and the LaTeX log. Enable **Auto-compile** to
  rebuild after every change.
- Import: *File ▸ Open .tex* parses an existing file — preamble packages,
  TikZ libraries and every `tikzpicture` become figures.
- Export: PDF (`Ctrl+E`) and PNG at a chosen DPI (`Ctrl+Shift+E`).
  *File ▸ Save .tex* writes the standalone document.

## Tips

- The Properties dock (left) sets stroke/fill colour, line width, dash,
  arrow tips and opacity — for the *selected* element, or as defaults for
  new shapes when nothing is selected. Arc angles, grid step and image
  width appear there contextually.
- Exact coordinates are easiest to fine-tune in the code panel with
  Ctrl+Wheel scrubbing.
- Trees, decorations, `\foreach` loops etc. are fully supported through
  the code editor / raw TikZ path and compile normally.

## Running from source

```bash
sudo apt install python3-pyqt6 texlive-latex-extra texlive-pictures poppler-utils
python3 run.py
```

## Layout

```
tikzstudio/
  elements.py   data model + TikZ code generation
  parser.py     TikZ -> model (two-way sync, lossless via RawEl)
  canvas.py     QGraphicsView drawing canvas & tools
  editor.py     code editor: highlighting, completion, number scrubbing
  compiler.py   background pdflatex + pdftoppm preview
  library.py    pre-compiled element library, cache & custom elements
  dialogs.py    package/library manager
  app.py        main window
```
