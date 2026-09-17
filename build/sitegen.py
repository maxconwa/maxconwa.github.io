"""Generator for the Learning section of maxconwa.github.io.

Reads lessons from ``lessons/``, validates the prerequisite graph, renders
both notebooks and Markdown to static HTML, lays the graph out with graphviz
at build time, and emits the whole site.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import Any

import nbformat
import networkx as nx
import yaml

# Packages Pyodide can supply. A lesson may only declare `runnable: true`
# with packages drawn from this set; torch, mujoco and ROS are absent on
# purpose, so marking such a lesson runnable fails the build rather than
# shipping a page whose Run button cannot work.
PYODIDE_PACKAGES = frozenset({
    "numpy", "scipy", "matplotlib", "pandas", "scikit-learn", "sympy",
    "networkx", "pillow", "statsmodels", "scikit-image", "seaborn",
    "sqlite3", "regex", "pyyaml", "micropip",
})

FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)

# Slugs become graphviz node names, and `dot -Tplain` is whitespace-delimited.
# Restricting them to kebab case keeps the layout parser unambiguous and the
# URLs clean.
SLUG = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def split_front_matter(text: str) -> tuple[dict, str]:
    """Split a leading YAML front-matter block from the body it precedes."""
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[match.end():]


@dataclasses.dataclass
class Lesson:
    slug: str
    fmt: str  # "article" | "notebook"
    source: pathlib.Path | None
    body: str = ""
    title: str | None = None
    summary: str | None = None
    prereqs: list[str] = dataclasses.field(default_factory=list)
    track: str | None = None
    runnable: bool = False
    packages: list[str] | None = None
    updated: str | None = None
    notebook: Any = None

    @property
    def url(self) -> str:
        return f"/learn/{self.slug}/"


def _lesson_from(meta: dict, *, slug, fmt, source, body="", notebook=None) -> Lesson:
    return Lesson(
        slug=slug,
        fmt=fmt,
        source=source,
        body=body,
        notebook=notebook,
        title=meta.get("title"),
        summary=meta.get("summary"),
        prereqs=list(meta.get("prereqs") or []),
        track=meta.get("track"),
        runnable=bool(meta.get("runnable", False)),
        packages=meta.get("packages"),
        updated=str(meta["updated"]) if meta.get("updated") else None,
    )


def parse_lesson(path: pathlib.Path) -> Lesson:
    """Read one lesson file. The slug is always the filename stem."""
    path = pathlib.Path(path)
    slug = path.stem

    if path.suffix == ".ipynb":
        notebook = nbformat.read(str(path), as_version=4)
        meta: dict = {}
        # Front matter lives in a leading raw cell: editable in any Jupyter
        # UI and visible in diffs, unlike notebook metadata.
        if notebook.cells and notebook.cells[0].cell_type == "raw":
            meta, _ = split_front_matter(notebook.cells[0].source)
            if meta:
                notebook.cells = notebook.cells[1:]
        return _lesson_from(meta, slug=slug, fmt="notebook", source=path,
                            notebook=notebook)

    meta, body = split_front_matter(path.read_text())
    return _lesson_from(meta, slug=slug, fmt="article", source=path, body=body)


def validate(lessons: list[Lesson]) -> list[str]:
    """Return every problem with a lesson set, so one build reports them all."""
    errors: list[str] = []

    seen: dict[str, int] = {}
    for lesson in lessons:
        seen[lesson.slug] = seen.get(lesson.slug, 0) + 1
    errors += [f"duplicate slug {slug!r}: two lessons cannot share a filename stem"
               for slug, count in sorted(seen.items()) if count > 1]

    known = set(seen)
    for lesson in lessons:
        where = lesson.slug
        if not SLUG.match(lesson.slug):
            errors.append(
                f"{where!r}: filename must be kebab case (lowercase letters, digits "
                f"and single hyphens), because the slug becomes a graph node name")
        if not lesson.title:
            errors.append(f"{where}: missing required field 'title'")
        if not lesson.summary:
            errors.append(f"{where}: missing required field 'summary'")

        for prereq in lesson.prereqs:
            if prereq not in known:
                errors.append(f"{where}: prereq {prereq!r} matches no lesson")

        if lesson.runnable and lesson.packages is None:
            errors.append(
                f"{where}: runnable lessons must declare 'packages' (use [] for none)")
        if not lesson.runnable and lesson.packages is not None:
            errors.append(
                f"{where}: 'packages' is meaningless without 'runnable: true'")
        for package in lesson.packages or []:
            if package not in PYODIDE_PACKAGES:
                errors.append(
                    f"{where}: package {package!r} is not available in Pyodide, so this "
                    f"lesson cannot be runnable")

    errors += _cycle_errors(lessons, known)
    return errors


def _cycle_errors(lessons: list[Lesson], known: set[str]) -> list[str]:
    graph = nx.DiGraph()
    graph.add_nodes_from(lesson.slug for lesson in lessons)
    for lesson in lessons:
        for prereq in lesson.prereqs:
            if prereq in known:
                graph.add_edge(prereq, lesson.slug)
    return [
        "prereq cycle: " + " -> ".join(list(cycle) + [cycle[0]])
        for cycle in sorted(nx.simple_cycles(graph))
    ]


def build_graph(lessons: list[Lesson]) -> nx.DiGraph:
    """Prerequisite DAG: an edge prereq -> lesson means 'comes before'."""
    graph = nx.DiGraph()
    for lesson in lessons:
        graph.add_node(lesson.slug, lesson=lesson)
    for lesson in lessons:
        for prereq in lesson.prereqs:
            graph.add_edge(prereq, lesson.slug)
    return graph


def all_prereqs(graph: nx.DiGraph, slug: str) -> set[str]:
    """Every lesson that must come before this one, transitively."""
    return nx.ancestors(graph, slug)


def all_unlocks(graph: nx.DiGraph, slug: str) -> set[str]:
    """Every lesson this one is a prerequisite for, transitively."""
    return nx.descendants(graph, slug)


# --------------------------------------------------------------------------
# Layout
#
# graphviz does the layered layout at build time so the browser never has to.
# `dot -Tplain` reports inches with the origin at the bottom-left; SVG wants
# points with the origin at the top-left, hence layout_to_svg.
# --------------------------------------------------------------------------

@dataclasses.dataclass
class NodeBox:
    name: str
    x: float
    y: float
    w: float
    h: float


@dataclasses.dataclass
class Edge:
    tail: str
    head: str
    points: list[tuple[float, float]]


@dataclasses.dataclass
class Layout:
    width: float
    height: float
    nodes: dict[str, NodeBox]
    edges: list[Edge]


def _unquote(name: str) -> str:
    """graphviz quotes any name that is not a bare DOT identifier, which
    includes every kebab-case slug."""
    if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
        return name[1:-1].replace('\\"', '"')
    return name


def parse_dot_plain(text: str) -> Layout:
    """Parse `dot -Tplain` output into node boxes and edge splines."""
    width = height = 0.0
    nodes: dict[str, NodeBox] = {}
    edges: list[Edge] = []

    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind == "stop":
            break
        if kind == "graph":
            width, height = float(parts[2]), float(parts[3])
        elif kind == "node":
            name = _unquote(parts[1])
            x, y, w, h = (float(v) for v in parts[2:6])
            nodes[name] = NodeBox(name, x, y, w, h)
        elif kind == "edge":
            tail, head = _unquote(parts[1]), _unquote(parts[2])
            count = int(parts[3])
            coords = [float(v) for v in parts[4:4 + 2 * count]]
            edges.append(Edge(tail, head, list(zip(coords[0::2], coords[1::2]))))

    return Layout(width, height, nodes, edges)


def layout_to_svg(layout: Layout, scale: float = 72.0) -> Layout:
    """Scale inches to points and flip the y axis for SVG."""
    def flip(x: float, y: float) -> tuple[float, float]:
        return x * scale, (layout.height - y) * scale

    return Layout(
        width=layout.width * scale,
        height=layout.height * scale,
        nodes={
            node.name: NodeBox(node.name, *flip(node.x, node.y),
                               node.w * scale, node.h * scale)
            for node in layout.nodes.values()
        },
        edges=[Edge(e.tail, e.head, [flip(x, y) for x, y in e.points])
               for e in layout.edges],
    )


# --------------------------------------------------------------------------
# Rendering
#
# Notebook cells and Markdown lessons go through the same Markdown renderer
# and the same Pygments highlighter, so one stylesheet covers both and the
# runtime DOM is identical for live cells.
# --------------------------------------------------------------------------

import base64
import html
import json
import shutil
import subprocess

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pygments import highlight as _highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LIGHT_STYLE, DARK_STYLE = "friendly", "native"


def highlight_code(source: str, language: str | None = None) -> str:
    try:
        lexer = get_lexer_by_name(language) if language else guess_lexer(source)
    except (ClassNotFound, ValueError):
        lexer = get_lexer_by_name("text")
    return _highlight(source, lexer, HtmlFormatter(cssclass="highlight"))


def _code_block(source: str, language: str | None) -> str:
    """A fenced block. Python becomes a cell so the runner can find it."""
    rendered = highlight_code(source, language)
    if (language or "").lower() in {"python", "py", "python3"}:
        return ('<div class="cell cell-code"><div class="code">' + rendered
                + '</div><div class="outputs"></div></div>')
    return f'<div class="code">{rendered}</div>'


def _fence(self, tokens, idx, options, env):
    """Replaces the default fence renderer outright: markdown-it only accepts
    highlighter output beginning with `<pre`, and a cell wrapper does not."""
    token = tokens[idx]
    info = token.info.strip() if token.info else ""
    return _code_block(token.content, info.split()[0] if info else None)


def _math_inline(self, tokens, idx, options, env):
    return "\\(" + html.escape(tokens[idx].content) + "\\)"


def _math_block(self, tokens, idx, options, env):
    return "<p>\\[" + html.escape(tokens[idx].content) + "\\]</p>\n"


def _markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"typographer": True})
    md.enable(["table", "strikethrough"])
    # Math is tokenised rather than left as raw text, so Markdown cannot
    # mangle what is inside it. KaTeX picks up the emitted delimiters.
    md.use(dollarmath_plugin)
    md.add_render_rule("math_inline", _math_inline)
    md.add_render_rule("math_block", _math_block)
    md.add_render_rule("fence", _fence)
    return md


MD = _markdown()


def render_markdown(text: str) -> str:
    return MD.render(text)


def contains_math(rendered: str) -> bool:
    return "\\(" in rendered or "\\[" in rendered


def render_notebook(lesson: Lesson, assets_dir: pathlib.Path) -> str:
    """Render notebook cells to the same markup a Markdown lesson produces."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []

    for index, cell in enumerate(lesson.notebook.cells):
        if cell.cell_type == "markdown":
            parts.append(f'<div class="cell cell-md">{render_markdown(cell.source)}</div>')
        elif cell.cell_type == "code":
            outputs = "".join(
                _render_output(output, assets_dir, index, n)
                for n, output in enumerate(cell.get("outputs", []))
            )
            parts.append(
                '<div class="cell cell-code"><div class="code">'
                + highlight_code(cell.source, "python")
                + f'</div><div class="outputs">{outputs}</div></div>'
            )
        # Raw cells carry front matter and nothing else; they are dropped.

    return "\n".join(parts)


