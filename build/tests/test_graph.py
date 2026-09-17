"""Graphviz layout parsing and prerequisite traversal."""
import pytest

import sitegen as b

# Recorded `dot -Tplain` output for a diamond: a->c, b->c, c->d.
# Coordinates are inches with the origin bottom-left.
PLAIN = """\
graph 1 3.4444 2.5
node a 0.79861 2.25 1.5972 0.5 a solid box black lightgrey
node c 1.7153 1.25 1.5972 0.5 c solid box black lightgrey
node b 2.6458 2.25 1.5972 0.5 b solid box black lightgrey
node d 1.7153 0.25 1.5972 0.5 d solid box black lightgrey
edge a c 4 1.0252 1.9958 1.1362 1.8781 1.2718 1.7342 1.3934 1.6053 solid black
edge c d 4 1.7153 0.99579 1.7153 0.88865 1.7153 0.7599 1.7153 0.64045 solid black
edge b c 4 2.4158 1.9958 2.3031 1.8781 2.1654 1.7342 2.0421 1.6053 solid black
stop
"""


def test_parses_graph_dimensions():
    layout = b.parse_dot_plain(PLAIN)
    assert layout.width == pytest.approx(3.4444)
    assert layout.height == pytest.approx(2.5)


def test_parses_node_positions_and_sizes():
    layout = b.parse_dot_plain(PLAIN)
    assert set(layout.nodes) == {"a", "b", "c", "d"}
    node = layout.nodes["a"]
    assert (node.x, node.y) == pytest.approx((0.79861, 2.25))
    assert (node.w, node.h) == pytest.approx((1.5972, 0.5))


def test_parses_every_edge_with_its_bezier_control_points():
    layout = b.parse_dot_plain(PLAIN)
    assert {(e.tail, e.head) for e in layout.edges} == {("a", "c"), ("b", "c"), ("c", "d")}
    edge = next(e for e in layout.edges if (e.tail, e.head) == ("c", "d"))
    assert len(edge.points) == 4
    assert edge.points[0] == pytest.approx((1.7153, 0.99579))
    assert edge.points[-1] == pytest.approx((1.7153, 0.64045))


def test_ignores_the_trailing_stop_line():
    assert "stop" not in b.parse_dot_plain(PLAIN).nodes


def test_svg_conversion_scales_inches_to_points():
    svg = b.layout_to_svg(b.parse_dot_plain(PLAIN), scale=72)
    assert svg.width == pytest.approx(3.4444 * 72)
    assert svg.nodes["a"].x == pytest.approx(0.79861 * 72)


def test_svg_conversion_flips_the_y_axis():
    """graphviz is y-up, SVG is y-down: the top row must end up near y=0."""
    svg = b.layout_to_svg(b.parse_dot_plain(PLAIN), scale=72)
    assert svg.nodes["a"].y == pytest.approx((2.5 - 2.25) * 72)
    assert svg.nodes["d"].y == pytest.approx((2.5 - 0.25) * 72)
    assert svg.nodes["a"].y < svg.nodes["d"].y  # 'a' is a prereq, so it sits above


def test_svg_conversion_flips_edge_points_too():
    svg = b.layout_to_svg(b.parse_dot_plain(PLAIN), scale=72)
    edge = next(e for e in svg.edges if (e.tail, e.head) == ("c", "d"))
    assert edge.points[0][1] == pytest.approx((2.5 - 0.99579) * 72)


# ---------- traversal ----------

def diamond():
    return b.build_graph([
        b.Lesson(slug="a", fmt="article", source=None),
        b.Lesson(slug="b", fmt="article", source=None, prereqs=["a"]),
        b.Lesson(slug="c", fmt="article", source=None, prereqs=["a"]),
        b.Lesson(slug="d", fmt="article", source=None, prereqs=["b", "c"]),
    ])


def test_all_prereqs_is_transitive():
    assert b.all_prereqs(diamond(), "d") == {"a", "b", "c"}


def test_a_root_lesson_has_no_prereqs():
    assert b.all_prereqs(diamond(), "a") == set()


def test_all_unlocks_is_transitive():
    assert b.all_unlocks(diamond(), "a") == {"b", "c", "d"}


def test_a_leaf_lesson_unlocks_nothing():
    assert b.all_unlocks(diamond(), "d") == set()


# graphviz quotes any node name that is not a bare DOT identifier. Every
# lesson slug is kebab-case, so quoted names are the normal case here, not
# the exception.
QUOTED = """\
graph 1 1.5 1.5
node "linear-algebra" 0.75 1.25 1.5 0.5 "" solid box black lightgrey
node "gradient-descent" 0.75 0.25 1.5 0.5 "" solid box black lightgrey
edge "linear-algebra" "gradient-descent" 4 0.75 0.99579 0.75 0.88865 0.75 0.7599 0.75 0.64045 solid black
stop
"""


def test_node_names_are_unquoted():
    assert set(b.parse_dot_plain(QUOTED).nodes) == {"linear-algebra", "gradient-descent"}


def test_edge_endpoints_are_unquoted():
    edge = b.parse_dot_plain(QUOTED).edges[0]
    assert (edge.tail, edge.head) == ("linear-algebra", "gradient-descent")
