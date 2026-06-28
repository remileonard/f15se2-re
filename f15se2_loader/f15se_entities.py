from typing import Optional, Union
from dataclasses import dataclass, field
from pathlib import Path
from f15se_helpers import _is_printable, aircraft_name
from f15se_constant import (
    _UNIT_TYPE_LABELS
)
PathLike = Union[str, Path]

@dataclass
class TileEntry:
    x: int
    y: int
    z: int
    shape: int


@dataclass
class TerrainTile:
    object_count: int
    objects: list[TileEntry] = field(default_factory=list)


@dataclass
class ThreeDTerrain:
    path: Path
    signature: int
    lod_sizes: list[int] = field(default_factory=list)
    tile_counts: list[list[int]] = field(default_factory=list)
    lod: list[list[TerrainTile]] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        tile_count = sum(len(category) for category in self.lod)
        object_count = sum(sum(tile.object_count for tile in category) for category in self.lod)
        return {
            "path": str(self.path),
            "signature": self.signature,
            "lod_sizes": self.lod_sizes,
            "tile_counts": self.tile_counts,
            "category_count": len(self.lod),
            "tile_count": tile_count,
            "object_count": object_count,
        }

    def describe(self) -> str:
        summary = self.summary()
        lines = [
            "3DT terrain",
            f"  path: {summary['path']}",
            f"  signature: 0x{summary['signature']:04x}",
            f"  lod_sizes: {summary['lod_sizes']}",
            f"  lod: {summary['category_count']}",
            f"  tiles: {summary['tile_count']}",
            f"  objects: {summary['object_count']}",
        ]
        for category_idx, category in enumerate(self.lod):
            lines.append(f"  category {category_idx}: {len(category)} tiles")
            for tile_idx, tile in enumerate(category):
                lines.append(
                    f"    tile {tile_idx}: {tile.object_count} objects"
                )
                for object_idx, obj in enumerate(tile.objects):
                    lines.append(
                        f"      object {object_idx}: x={obj.x}, y={obj.y}, z={obj.z}, shape=0x{obj.shape:02x}"
                    )
        return "\n".join(lines)


@dataclass
class ThreeD3Model:
    path: Path
    signature: int
    header_words: list[int] = field(default_factory=list)
    object_data: bytes = b""
    extra_bytes_a: bytes = b""
    extra_bytes_b: bytes = b""
    extra_bytes_c: bytes = b""
    vertex_x: list[int] = field(default_factory=list)
    vertex_y: list[int] = field(default_factory=list)
    vertex_z: list[int] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "signature": self.signature,
            "header_words": self.header_words,
            "object_bytes": len(self.object_data),
            "extra_bytes_a": len(self.extra_bytes_a),
            "extra_bytes_b": len(self.extra_bytes_b),
            "extra_bytes_c": len(self.extra_bytes_c),
            "vertex_count_x": len(self.vertex_x),
            "vertex_count_y": len(self.vertex_y),
            "vertex_count_z": len(self.vertex_z),
        }

    def describe(self) -> str:
        summary = self.summary()
        return "\n".join(
            [
                "3D3 model",
                f"  path: {summary['path']}",
                f"  signature: 0x{summary['signature']:04x}",
                f"  header_words: {summary['header_words']}",
                f"  object_bytes: {summary['object_bytes']}",
                f"  extra_bytes: {summary['extra_bytes_a']}/{summary['extra_bytes_b']}/{summary['extra_bytes_c']}",
                f"  vertex_tables: {summary['vertex_count_x']}/{summary['vertex_count_y']}/{summary['vertex_count_z']}",
            ]
        )


@dataclass
class ThreeDGGrid:
    path: Path
    signature: int
    header: bytes = b""
    layer1: bytes = b""
    layer2: bytes = b""
    layer3: bytes = b""
    layer4: bytes = b""
    # 8×8 top-LOD (LOD 4) grid, not stored in the 3DG file but copied from the
    # theater table g_theaterGrids; populated by the viewer before rendering.
    top_grid: bytes = b""

    def summary(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "signature": self.signature,
            "header_bytes": len(self.header),
            "layer1_bytes": len(self.layer1),
            "layer2_bytes": len(self.layer2),
            "layer3_bytes": len(self.layer3),
            "layer4_bytes": len(self.layer4),
        }

    def describe(self) -> str:
        summary = self.summary()
        preview = self.render_preview()
        return "\n".join(
            [
                "3DG grid",
                f"  path: {summary['path']}",
                f"  signature: 0x{summary['signature']:04x}",
                f"  section_sizes: {summary['header_bytes']}/{summary['layer1_bytes']}/{summary['layer2_bytes']}/{summary['layer3_bytes']}/{summary['layer4_bytes']}",
                f"  preview:\n{preview}",
            ]
        )

    def render_preview(self, width: int = 8, height: int = 8) -> str:
        values = self.layer2[: width * height]
        rows: list[str] = []
        for row in range(height):
            chunk = values[row * width : (row + 1) * width]
            rows.append(" ".join(f"{value:02x}" for value in chunk))
        return "\n".join(rows)


