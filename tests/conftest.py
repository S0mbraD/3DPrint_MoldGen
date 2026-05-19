"""Shared test fixtures for MoldGen test suite."""

import numpy as np
import pytest
import trimesh


@pytest.fixture
def unit_cube() -> trimesh.Trimesh:
    """1×1×1 box centered at origin."""
    return trimesh.creation.box(extents=[1, 1, 1])


@pytest.fixture
def unit_sphere() -> trimesh.Trimesh:
    """Sphere of radius 1, centered at origin."""
    return trimesh.creation.icosphere(subdivisions=2, radius=1.0)


@pytest.fixture
def small_cylinder() -> trimesh.Trimesh:
    """Cylinder r=0.5, h=2 along Z, centered at origin."""
    return trimesh.creation.cylinder(radius=0.5, height=2.0, sections=16)


@pytest.fixture
def large_box() -> trimesh.Trimesh:
    """10×10×10 box — used as an outer shell for boolean tests."""
    return trimesh.creation.box(extents=[10, 10, 10])


@pytest.fixture
def sample_model() -> trimesh.Trimesh:
    """A small watertight model suitable for mold generation tests."""
    return trimesh.creation.icosphere(subdivisions=3, radius=15.0)
