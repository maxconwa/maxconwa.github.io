# maxconwa.github.io

Personal site for Max Conway — https://maxconwa.github.io

The front page is still plain hand-written HTML and CSS. The Learning section at
`/learn/` is generated from the files in `lessons/` by a small Python build, and
GitHub Actions publishes the result.

## Layout

```
index.html              the front page, hand-edited
assets/css/base.css     colour tokens, resets and page furniture, shared by
                        index.html and every generated lesson page
lessons/                lesson sources: one .md or .ipynb per lesson
build/sitegen.py        the generator
build/templates/        page templates
build/static/           learn.css, graph.js, runner.js
build/tests/            pytest suite
```

Nothing generated is committed. `_site/` is build output and is gitignored.

## Editing the front page

Page-specific CSS is in the `<style>` block at the top of `index.html`; the
colour tokens live in `assets/css/base.css` and are shared with lesson pages, so
change them there.

- **Add a project** — copy an `<article class="project">` block inside
  `<section id="research">`. Blocks alternate media left/right automatically, so
  order is all you control.
- **Add a publication** — add an `<li>` to `<ul class="pubs">`, newest first.

## Adding a lesson

Drop a file in `lessons/`. **The filename stem is the slug and the URL**, so
`backprop.ipynb` becomes `/learn/backprop/`; it must be kebab case.

Markdown lessons take YAML front matter at the top of the file. Notebooks take
the same YAML **in a raw cell placed first** — change the first cell's type to
Raw and paste it in. The build strips that cell from the page.

```yaml
---
title: Backpropagation by hand
summary: Deriving the chain rule for an MLP, then implementing it in numpy.
prereqs: [linear-algebra, gradient-descent]
track: Deep learning
runnable: true
packages: [numpy, matplotlib]
updated: 2026-09-17
---
```

`prereqs` are slugs, and they are the edges of the graph — that is the only place
the ordering is declared. `track` groups lessons by colour; there are three
distinguishable slots, and a fourth track folds into a neutral one. `updated` is
optional.

### Lessons that run in the browser

`runnable: true` adds a button that boots Pyodide and turns every code cell into
a live editor. `packages` must then be listed, and is checked against what
Pyodide actually ships — numpy, scipy, matplotlib, pandas, scikit-learn, sympy
and friends.

**PyTorch, MuJoCo and ROS cannot run in the browser.** Leave those lessons
`runnable: false`: they render with their saved outputs and get an "Open in
Colab" button. Marking one runnable is a build error, not a broken page.

Notebook outputs are taken from the saved `.ipynb`, so run a notebook and save it
before committing, or its pages will have no output.

## Building

```sh
python3 -m venv .venv && .venv/bin/pip install -r build/requirements.txt
sudo apt-get install graphviz        # the graph is laid out by `dot`

.venv/bin/python -m pytest build/tests -q
.venv/bin/python build/sitegen.py --out _site
.venv/bin/python -m http.server -d _site 8000    # http://localhost:8000
```

The build fails, and writes nothing, if a prerequisite names a lesson that does
not exist, if the prerequisites contain a cycle, if a runnable lesson declares a
package Pyodide does not have, or if any generated page links to a file that is
not there. It reports every problem at once.

## Deploying

Pushing to `main` runs `.github/workflows/pages.yml`, which tests, builds and
publishes. Feature branches build nothing.

**One-time setup:** the repository's Settings → Pages source must be set to
**GitHub Actions** rather than "Deploy from a branch", or the deploy step has
nowhere to publish.

## Assets

```
assets/cv/max-conway-resume.pdf   redacted copy — no phone number or home address
assets/img/headshot.png
assets/img/favicon-32.png, favicon-180.png   tab icon + iOS home screen
assets/vendor/katex/               vendored KaTeX, loaded only by pages with math
assets/golem/  golem.mp4, poster JPG, og-cover.jpg (social preview)
assets/rapid/  rapid.mp4, + poster JPG
lessons/media/<slug>/              images and video belonging to a lesson
```

Videos are re-encoded to 720p H.264 with `-movflags +faststart` and are lazily
loaded (`preload="none"` plus a poster frame), so the page costs ~400 KB until a
visitor presses play. To add one:

```sh
ffmpeg -i input.mp4 -vf scale=-2:720 -c:v libx264 -crf 26 -preset slow \
       -pix_fmt yuv420p -c:a aac -b:a 96k -movflags +faststart assets/<proj>/<name>.mp4
ffmpeg -ss 10 -i assets/<proj>/<name>.mp4 -frames:v 1 -q:v 3 assets/<proj>/<name>-poster.jpg
```

Keep individual files under 100 MB — GitHub rejects anything larger.
