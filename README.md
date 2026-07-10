**This project aims to develop a native Linux interface inspired by TikZedit. Please note that the majority of the codebase was generated using Claude's Fabel AI model. The software is currently under active development and is provided "as is," so please use it at your own discretion. We anticipate rolling out new version releases in the near future.**



# TikZ Studio

A WYSIWYG desktop editor for TikZ/LaTeX diagrams on Linux, with **live
two-way synchronization** between a visual canvas and the TikZ source code.

## Install (Debian/Ubuntu)

```bash
sudo apt install ./tikzstudio_1.6.0_all.deb
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
- **Whole-element multi-select**: the rubber band selects only elements
  fully inside it (no accidental partial grabs); the Properties panel
  bulk-edits everything selected.
- **N-point Bézier curves**: the Bézier tool is click-based — click any
  number of anchor points, double-click to finish a smooth
  Catmull-Rom curve emitted as chained `.. controls ..` segments; every
  anchor and control point stays draggable with guide lines.
- **PGF layer rendering**: raw `\pgfset…`/`\pgftransform…` commands in
  the code (no semicolon needed) act as a running graphics state that
  the canvas honours on subsequent paths — line width, dash pattern &
  phase, inner line width/dash (double lines), butt/round/rect caps,
  miter/round/bevel joins + miter limit, stroke/fill colour &
  opacities, blend modes, even-odd vs nonzero fill rule, arrow
  start/end tips, shorten start/end, and shift/scale/x-yscale/rotate
  transforms. Commands are preserved verbatim in the code.
- The star tool moved from the toolbar into the element collection
  (Geometric group: *star node*, *star 6*, *star path*); the palette
  rebuilds automatically when new built-ins appear.
- **Text formatting** for the selected node in the Properties dock:
  Bold / Italic / Underline toggles, a text-colour picker
  (`\textcolor`) and a size combo (`\tiny` … `\Huge`) — wrapped as
  proper LaTeX and rendered on the canvas.
- **Auto-select after drawing**: finishing any shape switches back to
  the Select tool with the fresh element already selected.
- **Icon toolbar** with tooltips; the Arrow button is a dropdown
  (straight / multipoint) and ⧉ / ⧈ buttons group and ungroup scopes.
- **Full scope & path transforms**: scopes support `shift`, `rotate`,
  `scale`, `xscale`, `yscale`, `xshift`, `yshift` (negative scales
  mirror) with Group rotate/xscale/yscale spinners in Properties — and
  the same transform options on *any* element (`\draw[xscale=2,
  rotate=15] …`) render correctly on the canvas.
- **Jump code ⇄ element**: right-click an element → *Show in code*
  highlights its statement; right-click a code line → *Show element on
  canvas* selects and centres it.
- **Faithful option rendering**: node options (`anchor=`, `scale=`,
  `rotate=`, `minimum width/height/size=`, `text width=` with wrapping,
  `align=`, positional `above`/`below left`/…) all affect the canvas;
  `\includegraphics` honours every graphicx combination (width+height,
  `keepaspectratio`, `scale=`, `angle=`, other keys preserved); xcolor
  mix chains like `green!40!blue!20` render exactly; `draw opacity`,
  `fill opacity` and `rounded corners` are shown. **Any other TikZ
  option typed in code is preserved verbatim** — elements no longer
  drop out of visual editing because of an option the canvas doesn't
  draw.
- **Math on canvas**: `$...$` node text renders as Unicode math (Greek
  letters, sub/superscripts, operators, fractions) so labels look right
  without waiting for a compile.
- **Multipoint arrows**: the Arrow toolbar button is a dropdown —
  straight (drag) or multipoint (click waypoints, double-click to
  finish), emitted as an open polyline with arrow tips.
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

**Workspace**
- **Accordion side panels**: left panel stacks Properties / Elements /
  Files, right panel stacks TikZ code / PDF preview — with slim margin
  arrows on both window edges to hide or show each side entirely.
- **File explorer**: the Files section browses the current working
  folder; double-click opens `.tex`/`.tikz` files or inserts images.
  The active file's full path is always shown above the canvas.
- **PDF preview zoom**: − / ＋ / 1:1 controls with a live percentage.
- **Smart Properties panel**: only the fields valid for the current
  selection are shown; with a multi-selection it shows the fields all
  selected elements share and edits apply to **all of them at once**
  (bulk edit).
- **Element groups**: palette elements are organised into groups
  (Geometric, Symbols, Callouts, Arrows, Paths, Flowchart, Misc) with a
  filter dropdown; custom elements go into user-named groups —
  right-click a custom element to change its group or delete it.

**Code editor (right dock)**
- **Two editing modes**: *Current figure body* (default, syncs with the
  canvas) or *Whole document* — full .tex file editing including the
  preamble, packages and every figure, still live-synced back into the
  app. Opens `.tex`, `.tikz`, `.pgf` and bare TikZ body files.
- **Search & replace** with Ctrl+H (find next / replace / replace all,
  match-case), also in the right-click menu; legacy `{\bf …}`,
  `{\it …}`, `{\em …}` switches are understood and rendered.
- **Comment / uncomment** the selected lines with Ctrl+T / Ctrl+R;
  **find** with Ctrl+F (F3 next, Shift+F3 previous); **undo/redo** with
  Ctrl+Z / Ctrl+Shift+Z (works in the editor *and* on canvas edits —
  each figure keeps a 200-step history).
- **Auto-suggest while typing**: commands complete after `\`, and plain
  option/tag words (anchors, `rounded corners`, decorations, graphicx
  keys, …) pop up after two letters. Ctrl+Space forces the popup.
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
