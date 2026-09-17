# Learning section — design

*2026-09-17*

## Goal

Add a Learning section to maxconwa.github.io: a small set of high-polish lessons,
authored as `.ipynb` and `.md`, presented as an interactive directed graph whose
edges mean "this lesson comes before that one."

The audience is faculty search committees, employers, and prospective
collaborators. That sets the priorities:

- **Indexable.** Lesson pages are real static HTML. Someone who searches "Max
  Conway backpropagation" should land on the lesson, not on an empty shell that
  JavaScript later fills in.
- **Fast and self-contained.** The site currently loads zero third-party
  resources. Lesson pages keep that property. The single exception is Pyodide,
  which is too large to vendor and loads only when a visitor explicitly asks for
  it.
- **Visually of a piece with the rest of the site.** A lesson page should look
  like it was always part of `index.html`, not like a docs generator bolted on.

## Non-goals

- No completion tracking, accounts, quizzes, or progress state.
- No search. At portfolio scale the graph and the lesson list are enough.
- No comments or discussion.
- No client-side graph layout library. Layout is computed at build time.

## Authoring model

A lesson is one file in `lessons/`. Its **slug is its filename stem** — there is
no `slug` field to drift out of sync, and `prereqs` reference filename stems.
Renaming a file changes its URL; that is the accepted cost of having one source
of truth.

Front-matter for a `.md` lesson is YAML at the top of the file. For an `.ipynb`
lesson it is the same YAML in a **raw cell placed first in the notebook** — raw
cells are editable in any Jupyter UI, show up in diffs, and need no metadata
editor. The build strips that cell from the output.

```yaml
---
title: Backpropagation by hand
summary: Deriving the chain rule for a multilayer perceptron, then implementing it in numpy.
prereqs: [linear-algebra, gradient-descent]
track: Math foundations
runnable: true
packages: [numpy, matplotlib]
updated: 2026-09-17
---
```

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | Node label and page `<h1>`. |
| `summary` | yes | One or two sentences. Side panel, meta description, lesson header. |
| `prereqs` | yes (may be `[]`) | Slugs this lesson depends on. Defines the edges. |
| `track` | no | Groups lessons by colour in the graph. Free-form string. |
| `runnable` | no, default `false` | Whether the lesson offers in-browser execution. |
| `packages` | only when `runnable` | Pyodide packages to load. Validated against an allowlist. |
| `updated` | no | ISO date, shown in the lesson footer. |

Lesson-specific media lives in `lessons/media/<slug>/`. Notebook outputs are
extracted to files by the build rather than left as base64 in the HTML.

## Repository layout

```
lessons/                     sources, hand-authored
  linear-algebra.md
  backprop.ipynb
  media/<slug>/…
build/
  build.py                   the generator
  templates/                 base.html.j2, lesson.html.j2, graph.html.j2
  static/                    learn.css, graph.js, runner.js
  requirements.txt
  tests/                     pytest suite + fixture lessons
assets/vendor/katex/         vendored KaTeX (css, js, woff2)
docs/superpowers/specs/      this document
.github/workflows/pages.yml
```

Nothing generated is committed. `index.html`, `404.html`, `robots.txt`,
`assets/` stay exactly where they are and are copied into the output as-is.

## Build pipeline

`python build/sitegen.py --out _site` runs five stages. Each stage is a pure
function over the previous stage's output so it can be tested in isolation.

1. **Discover and parse.** Walk `lessons/`, split front-matter from body, and
   produce a `Lesson` record per file. Notebooks are read with `nbformat`.
2. **Validate.** See *Validation* below. Collects every error, then fails once.
3. **Render bodies.** Notebook cells are rendered directly rather than
   through `nbconvert`: markdown cells go through the same `markdown-it-py`
   pipeline the `.md` lessons use, code cells through the same Pygments
   highlighter, and image outputs are written to `learn/<slug>/output-N.png`.
   nbconvert's "basic" template emits JupyterLab's `jp-*` class soup, which
   would have to be restyled wholesale; rendering the cells directly means
   both formats produce identical markup, share one stylesheet, give the live
   runner a single DOM shape to find, and drop a heavy dependency.
   (Changed during implementation — the spec originally called for nbconvert.)
4. **Lay out the graph.** Build a `networkx.DiGraph`, emit DOT with
   `rankdir=TB` and fixed node sizes, shell out to `dot -Tplain`, and parse the
   result: node centres and sizes in inches, plus cubic bezier control points
   per edge. Convert to SVG user units at 72/inch and flip the y axis
   (`dot` is y-up, SVG is y-down).
