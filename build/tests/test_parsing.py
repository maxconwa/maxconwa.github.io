"""Front-matter parsing and lesson validation."""
import textwrap

import nbformat
import pytest

import sitegen as b


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text).lstrip())
    return p


def notebook(tmp_path, name, cells):
    nb = nbformat.v4.new_notebook(cells=cells)
    p = tmp_path / name
    nbformat.write(nb, str(p))
    return p


FRONT_MATTER = """\
---
title: Backpropagation by hand
summary: Deriving the chain rule for an MLP.
prereqs: [linear-algebra]
---
"""


# ---------- front matter ----------

def test_splits_yaml_front_matter_from_markdown_body(tmp_path):
    path = write(tmp_path, "backprop.md", FRONT_MATTER + "\nThe body starts here.\n")
    meta, body = b.split_front_matter(path.read_text())
    assert meta["title"] == "Backpropagation by hand"
    assert meta["prereqs"] == ["linear-algebra"]
    assert body.strip() == "The body starts here."


def test_markdown_without_front_matter_yields_empty_metadata(tmp_path):
    path = write(tmp_path, "bare.md", "Just prose, no header.\n")
    meta, body = b.split_front_matter(path.read_text())
    assert meta == {}
    assert body.strip() == "Just prose, no header."


def test_reads_front_matter_from_leading_raw_cell_of_notebook(tmp_path):
    path = notebook(tmp_path, "backprop.ipynb", [
        nbformat.v4.new_raw_cell(FRONT_MATTER),
        nbformat.v4.new_code_cell("import numpy as np"),
    ])
    lesson = b.parse_lesson(path)
    assert lesson.title == "Backpropagation by hand"
    assert lesson.prereqs == ["linear-algebra"]


def test_front_matter_raw_cell_is_stripped_from_notebook_body(tmp_path):
    path = notebook(tmp_path, "backprop.ipynb", [
        nbformat.v4.new_raw_cell(FRONT_MATTER),
        nbformat.v4.new_code_cell("import numpy as np"),
    ])
    lesson = b.parse_lesson(path)
    assert len(lesson.notebook.cells) == 1
    assert lesson.notebook.cells[0].cell_type == "code"


def test_notebook_whose_first_cell_is_not_raw_yields_no_front_matter(tmp_path):
    path = notebook(tmp_path, "nometa.ipynb", [
        nbformat.v4.new_markdown_cell("# A heading, not front matter"),
    ])
    lesson = b.parse_lesson(path)
    assert lesson.title is None


def test_slug_comes_from_filename_stem(tmp_path):
    path = write(tmp_path, "gradient-descent.md", FRONT_MATTER)
    assert b.parse_lesson(path).slug == "gradient-descent"


def test_format_distinguishes_notebooks_from_articles(tmp_path):
    md = write(tmp_path, "a.md", FRONT_MATTER)
    nb = notebook(tmp_path, "b.ipynb", [nbformat.v4.new_raw_cell(FRONT_MATTER)])
    assert b.parse_lesson(md).fmt == "article"
    assert b.parse_lesson(nb).fmt == "notebook"


# ---------- validation ----------

def lesson(slug, **kw):
    kw.setdefault("title", "T")
    kw.setdefault("summary", "S")
    kw.setdefault("prereqs", [])
    return b.Lesson(slug=slug, fmt="article", source=None, body="", **kw)


def test_valid_lesson_set_produces_no_errors():
    assert b.validate([lesson("a"), lesson("b", prereqs=["a"])]) == []


def test_duplicate_slug_is_rejected():
    errors = b.validate([lesson("a"), lesson("a")])
    assert any("duplicate" in e.lower() and "a" in e for e in errors)


def test_prereq_naming_an_unknown_lesson_is_rejected():
    errors = b.validate([lesson("a", prereqs=["ghost"])])
    assert any("ghost" in e for e in errors)


def test_cycle_is_rejected_and_names_the_cycle():
    errors = b.validate([
        lesson("a", prereqs=["c"]),
        lesson("b", prereqs=["a"]),
        lesson("c", prereqs=["b"]),
    ])
    assert any("cycle" in e.lower() for e in errors)
    cycle_error = next(e for e in errors if "cycle" in e.lower())
    assert all(slug in cycle_error for slug in ("a", "b", "c"))


def test_missing_title_is_rejected():
    assert any("title" in e for e in b.validate([lesson("a", title=None)]))


def test_missing_summary_is_rejected():
    assert any("summary" in e for e in b.validate([lesson("a", summary=None)]))


def test_runnable_lesson_without_packages_is_rejected():
    errors = b.validate([lesson("a", runnable=True, packages=None)])
    assert any("packages" in e for e in errors)


def test_packages_on_a_non_runnable_lesson_is_rejected():
    errors = b.validate([lesson("a", runnable=False, packages=["numpy"])])
    assert any("packages" in e for e in errors)


def test_package_outside_the_pyodide_allowlist_is_rejected():
    errors = b.validate([lesson("a", runnable=True, packages=["torch"])])
    assert any("torch" in e for e in errors)


def test_runnable_lesson_with_allowed_packages_is_accepted():
    assert b.validate([lesson("a", runnable=True, packages=["numpy", "matplotlib"])]) == []


def test_runnable_lesson_may_declare_an_empty_package_list():
    assert b.validate([lesson("a", runnable=True, packages=[])]) == []


def test_validation_reports_every_error_not_just_the_first():
    errors = b.validate([
        lesson("a", title=None),
        lesson("b", summary=None),
        lesson("c", prereqs=["ghost"]),
    ])
    assert len(errors) >= 3


# Slugs become graphviz node names in `dot -Tplain` output, which is
# whitespace-delimited. A filename with a space would silently corrupt layout.

def test_slug_containing_a_space_is_rejected():
    assert any("two words" in e for e in b.validate([lesson("two words")]))


def test_slug_containing_uppercase_is_rejected():
    assert any("GradientDescent" in e for e in b.validate([lesson("GradientDescent")]))


def test_conventional_kebab_case_slug_is_accepted():
    assert b.validate([lesson("gradient-descent-2")]) == []


# A summary like "momentum: why it works" is natural to write and is invalid
# unquoted YAML. The build must say so rather than surface a parser traceback.

def test_unparseable_front_matter_names_the_file_and_suggests_quoting(tmp_path):
    path = write(tmp_path, "adam.md", """
        ---
        title: Adam
        summary: Momentum: why everything is trained with this.
        ---

        Body.
        """)
    with pytest.raises(SystemExit) as raised:
        b.parse_lesson(path)
    message = str(raised.value)
    assert "adam.md" in message
    assert "quote" in message.lower()