def _render_output(output, assets_dir: pathlib.Path, cell: int, n: int) -> str:
    kind = output.get("output_type")

    if kind == "stream":
        text = "".join(output.get("text", ""))
        return f'<pre class="out out-stream">{html.escape(text)}</pre>' if text.strip() else ""

    if kind == "error":
        text = ANSI.sub("", "\n".join(output.get("traceback", [])))
        return f'<pre class="out out-error">{html.escape(text)}</pre>'

    if kind in {"execute_result", "display_data"}:
        data = output.get("data", {})
        # Images are written to files rather than inlined as base64, which
        # keeps the HTML small and lets the browser cache them.
        if "image/png" in data:
            name = f"output-{cell}-{n}.png"
            (assets_dir / name).write_bytes(base64.b64decode(data["image/png"]))
            return (f'<div class="out out-image"><img src="{name}" alt="Output of '
                    f'code cell {cell + 1}" loading="lazy"></div>')
        if "text/html" in data:
            return f'<div class="out out-html">{"".join(data["text/html"])}</div>'
        if "text/plain" in data:
            text = "".join(data["text/plain"])
            return f'<pre class="out out-value">{html.escape(text)}</pre>'

    return ""


def pygments_css() -> str:
    """Highlighting for both colour schemes, with Pygments' own background
    removed so the cell chrome in learn.css shows through."""
    light = HtmlFormatter(style=LIGHT_STYLE).get_style_defs(".highlight")
    dark = HtmlFormatter(style=DARK_STYLE).get_style_defs(".highlight")
    return (
        "\n/* ---------- syntax highlighting (generated) ---------- */\n"
        ".highlight { background:none !important; }\n"
        ".highlight pre { background:none; margin:0; }\n"
        f"{light}\n"
        "@media (prefers-color-scheme: dark) {\n"
        + "\n".join("  " + line for line in dark.splitlines())
        + "\n}\n"
    )


