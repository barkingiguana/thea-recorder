import pytest

from thea.layout import Region, validate_regions, generate_testcard


class TestRegion:
    def test_basic_properties(self):
        r = Region("app", 0, 0, 1920, 1080, kind="app")
        assert r.name == "app"
        assert r.x == 0
        assert r.y == 0
        assert r.width == 1920
        assert r.height == 1080
        assert r.kind == "app"

    def test_right_and_bottom(self):
        r = Region("box", 100, 200, 300, 400)
        assert r.right() == 400
        assert r.bottom() == 600

    def test_to_dict(self):
        r = Region("test", 10, 20, 100, 50, kind="panel")
        d = r.to_dict()
        assert d == {
            "name": "test",
            "x": 10,
            "y": 20,
            "width": 100,
            "height": 50,
            "kind": "panel",
        }

    def test_repr(self):
        r = Region("a", 1, 2, 3, 4, kind="app")
        assert "a" in repr(r)
        assert "app" in repr(r)

    def test_default_kind_is_panel(self):
        r = Region("x", 0, 0, 10, 10)
        assert r.kind == "panel"


class TestOverlaps:
    def test_non_overlapping_side_by_side(self):
        a = Region("left", 0, 0, 100, 100)
        b = Region("right", 100, 0, 100, 100)
        assert not a.overlaps(b)
        assert not b.overlaps(a)

    def test_non_overlapping_stacked(self):
        a = Region("top", 0, 0, 100, 100)
        b = Region("bottom", 0, 100, 100, 100)
        assert not a.overlaps(b)

    def test_overlapping(self):
        a = Region("a", 0, 0, 100, 100)
        b = Region("b", 50, 50, 100, 100)
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_fully_contained(self):
        outer = Region("outer", 0, 0, 200, 200)
        inner = Region("inner", 50, 50, 50, 50)
        assert outer.overlaps(inner)
        assert inner.overlaps(outer)

    def test_zero_width_no_overlap(self):
        a = Region("a", 0, 0, 0, 100)
        b = Region("b", 0, 0, 100, 100)
        assert not a.overlaps(b)

    def test_zero_height_no_overlap(self):
        a = Region("a", 0, 0, 100, 0)
        b = Region("b", 0, 0, 100, 100)
        assert not a.overlaps(b)

    def test_touching_edges_no_overlap(self):
        a = Region("a", 0, 0, 100, 100)
        b = Region("b", 100, 0, 100, 100)
        assert not a.overlaps(b)

    def test_one_pixel_overlap(self):
        a = Region("a", 0, 0, 100, 100)
        b = Region("b", 99, 99, 100, 100)
        assert a.overlaps(b)


class TestValidateRegions:
    def test_valid_layout(self):
        regions = [
            Region("viewport", 0, 0, 1920, 1080, kind="app"),
            Region("status", 0, 1080, 120, 300, kind="panel"),
            Region("log", 120, 1080, 1800, 300, kind="panel"),
        ]
        warnings = validate_regions(1920, 1380, regions)
        assert warnings == []

    def test_region_beyond_width(self):
        regions = [Region("wide", 1800, 0, 200, 100)]
        warnings = validate_regions(1920, 1080, regions)
        assert any("beyond canvas width" in w for w in warnings)

    def test_region_beyond_height(self):
        regions = [Region("tall", 0, 1000, 100, 200)]
        warnings = validate_regions(1920, 1080, regions)
        assert any("beyond canvas height" in w for w in warnings)

    def test_negative_coordinates(self):
        regions = [Region("neg", -10, 0, 100, 100)]
        warnings = validate_regions(1920, 1080, regions)
        assert any("negative coordinates" in w for w in warnings)

    def test_non_positive_dimensions(self):
        regions = [Region("zero", 0, 0, 0, 100)]
        warnings = validate_regions(1920, 1080, regions)
        assert any("non-positive dimensions" in w for w in warnings)

    def test_overlapping_regions(self):
        regions = [
            Region("a", 0, 0, 200, 200),
            Region("b", 100, 100, 200, 200),
        ]
        warnings = validate_regions(1920, 1080, regions)
        assert any("overlap" in w for w in warnings)

    def test_no_regions(self):
        warnings = validate_regions(1920, 1080, [])
        assert warnings == []

    def test_multiple_warnings(self):
        regions = [
            Region("neg", -5, -5, 100, 100),
            Region("wide", 1900, 0, 100, 100),
        ]
        warnings = validate_regions(1920, 1080, regions)
        assert len(warnings) >= 2

    def test_exact_fit_no_warnings(self):
        regions = [
            Region("left", 0, 0, 960, 1080),
            Region("right", 960, 0, 960, 1080),
        ]
        warnings = validate_regions(1920, 1080, regions)
        assert warnings == []


class TestGenerateTestcard:
    def test_returns_svg_string(self):
        regions = [Region("viewport", 0, 0, 1920, 1080, kind="app")]
        svg = generate_testcard(1920, 1080, regions)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_region_name(self):
        regions = [Region("my_panel", 0, 0, 100, 100)]
        svg = generate_testcard(1920, 1080, regions)
        assert "my_panel" in svg

    def test_contains_canvas_dimensions(self):
        svg = generate_testcard(1920, 1080, [])
        assert "1920" in svg
        assert "1080" in svg

    def test_with_warnings(self):
        regions = [Region("bad", -10, 0, 100, 100)]
        warnings = ["Something is wrong"]
        svg = generate_testcard(1920, 1080, regions, warnings=warnings)
        assert "Something is wrong" in svg
        assert "Warnings" in svg

    def test_without_warnings(self):
        regions = [Region("ok", 0, 0, 100, 100)]
        svg = generate_testcard(1920, 1080, regions, warnings=None)
        assert "Warnings" not in svg

    def test_html_escapes_region_names(self):
        regions = [Region("<script>", 0, 0, 100, 100)]
        svg = generate_testcard(1920, 1080, regions)
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_multiple_regions(self):
        regions = [
            Region("viewport", 0, 0, 1920, 1080, kind="app"),
            Region("status", 0, 1080, 120, 300, kind="panel"),
            Region("log", 120, 1080, 1800, 300, kind="panel"),
        ]
        svg = generate_testcard(1920, 1380, regions)
        assert "viewport" in svg
        assert "status" in svg
        assert "log" in svg

    def test_empty_canvas(self):
        svg = generate_testcard(0, 0, [])
        assert "<svg" in svg