@dataclass
class WldObject:
    """16-byte world target/object entry from a .WLD file (struct WorldObject)."""
    unit_ref: int       # uint16 — type reference
    x: int              # uint16 — world X
    y: int              # uint16 — world Y
    unit_type: int      # int16
    target_flags: int   # int16 (0x100=airbase, 0x200=large, 0x400=waypoint…)
    occupant_type: int  # int16 — plane type stationed here
    patrol_count: int   # int16
    object_idx: int     # int16 & 0x7f

    @property
    def is_airbase(self) -> bool:
        return bool(self.target_flags & 0x100)


@dataclass
class WldUnit:
    """36-byte flight unit entry from a .WLD file (struct FlightUnit)."""
    waypoint_idx: int
    x: int          # uint16
    y: int          # uint16
    altitude: int   # uint16
    heading: int    # int16
    pitch: int      # int16
    roll: int       # int16
    plane_type: int # int16
    flags: int      # int16
    max_speed: int  # int16
    fuel: int       # uint16


@dataclass
class ThreeWld:
    path: Path
    buf1: int = 0
    buf2: int = 0
    buf3: int = 0
    objects: list[WldObject] = field(default_factory=list)
    units: list[WldUnit] = field(default_factory=list)
    names: list[str] = field(default_factory=list)  # worldStringBuf strings, indexed sequentially

    def name_for(self, obj_idx: int, obj: 'WldObject') -> str:
        """Return the best available name for a WldObject.

        Priority:
          1. Sequential index (position of the object in worldObjects[]).
          2. unit_ref field (struct.h says it is the index into wldOffsets).
          3. Hardcoded Python dict keyed by unit_type (simple fallback).
        """
        # 1 — sequential index
        name = self.names[obj_idx] if obj_idx < len(self.names) else ''
        if _is_printable(name):
            return name
        # 2 — unit_ref as name index
        name = self.names[obj.unit_ref] if 0 < obj.unit_ref < len(self.names) else ''
        if _is_printable(name):
            return name
        # 3 — generic type from unit_type
        return _UNIT_TYPE_LABELS.get(obj.unit_type, '')

    def describe(self) -> str:
        lines = [
            f"WLD world file: {self.path}",
            f"  objects: {len(self.objects)}  units: {len(self.units)}  strings: {len(self.names)}",
        ]
        lines.append("--- Objects ---")
        for i, o in enumerate(self.objects):
            if o.x == 0 and o.y == 0:
                continue
            flags = []
            if o.is_airbase:
                flags.append("AIRBASE")
            if o.target_flags & 0x200:
                flags.append("LARGE")
            if o.target_flags & 0x400:
                flags.append("WAYPOINT")
            if o.target_flags & 0x800:
                flags.append("DEST")
            if o.target_flags & 0x008:
                flags.append("opt")
            name = self.name_for(i, o)
            lines.append(
                f"  [{i:3d}] x={o.x:5d} y={o.y:5d}  type={o.unit_type:3d}"
                f"  ref={o.unit_ref:3d}  obj={o.object_idx:3d}"
                f"  flags=0x{o.target_flags:04x}"
                f"  {(' '.join(flags) or '-'):20s}  \"{name}\""
                + (f"  [occupant: {aircraft_name(o.occupant_type)}]" if o.occupant_type > 0 else "")
            )
        lines.append("--- Units (flight units / flightDataBuf) ---")
        for i, u in enumerate(self.units):
            lines.append(
                f"  [{i:3d}] x={u.x:5d} y={u.y:5d}  alt={u.altitude:5d}"
                f"  hdg={u.heading:6d}  {aircraft_name(u.plane_type)}"
            )
        lines.append("--- String table (worldStringBuf) ---")
        for i, n in enumerate(self.names):
            if _is_printable(n):
                lines.append(f"  [{i:3d}] {repr(n)}")
        return "\n".join(lines)


@dataclass
class FaceNormal:
    nx: int
    ny: int
    nz: int
    threshold: int


@dataclass
class ModelVertex:
    x: int
    y: int
    z: int


@dataclass
class ModelEdge:
    va: int
    vb: int


@dataclass
class ModelFace:
    edge_indices: list[int]
    color: int
    normal_index: int = 0  # bits [6:2] of opcode byte → face normal slot


@dataclass
class ModelWireLine:
    edge_index: int
    color: int


@dataclass
class DecodedModel:
    index: int
    offset: int
    face_normals: list[FaceNormal] = field(default_factory=list)
    vertices: list[ModelVertex] = field(default_factory=list)
    edges: list[ModelEdge] = field(default_factory=list)
    faces: list[ModelFace] = field(default_factory=list)
    wire_lines: list[ModelWireLine] = field(default_factory=list)

    def describe(self) -> str:
        lines = [
            f"model #{self.index} @ 0x{self.offset:04x}",
            f"  vertices={len(self.vertices)} edges={len(self.edges)} "
            f"faces={len(self.faces)} lines={len(self.wire_lines)}",
        ]
        for i, v in enumerate(self.vertices):
            lines.append(f"  v{i}: ({v.x}, {v.y}, {v.z})")
        for i, e in enumerate(self.edges):
            lines.append(f"  e{i}: {e.va} -> {e.vb}")
        for i, f in enumerate(self.faces):
            lines.append(f"  face {i}: edges={f.edge_indices} color={f.color} normal={f.normal_index}")
        for i, ln in enumerate(self.wire_lines):
            lines.append(f"  line {i}: edge={ln.edge_index} color={ln.color}")
        return "\n".join(lines)