# --------------------------------------------------------------------------
# Graph rendering
# --------------------------------------------------------------------------

SITE_URL = "https://maxconwa.github.io"
REPO = "maxconwa/maxconwa.github.io"
NODE_W_IN, NODE_H_IN = 2.45, 0.86
PAD = 26.0


def track_slots(lessons: list[Lesson]) -> dict[str, int]:
    """Map track names to palette slots.

    Three slots are validated for the all-pairs case (every track is on
    screen at once); a fourth track folds into the neutral slot rather than
    inventing a hue that cannot be told apart.
    """
    names = sorted({lesson.track for lesson in lessons if lesson.track})
    return {name: (index + 1 if index < 3 else 0) for index, name in enumerate(names)}


def run_dot(graph: nx.DiGraph) -> Layout:
    lines = [
        "digraph lessons {",
        "  rankdir=TB;",
        "  nodesep=0.4; ranksep=0.8;",
        f'  node [shape=box, fixedsize=true, width={NODE_W_IN}, height={NODE_H_IN}, label=""];',
    ]
    lines += [f'  "{slug}";' for slug in graph.nodes]
    lines += [f'  "{tail}" -> "{head}";' for tail, head in graph.edges]
    lines.append("}")

    try:
        result = subprocess.run(["dot", "-Tplain"], input="\n".join(lines),
                                capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise SystemExit(
            "graphviz is not installed, so the lesson graph cannot be laid out.\n"
            "  Debian/Ubuntu: sudo apt-get install graphviz\n"
            "  macOS:         brew install graphviz")
    return parse_dot_plain(result.stdout)


def wrap_label(title: str, width: int = 24, max_lines: int = 2) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in title.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines)) < len(title):
        lines[-1] = lines[-1][:width - 1].rstrip() + "…"
    return lines


