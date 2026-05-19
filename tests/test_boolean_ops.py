"""Tests for moldgen.core.boolean_ops — unified boolean operations."""

import numpy as np
import pytest
import trimesh

from moldgen.core.boolean_ops import (
    boolean_subtract,
    boolean_union,
    boolean_intersect,
    batch_subtract,
)


class TestBooleanSubtract:
    def test_subtract_cube_from_large_box(self, large_box, unit_cube):
        result = boolean_subtract(large_box, unit_cube)
        assert result is not None
        assert len(result.faces) > 10
        assert result.volume < large_box.volume

    def test_subtract_returns_none_for_disjoint(self):
        a = trimesh.creation.box(extents=[1, 1, 1])
        b = trimesh.creation.box(extents=[1, 1, 1])
        b.apply_translation([100, 100, 100])
        result = boolean_subtract(a, b)
        if result is not None:
            assert abs(result.volume - a.volume) < 0.1

    def test_subtract_min_faces(self, large_box, unit_cube):
        result = boolean_subtract(large_box, unit_cube, min_faces=10)
        assert result is not None
        assert len(result.faces) > 10


class TestBooleanUnion:
    def test_union_two_cubes(self, unit_cube):
        other = unit_cube.copy()
        other.apply_translation([0.5, 0, 0])
        result = boolean_union(unit_cube, other)
        assert result is not None
        assert len(result.faces) > 10
        assert result.volume > unit_cube.volume

    def test_union_require_watertight(self, unit_cube):
        other = unit_cube.copy()
        other.apply_translation([0.5, 0, 0])
        result = boolean_union(unit_cube, other, require_watertight=True)
        if result is not None:
            assert result.is_watertight


class TestBooleanIntersect:
    def test_intersect_overlapping_cubes(self, unit_cube):
        other = unit_cube.copy()
        other.apply_translation([0.5, 0, 0])
        result = boolean_intersect(unit_cube, other)
        assert result is not None
        assert result.volume < unit_cube.volume


class TestBatchSubtract:
    def test_batch_subtract_multiple_holes(self, large_box):
        cutters = [
            trimesh.creation.cylinder(radius=0.5, height=20, sections=8)
            for _ in range(3)
        ]
        cutters[0].apply_translation([2, 0, 0])
        cutters[1].apply_translation([-2, 0, 0])
        cutters[2].apply_translation([0, 2, 0])
        result = batch_subtract(large_box, cutters)
        assert result is not None
        assert result.volume < large_box.volume

    def test_batch_subtract_empty_cutters(self, large_box):
        result = batch_subtract(large_box, [])
        assert result is large_box