5. **Emit.** Write lesson pages and the graph page; emit `learn.css` as
   `build/static/learn.css` (hand-written) concatenated with Pygments
   stylesheets generated for both colour schemes; copy static and vendored files,
   copy the existing root files, and regenerate `sitemap.xml` with every
   lesson URL.

## The graph page — `/learn/`

The layered DAG is **inline `<svg>` written into the HTML at build time**. It is
on the page before any JavaScript runs: crawlable, visible with JS disabled,
and it paints instantly. No graph library ships.

- Each node is an `<a href="/learn/<slug>/">` wrapping a `<rect>` and `<text>`,
  so keyboard tabbing and Enter work for free, middle-click and Cmd-click open
  in a new tab, and crawlers follow the edges of the curriculum.
- Edges are `<path>` elements built from the bezier control points, with an
  arrowhead `marker-end` pointing at the dependent lesson.
- Node fill is derived from `track`. Track names are sorted and assigned
  indices into a fixed palette, so a colour is stable as long as the set of
  track names is. The palette is chosen against the existing `--bg` and `--card`
  values in both light and dark mode and must clear 3:1 contrast for the node
  fill and 4.5:1 for the label; the dimmed state must stay legible rather than
  approaching the background. Notebooks and articles are distinguished by a
  small glyph rather than by colour, so the two encodings do not collide.
- The `<svg>` carries `role="img"` and a title describing the graph, and the
  lesson list below it is the accessible equivalent — selection state is
  mirrored to `aria-current` on the corresponding list item.
- Beneath the SVG, always in the DOM, is an `<ol>` of every lesson with its
  summary and prerequisites. This is the mobile view, the no-JS view, and the
  SEO surface, and it is not a duplicate maintained by hand — the same data
  renders it.

`graph.js` (~150 lines, vanilla, no dependencies) adds:

- **Selection.** Click a node to select it. Its transitive ancestors — every
  lesson you need first — highlight along with the edges connecting them.
  Descendants get an outline treatment ("what this unlocks"). Everything else
  dims. Escape clears.
- **Side panel.** Title, summary, format and runnable badges, prerequisite
  links, unlocks links, and an Open button. Under 760px — the breakpoint
  `index.html` already uses — it becomes a bottom sheet.
- **Pan and zoom** by updating the SVG `viewBox` on pointer drag and wheel.
- **Deep links.** `/learn/#backprop` selects that node on load, and selecting a
  node updates the hash.

Adjacency for ancestor and descendant walks is embedded as a
`<script type="application/json">` block — the same data the SVG was built
from, so the two cannot disagree.

## Lesson pages — `/learn/<slug>/`

Breadcrumb, `<h1>`, summary, badges, and prerequisite chips linking back to
those lessons. Then the rendered body. Then a footer listing the lessons this
one unlocks, which turns the graph into navigation rather than decoration.

- Styling reuses the existing CSS custom properties, so light and dark mode work
  with no new colour decisions. Prose measure widens from 62ch to ~72ch to give
  code room.
- **Math.** Detected at build time; only pages that contain math load the
  vendored KaTeX CSS and auto-render script. Pages without math load nothing.
- **Structured data.** Each lesson emits `LearningResource` JSON-LD whose
  `author` points at the existing `Person` block in `index.html`.
- **Read-only lessons** (`runnable: false`) show saved notebook outputs. A
  `.ipynb` lesson gets an "Open in Colab" button
  (`colab.research.google.com/github/maxconwa/maxconwa.github.io/blob/main/lessons/<slug>.ipynb`);
  a `.md` lesson has no notebook to open, so it gets a "View source" link to the
  file on GitHub instead.

## Live cells

Lessons marked `runnable: true` get one button at the top: **"Run this lesson in
your browser."** Until it is pressed the page is exactly the static rendered
lesson and has cost the visitor nothing.

On activation `runner.js` loads Pyodide from the jsDelivr CDN, loads the
lesson's declared `packages`, and converts each code cell into an editable cell
with its own Run button and output area. A status chip reports booting, ready,
running, or failed. There is a Run-all and a Reset that restores the original
sources.

- **Editing** uses a styled `<textarea>` sized to its content, with Tab
  indenting rather than escaping the cell — no editor dependency. Syntax highlighting is present on the static page and is dropped
  once a cell becomes editable. This is a deliberate trade (see *Deferred*).
- **Plots** work through a small Python shim injected at kernel boot: after each
  cell, any open matplotlib figures are serialised to PNG and appended to that
  cell's output.
- **State** is a single shared namespace. Running a cell out of order is allowed;
  if an earlier cell has not run, the cell shows an unobtrusive note rather than
  blocking.
- **Failure is contained.** If Pyodide does not load, the button reports the
  error and the static lesson remains completely readable. The read path never
  depends on the run path.