def _bezier(points: list[tuple[float, float]]) -> str:
    path = [f"M {points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(1, len(points) - 2, 3):
        (x1, y1), (x2, y2), (x3, y3) = points[i:i + 3]
        path.append(f"C {x1:.1f},{y1:.1f} {x2:.1f},{y2:.1f} {x3:.1f},{y3:.1f}")
    return " ".join(path)


def _arrow(points: list[tuple[float, float]], size: float = 8.0) -> str:
    (x0, y0), (x1, y1) = points[-2], points[-1]
    dx, dy = x1 - x0, y1 - y0
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    bx, by = x1 - ux * size, y1 - uy * size
    px, py = -uy * size * 0.42, ux * size * 0.42
    return (f"{x1:.1f},{y1:.1f} {bx + px:.1f},{by + py:.1f} "
            f"{bx - px:.1f},{by - py:.1f}")


def svg_markup(layout: Layout, lessons: dict[str, Lesson], slots: dict[str, int]) -> str:
    out = [
        f'<svg viewBox="{-PAD:.0f} {-PAD:.0f} {layout.width + 2 * PAD:.0f} '
        f'{layout.height + 2 * PAD:.0f}" role="img" '
        f'aria-label="Lesson prerequisite graph. Arrows point from a lesson to the '
        f'lessons it prepares you for. The list below the graph has the same content.">',
        '<g class="edges">',
    ]

    for edge in layout.edges:
        out.append(
            f'<g class="edge-group" data-tail="{edge.tail}" data-head="{edge.head}">'
            f'<path class="edge" d="{_bezier(edge.points)}"/>'
            f'<polygon class="edge-head" points="{_arrow(edge.points)}"/></g>'
        )

    out.append('</g>\n<g class="nodes">')

    for slug, node in sorted(layout.nodes.items()):
        lesson = lessons[slug]
        left, top = node.x - node.w / 2, node.y - node.h / 2
        slot = slots.get(lesson.track, 0)
        title_lines = wrap_label(lesson.title)
        first = top + (20 if len(title_lines) > 1 else 27)

        meta = "Notebook" if lesson.fmt == "notebook" else "Article"
        if lesson.runnable:
            meta += " · runs in browser"

        labels = "".join(
            f'<text class="node-label" x="{left + 16:.1f}" y="{first + i * 15:.1f}">'
            f'{html.escape(line)}</text>'
            for i, line in enumerate(title_lines)
        )
        out.append(
            f'<g class="node" data-slug="{slug}" data-track="{slot}">'
            f'<a href="{lesson.url}">'
            f'<rect class="node-box" x="{left:.1f}" y="{top:.1f}" '
            f'width="{node.w:.1f}" height="{node.h:.1f}" rx="9"/>'
            f'<rect class="node-tab" x="{left + 1.5:.1f}" y="{top + 10:.1f}" '
            f'width="4" height="{node.h - 20:.1f}" rx="2"/>'
            f'{labels}'
            f'<text class="node-meta" x="{left + 16:.1f}" y="{top + node.h - 11:.1f}">'
            f'{html.escape(meta)}</text>'
            f'</a></g>'
        )

    out.append("</g>\n</svg>")
    return "\n".join(out)


def graph_payload(lessons: dict[str, Lesson], graph: nx.DiGraph,
                  slots: dict[str, int]) -> str:
    return json.dumps({
        "nodes": {
            slug: {
                "slug": slug, "title": lesson.title, "summary": lesson.summary,
                "url": lesson.url, "fmt": lesson.fmt, "runnable": lesson.runnable,
                "track": lesson.track, "slot": slots.get(lesson.track, 0),
            }
            for slug, lesson in lessons.items()
        },
        "prereqs": {slug: sorted(graph.predecessors(slug)) for slug in graph.nodes},
        "unlocks": {slug: sorted(graph.successors(slug)) for slug in graph.nodes},
        "order": list(nx.topological_sort(graph)),
    }, separators=(",", ":"))


# --------------------------------------------------------------------------
# Emit
# --------------------------------------------------------------------------

import argparse
import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

HERE = pathlib.Path(__file__).resolve().parent
ROOT_FILES = ["index.html", "404.html", "robots.txt", ".nojekyll"]
INTRO = ("Lessons I have written for the courses I teach and the topics I work in. "
         "Arrows run from a lesson to the ones it prepares you for, so you can start "
         "anywhere and see exactly what it assumes.")


def _script_safe(payload: str) -> str:
    """JSON destined for a <script> block. Escaping `<` keeps a title
    containing `</script>` from ending the element early."""
    return payload.replace("<", "\\u003c")


def _jsonld(lesson: Lesson, prereqs: list[Lesson]) -> str:
    return _script_safe(json.dumps({
        "@context": "https://schema.org",
        "@type": "LearningResource",
        "name": lesson.title,
        "description": lesson.summary,
        "url": f"{SITE_URL}{lesson.url}",
        "inLanguage": "en",
        "learningResourceType": "Lesson",
        "isAccessibleForFree": True,
        "author": {"@type": "Person", "name": "Max Conway", "url": f"{SITE_URL}/"},
        "isPartOf": {"@type": "Collection", "name": "Learning",
                     "url": f"{SITE_URL}/learn/"},
        **({"competencyRequired": [p.title for p in prereqs]} if prereqs else {}),
    }, indent=2))


def discover(lessons_dir: pathlib.Path) -> list[Lesson]:
    paths = sorted(
        [p for p in lessons_dir.glob("*.md")] + [p for p in lessons_dir.glob("*.ipynb")],
        key=lambda p: p.stem,
    )
    return [parse_lesson(path) for path in paths]


def build_site(root: pathlib.Path, lessons_dir: pathlib.Path,
               out_dir: pathlib.Path) -> int:
    lessons = discover(lessons_dir)
    if not lessons:
        raise SystemExit(f"no lessons found in {lessons_dir}")

    errors = validate(lessons)
    if errors:
        raise SystemExit("\n".join(
            [f"{len(errors)} problem(s) found; nothing was written:"]
            + [f"  - {error}" for error in errors]))

    by_slug = {lesson.slug: lesson for lesson in lessons}
    slots = track_slots(lessons)
    graph = build_graph(lessons)
    layout = layout_to_svg(run_dot(graph))

    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        trim_blocks=True, lstrip_blocks=False,
    )

    learn = out_dir / "learn"
    learn.mkdir(parents=True, exist_ok=True)

    for lesson in lessons:
        destination = learn / lesson.slug
        destination.mkdir(parents=True, exist_ok=True)
        body = (render_notebook(lesson, destination) if lesson.fmt == "notebook"
                else render_markdown(lesson.body))
        prereqs = [by_slug[slug] for slug in lesson.prereqs]

        (destination / "index.html").write_text(env.get_template("lesson.html.j2").render(
            lesson=lesson,
            body=Markup(body),
            has_math=contains_math(body),
            prereqs=prereqs,
            unlocks=[by_slug[s] for s in sorted(graph.successors(lesson.slug))],
            track_slot=slots.get(lesson.track, 0),
            jsonld=Markup(_jsonld(lesson, prereqs)),
            colab_url=f"https://colab.research.google.com/github/{REPO}/blob/main/lessons/{lesson.slug}.ipynb",
            source_url=f"https://github.com/{REPO}/blob/main/lessons/{lesson.slug}.md",
            page_title=f"{lesson.title} — Max Conway",
            og_title=lesson.title,
            description=lesson.summary,
            path=lesson.url,
            site_url=SITE_URL,
            og_type="article",
        ))

    (learn / "index.html").write_text(env.get_template("graph.html.j2").render(
        svg=Markup(svg_markup(layout, by_slug, slots)),
        graph_json=Markup(_script_safe(graph_payload(by_slug, graph, slots))),
        rows=[by_slug[slug] for slug in nx.topological_sort(graph)],
        tracks=sorted(slots.items(), key=lambda item: item[1]),
        intro=INTRO,
        has_math=False,
        page_title="Learning — Max Conway",
        og_title="Learning — Max Conway",
        description="Lessons on robotics, planning and machine learning, "
                    "arranged by what each one assumes you already know.",
        path="/learn/",
        site_url=SITE_URL,
        og_type="website",
    ))

    # Static assets. Pygments styles are appended to the hand-written
    # stylesheet so a lesson page still loads exactly one CSS file of our own.
    static = learn / "static"
    if static.exists():
        shutil.rmtree(static)
    shutil.copytree(HERE / "static", static)
    with (static / "learn.css").open("a") as handle:
        handle.write(pygments_css())

    media = lessons_dir / "media"
    if media.is_dir():
        shutil.copytree(media, learn / "media", dirs_exist_ok=True)

    for name in ROOT_FILES:
        source = root / name
        if source.exists():
            shutil.copy2(source, out_dir / name)
    if (root / "assets").is_dir():
        shutil.copytree(root / "assets", out_dir / "assets", dirs_exist_ok=True)

    _write_sitemap(out_dir, lessons)
    _check_links(out_dir)
    return len(lessons)


