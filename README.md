# maxconwa.github.io

Personal site for Max Conway — https://maxconwa.github.io

Plain HTML and CSS. No build step, no dependencies, no JavaScript.
GitHub Pages serves `index.html` from the root of `main`.

## Editing

Everything lives in `index.html`; the CSS is in the `<style>` block at the top.

- **Add a project** — copy an `<article class="project">` block inside
  `<section id="research">`. Blocks alternate media left/right automatically, so
  order is all you control.
- **Add a publication** — add an `<li>` to `<ul class="pubs">`, newest first.
- **Colors** — the CSS custom properties under `:root` (and the
  `prefers-color-scheme: dark` block below it) define the whole palette.

## Assets

```
assets/cv/max-conway-resume.pdf   redacted copy — no phone number or home address
assets/img/headshot.png
assets/img/favicon-32.png, favicon-180.png   tab icon + iOS home screen
assets/golem/  golem.mp4, golem-clip.mp4, + poster JPGs
assets/rapid/  rapid.mp4, + poster JPG
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

## Local preview

```sh
python3 -m http.server 8000   # then open http://localhost:8000
```