Pyodide cannot run PyTorch, MuJoCo, or ROS. Lessons covering those are
`runnable: false` by design — they show saved outputs, figures, or video, and
link out to Colab. The `packages` allowlist makes that a build-time error rather
than a broken page.

## Validation

The build collects **all** errors before failing, and prints them as a list with
file paths. Any of these fails the build:

- duplicate slug
- `prereqs` entry that matches no lesson
- a cycle in the prerequisite graph (reported as the actual cycle path)
- missing `title` or `summary`
- `packages` declared on a non-runnable lesson, or absent on a runnable one
- a `packages` entry outside the Pyodide allowlist
- an internal link in generated output pointing at a path not present in `_site`

Warnings that do not fail the build: a notebook with no saved outputs and
`runnable: false`; a lesson unreachable from any root; a missing `updated` date.

A missing `dot` binary produces an explicit "install graphviz" message rather
than a traceback.

## CI and deploy

`.github/workflows/pages.yml`, triggered on push to `main` and manually:
install graphviz via apt, set up Python 3.12, `pip install -r
build/requirements.txt`, run `pytest`, run the build, upload `_site` with
`actions/upload-pages-artifact`, deploy with `actions/deploy-pages`. Needs
`permissions: { pages: write, id-token: write }`.

Local preview keeps working the same way it does today:

```sh
python build/sitegen.py --out _site && python -m http.server -d _site 8000
```

**Manual step Max must do once:** in the repo's Settings → Pages, change the
source from "Deploy from a branch" to "GitHub Actions". Until that is flipped
the deploy job cannot publish. This cannot be done from the CLI.

## Integration with the existing page

A new `<section id="learning">` in `index.html`, between Teaching and
Publications: a short prose blurb and a button to `/learn/`. Hand-written, with
no generated content, so `index.html` stays a file you can edit by hand. The
skip link and `sitemap.xml` pick up the new section and pages.

## Implementation order

Three phases, each independently useful and independently verifiable:

1. **Pipeline and lesson pages.** Parsing, validation, both renderers, the
   lesson template, CI, and the deploy switch. Ends with real lesson pages
   reachable by URL and a `/learn/` that is just the list.
2. **The graph.** Graphviz layout, SVG emission, `graph.js`, the side panel.
   Ends with the showpiece.
3. **Live cells.** `runner.js`, Pyodide activation, the matplotlib shim, the
   packages allowlist.

Phase 1 must be complete and deployed before phase 2 starts; a graph pointing at
pages that do not exist is not worth debugging.

## Testing

`pytest` over `build/tests/`, run in CI before the build:

- front-matter parsing for both `.md` and notebook raw cells, including a
  notebook whose first cell is not raw
- slug derivation, and prereq resolution across both formats
- each validation rule, asserting the specific error — cycle detection asserts
  the reported cycle path
- the `dot -Tplain` parser against recorded fixture output, including the y-axis
  flip and multi-segment bezier edges
- ancestor and descendant computation on a fixture DAG with a diamond
- golden-file build of a three-lesson fixture set: node `<a>` elements present,
  prerequisite links resolve, KaTeX included only on the lesson with math,
  sitemap contains every lesson
- `node --check` on `graph.js` and `runner.js` as a syntax smoke test

Not covered by automated tests: graph interaction and live-cell execution in a
real browser. Those are verified by hand — select a node and confirm the
ancestor highlight, then activate one runnable lesson and run a cell that draws
a plot. A browser harness is out of proportion to a site this size.

## Decisions made without asking

- **Slug is the filename stem**, with no override field, to avoid two sources of
  truth for URLs.
- **Notebook front-matter lives in a leading raw cell** rather than notebook
  metadata, because it is editable in a plain Jupyter session.
- **KaTeX is vendored**, not loaded from a CDN, to preserve the site's property
  of loading nothing third-party on a normal page view. Pyodide is the one
  exception and only after an explicit click.
- **Both a graph and a list** are always rendered on `/learn/`, from the same
  data. The list is the mobile and no-JS experience rather than a fallback that
  rots.

## Deferred

- **CodeMirror for editable cells.** A styled `<textarea>` ships first: zero
  dependencies, about fifteen lines. If it feels cheap next to the rest of the
  page, swapping in a vendored CodeMirror bundle is a contained change behind
  the same activation step. Not worth the bytes until the textarea has been
  seen in context.
- **Featured lessons on the homepage.** Would need generated content inside
  `index.html`. Revisit once there are enough lessons for the choice to matter.
- **Track filtering on the graph.** Trivial to add once tracks exist and are
  numerous enough to be worth filtering.