def _write_sitemap(out_dir: pathlib.Path, lessons: list[Lesson]) -> None:
    today = datetime.date.today().isoformat()
    entries = [("/", "monthly", today), ("/learn/", "weekly", today)]
    entries += [(lesson.url, "monthly", lesson.updated or today) for lesson in lessons]
    body = "\n".join(
        f"  <url>\n    <loc>{SITE_URL}{path}</loc>\n"
        f"    <lastmod>{modified}</lastmod>\n"
        f"    <changefreq>{frequency}</changefreq>\n  </url>"
        for path, frequency, modified in entries
    )
    (out_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n")


LOCAL_HREF = re.compile(r'(?:href|src)="(/[^"#?]*)"')


def _check_links(out_dir: pathlib.Path) -> None:
    """Every root-relative link in the output must resolve to a real file."""
    missing: set[str] = set()
    for page in out_dir.rglob("*.html"):
        for href in LOCAL_HREF.findall(page.read_text()):
            target = out_dir / href.lstrip("/")
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                missing.add(f"{page.relative_to(out_dir)} -> {href}")
    if missing:
        raise SystemExit("\n".join(
            ["broken internal links:"] + [f"  - {m}" for m in sorted(missing)]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build maxconwa.github.io")
    parser.add_argument("--out", default="_site", type=pathlib.Path)
    parser.add_argument("--root", default=HERE.parent, type=pathlib.Path)
    parser.add_argument("--lessons", default=None, type=pathlib.Path)
    args = parser.parse_args()

    root = args.root.resolve()
    lessons_dir = (args.lessons or root / "lessons").resolve()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    count = build_site(root, lessons_dir, out_dir)
    print(f"built {count} lesson(s) into {out_dir}")


if __name__ == "__main__":
    main()
