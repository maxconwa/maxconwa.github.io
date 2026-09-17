"""End-to-end build over a fixture lesson set."""
import json
import re
import textwrap

import nbformat
import pytest

import sitegen as b

STUB_ASSETS = [
    # The breadcrumb on every lesson page links to "/", so the site root has
    # to exist for the link check to pass.
    "index.html",
    "assets/css/base.css",
    "assets/img/favicon-32.png",
    "assets/img/favicon-180.png",
    "assets/vendor/katex/katex.min.css",
    "assets/vendor/katex/katex.min.js",
    "assets/vendor/katex/auto-render.min.js",
]


@pytest.fixture
def site(tmp_path):
    """A root with the shared assets a lesson page links to, and three
    lessons: a root article, a notebook that depends on it, and an article
    with no math."""
    root = tmp_path / "root"
    for asset in STUB_ASSETS:
        path = root / asset
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub")

    lessons = root / "lessons"
    lessons.mkdir()

    (lessons / "alpha.md").write_text(textwrap.dedent("""\
        ---
        title: Alpha
        summary: The first one.
        prereqs: []
        track: Foundations
        ---

        Body with math $e^{i\\pi} = -1$ in it.
        """))

    (lessons / "beta.md").write_text(textwrap.dedent("""\
        ---
        title: Beta
        summary: Depends on alpha, and has no math at all.
        prereqs: [alpha]
        track: Foundations
        ---

        Just prose here.
        """))

    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_raw_cell(textwrap.dedent("""\
            ---
            title: Gamma
            summary: A runnable notebook.
            prereqs: [beta]
            runnable: true
            packages: [numpy]
            ---
            """)),
        nbformat.v4.new_code_cell("print('hi')"),
    ])
    notebook.cells[1].outputs = [
        nbformat.v4.new_output("stream", name="stdout", text="hi\n")
    ]
    nbformat.write(notebook, str(lessons / "gamma.ipynb"))

    out = tmp_path / "out"
    return root, lessons, out


def build(site):
    root, lessons, out = site
    out.mkdir(parents=True, exist_ok=True)
    b.build_site(root, lessons, out)
    return out


def test_builds_a_page_for_every_lesson(site):
    out = build(site)
    for slug in ("alpha", "beta", "gamma"):
        assert (out / "learn" / slug / "index.html").is_file()


def test_graph_page_links_to_every_lesson(site):
    html = (build(site) / "learn" / "index.html").read_text()
    for slug in ("alpha", "beta", "gamma"):
        assert f'href="/learn/{slug}/"' in html


def test_graph_page_draws_a_node_and_an_edge_per_relationship(site):
    html = (build(site) / "learn" / "index.html").read_text()
    assert html.count('class="node"') == 3
    assert 'data-tail="alpha" data-head="beta"' in html
    assert 'data-tail="beta" data-head="gamma"' in html


def test_graph_svg_is_inline_so_it_needs_no_javascript(site):
    html = (build(site) / "learn" / "index.html").read_text()
    assert "<svg" in html
    # The list view must be present in the markup too, not built by JS.
    assert 'id="lesson-list"' in html
    assert "Depends on alpha" in html


def test_embedded_adjacency_matches_the_front_matter(site):
    html = (build(site) / "learn" / "index.html").read_text()
    payload = re.search(
        r'<script type="application/json" id="graph-data">(.*?)</script>',
        html, re.DOTALL).group(1)
    data = json.loads(payload)
    assert data["prereqs"]["gamma"] == ["beta"]
    assert data["unlocks"]["alpha"] == ["beta"]
    assert data["order"].index("alpha") < data["order"].index("gamma")


def test_katex_is_included_only_where_there_is_math(site):
    out = build(site)
    assert "katex.min.css" in (out / "learn" / "alpha" / "index.html").read_text()
    assert "katex.min.css" not in (out / "learn" / "beta" / "index.html").read_text()
    assert "katex.min.css" not in (out / "learn" / "index.html").read_text()


def test_lesson_page_links_to_its_prerequisite(site):
    html = (build(site) / "learn" / "beta" / "index.html").read_text()
    assert 'href="/learn/alpha/"' in html


def test_runnable_lesson_ships_the_runner_and_its_packages(site):
    html = (build(site) / "learn" / "gamma" / "index.html").read_text()
    assert "runner.js" in html
    assert 'data-packages="numpy"' in html


def test_non_runnable_lesson_does_not_ship_the_runner(site):
    html = (build(site) / "learn" / "beta" / "index.html").read_text()
    assert "runner.js" not in html


def test_sitemap_lists_every_lesson(site):
    sitemap = (build(site) / "sitemap.xml").read_text()
    for slug in ("alpha", "beta", "gamma"):
        assert f"<loc>{b.SITE_URL}/learn/{slug}/</loc>" in sitemap
    assert f"<loc>{b.SITE_URL}/learn/</loc>" in sitemap


def test_notebook_saved_output_is_rendered(site):
    html = (build(site) / "learn" / "gamma" / "index.html").read_text()
    assert 'class="out out-stream"' in html
    assert "hi" in html


def test_a_missing_shared_asset_fails_the_build(site):
    """The link check must catch a page pointing at a file that is not there."""
    root, lessons, out = site
    (root / "assets" / "css" / "base.css").unlink()
    out.mkdir(parents=True, exist_ok=True)
    with pytest.raises(SystemExit, match="broken internal links"):
        b.build_site(root, lessons, out)


def test_every_lesson_page_carries_the_ai_disclaimer(site):
    """Disclosure belongs in the template, not in each lesson's prose, so it
    cannot be forgotten on a new lesson."""
    out = build(site)
    for slug in ("alpha", "beta", "gamma"):
        html = (out / "learn" / slug / "index.html").read_text()
        assert "lesson-disclaimer" in html, f"{slug} has no disclaimer"
        assert "AI assistance" in html, f"{slug} disclaimer text missing"


def test_a_deleted_lesson_does_not_survive_in_the_output(site):
    """Rebuilding into an existing output directory must not leave the page
    of a lesson that has since been removed or renamed."""
    root, lessons, out = site
    build(site)
    assert (out / "learn" / "gamma" / "index.html").is_file()

    (lessons / "gamma.ipynb").unlink()
    b.build_site(root, lessons, out)

    assert not (out / "learn" / "gamma").exists()
    assert (out / "learn" / "alpha" / "index.html").is_file()
