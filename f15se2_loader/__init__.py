"""Python helpers for inspecting the F-15 Strike Eagle 2 3D asset formats."""

from .loader import (
    ThreeD3Model,
    ThreeDGGrid,
    ThreeDTerrain,
    TerrainTile,
    TileEntry,
    load_3d3,
    load_3dg,
    load_3dt,
    load_scene,
)

__all__ = [
    "ThreeD3Model",
    "ThreeDGGrid",
    "ThreeDTerrain",
    "TerrainTile",
    "TileEntry",
    "load_3d3",
    "load_3dg",
    "load_3dt",
    "load_scene",
]
