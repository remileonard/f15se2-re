from __future__ import annotations

import argparse
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

try:
    import pygame  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pygame = None


PathLike = Union[str, Path]

MAX_TILE_DATA = 4000
TILE_OBJECT_SIZE = 7


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
    category_sizes: list[int] = field(default_factory=list)
    tile_counts: list[list[int]] = field(default_factory=list)
    categories: list[list[TerrainTile]] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        tile_count = sum(len(category) for category in self.categories)
        object_count = sum(sum(tile.object_count for tile in category) for category in self.categories)
        return {
            "path": str(self.path),
            "signature": self.signature,
            "category_sizes": self.category_sizes,
            "tile_counts": self.tile_counts,
            "category_count": len(self.categories),
            "tile_count": tile_count,
            "object_count": object_count,
        }

    def describe(self) -> str:
        summary = self.summary()
        lines = [
            "3DT terrain",
            f"  path: {summary['path']}",
            f"  signature: 0x{summary['signature']:04x}",
            f"  category_sizes: {summary['category_sizes']}",
            f"  categories: {summary['category_count']}",
            f"  tiles: {summary['tile_count']}",
            f"  objects: {summary['object_count']}",
        ]
        for category_idx, category in enumerate(self.categories):
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

def _is_printable(s: str) -> bool:
    """True when s is a non-empty string containing only printable ASCII."""
    return bool(s) and all(32 <= ord(c) <= 126 for c in s)


# Hardcoded fallback labels for WorldObject.unit_type values.
# Derived from reverse-engineering unit_type usage across stgen.c / egcombat.c.
_UNIT_TYPE_LABELS: dict[int, str] = {
    0:  '',
    1:  'Waypoint',
    2:  'Bridge',
    3:  'Road Junction',
    4:  'Armored Column',
    5:  'Infantry',
    6:  'Truck Column',
    7:  'Recon',
    8:  'Supply Depot',
    9:  'SAM Site',
    10: 'AA Gun',
    11: 'SAM Radar',
    12: 'Command Post',
    13: 'Fuel Dump',
    14: 'Ammo Dump',
    15: 'Factory',
    16: 'Power Plant',
    17: 'Rail Yard',
    18: 'Airfield',
    19: 'Naval Base',
    20: 'Oil Refinery',
    21: 'Port/Refinery',
}

# Aircraft type catalogue — mirrors aircraftTypes[19] in egdata.c.
# Each entry: (short_name, nato_reporting_name).
# Index == WldUnit.plane_type == WldObject.occupant_type.
_AIRCRAFT_TYPES: list[tuple[str, str]] = [
    ("MIG-23",  "Flogger"),   # 0
    ("MIG-25",  "Foxbat"),    # 1
    ("MIG-29",  "Fulcrum"),   # 2
    ("F-1",     "Mirage"),    # 3
    ("Su-27",   "Flanker"),   # 4
    ("IL-76",   "Mainstay"),  # 5
    ("F-4E",    "Phantom"),   # 6
    ("F-14",    "Tomcat"),    # 7
    ("F-18",    "Hornet"),    # 8
    ("An-72",   "Coaler"),    # 9
    ("F-18",    "Hornet"),    # 10  (friendly variant)
    ("MIG-23",  "Flogger"),   # 11  (variant)
    ("F-14",    "Tomcat"),    # 12  (friendly variant)
    ("F-4E",    "Phantom"),   # 13  (friendly variant)
    ("MIG-17",  "Fresco"),    # 14
    ("Tu-95",   "Bear"),      # 15
    ("Mi-24",   "Hind"),      # 16
    ("F-5",     "Tiger"),     # 17
    ("767",     "Boeing"),    # 18
]


# Shape indices into 15FLT.3D3 per aircraftTypes[i].modelId in egdata.c.
# -1 = no 3D model available for that type.
_AIRCRAFT_MODEL_IDS: list[int] = [
    17, 18, 19, 20, 19, 16, 18, 19, -1,  0,   # 0-9
    -1,  0, -1, -1, 17,  0, 17, 22, -1,        # 10-18
]


def aircraft_name(plane_type: int) -> str:
    """Return 'SHORT (NATO)' for a plane_type index into aircraftTypes[]."""
    if 0 <= plane_type < len(_AIRCRAFT_TYPES):
        short, nato = _AIRCRAFT_TYPES[plane_type]
        return f"{short} ({nato})"
    return f"plane#{plane_type}"


def aircraft_model_id(plane_type: int) -> int:
    """Return the 15FLT.3D3 shape index for a plane_type, or -1 if none."""
    if 0 <= plane_type < len(_AIRCRAFT_MODEL_IDS):
        return _AIRCRAFT_MODEL_IDS[plane_type]
    return -1


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

def _read_bytes(data: bytes, offset: int, size: int, *, name: str) -> bytes:
    if offset + size > len(data):
        raise ValueError(f"Unexpected end of file while reading {name}")
    return data[offset : offset + size]


def _read_u8(data: bytes, offset: int) -> int:
    return int(_read_bytes(data, offset, 1, name="u8")[0])


def _read_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(_read_bytes(data, offset, 2, name="u16"), "little")


def _read_i16(data: bytes, offset: int) -> int:
    return int.from_bytes(_read_bytes(data, offset, 2, name="i16"), "little", signed=True)



def load_3d3(path: PathLike) -> ThreeD3Model:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 2:
        raise ValueError("3D3 file is empty")

    signature = _read_u16(data, 0)
    if signature != 0x3333:
        raise ValueError(f"Unexpected 3D3 signature 0x{signature:04x}")

    offset = 2
    header_count = _read_u16(data, offset)
    offset += 2
    header_words = [
        _read_u16(data, offset + index * 2)
        for index in range(header_count)
    ]
    offset += header_count * 2

    object_size = _read_u16(data, offset)
    offset += 2
    object_data = _read_bytes(data, offset, object_size, name="object data")
    offset += object_size

    extra_section_count = _read_u8(data, offset)
    offset += 1

    extra_bytes_a = b""
    extra_bytes_b = b""
    extra_bytes_c = b""
    vertex_x: list[int] = []
    vertex_y: list[int] = []
    vertex_z: list[int] = []
    if extra_section_count != 0:
        extra_bytes_a = _read_bytes(data, offset, extra_section_count, name="extra A")
        offset += extra_section_count
        extra_bytes_b = _read_bytes(data, offset, extra_section_count, name="extra B")
        offset += extra_section_count
        extra_bytes_c = _read_bytes(data, offset, extra_section_count, name="extra C")
        offset += extra_section_count

        vertex_x_count = _read_u8(data, offset)
        offset += 1
        if vertex_x_count != 0:
            vertex_x = [
                _read_u16(data, offset + index * 2)
                for index in range(vertex_x_count)
            ]
            offset += vertex_x_count * 2

        vertex_y_count = _read_u8(data, offset)
        offset += 1
        if vertex_y_count != 0:
            vertex_y = [
                _read_u16(data, offset + index * 2)
                for index in range(vertex_y_count)
            ]
            offset += vertex_y_count * 2

        vertex_z_count = _read_u8(data, offset)
        offset += 1
        if vertex_z_count != 0:
            vertex_z = [
                _read_u16(data, offset + index * 2)
                for index in range(vertex_z_count)
            ]

    return ThreeD3Model(
        path=path,
        signature=signature,
        header_words=header_words,
        object_data=object_data,
        extra_bytes_a=extra_bytes_a,
        extra_bytes_b=extra_bytes_b,
        extra_bytes_c=extra_bytes_c,
        vertex_x=vertex_x,
        vertex_y=vertex_y,
        vertex_z=vertex_z,
    )


def load_3dt(path: PathLike) -> ThreeDTerrain:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 2:
        raise ValueError("3DT file is empty")

    signature = _read_u16(data, 0)
    if signature != 0x3131:
        raise ValueError(f"Unexpected 3DT signature 0x{signature:04x}")

    offset = 2
    category_sizes = [_read_u16(data, offset + index * 2) for index in range(5)]
    offset += 10

    # First loop: read all tile count arrays (matrix3dt in C) before any tile data
    tile_counts: list[list[int]] = []
    for category_size in category_sizes:
        if category_size > 32:
            raise ValueError(f"Category size {category_size} exceeds 0x20")
        counts = [_read_u16(data, offset + index * 2) for index in range(category_size)]
        offset += category_size * 2
        tile_counts.append(counts)

    # Second loop: read actual tile object data
    categories: list[list[TerrainTile]] = []
    byte_offset = 0
    for counts in tile_counts:
        tiles: list[TerrainTile] = []
        for object_count in counts:
            if byte_offset + object_count * TILE_OBJECT_SIZE > MAX_TILE_DATA:
                raise ValueError("Too much tile data")
            objects: list[TileEntry] = []
            for _ in range(object_count):
                x = _read_i16(data, offset)
                offset += 2
                y = _read_i16(data, offset)
                offset += 2
                z = _read_i16(data, offset)
                offset += 2
                shape = _read_u16(data, offset)
                offset += 2
                objects.append(TileEntry(x=x, y=y, z=z, shape=shape & 0xFF))
                byte_offset += TILE_OBJECT_SIZE
            tiles.append(TerrainTile(object_count=object_count, objects=objects))
        categories.append(tiles)
    return ThreeDTerrain(
        path=path,
        signature=signature,
        category_sizes=category_sizes,
        tile_counts=tile_counts,
        categories=categories,
    )

def load_3dg(path: PathLike) -> ThreeDGGrid:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 2:
        raise ValueError("3DG file is empty")

    signature = _read_u16(data, 0)
    if signature != 0x3232:
        raise ValueError(f"Unexpected 3DG signature 0x{signature:04x}")

    offset = 2
    header = _read_bytes(data, offset, 0x10, name="header")
    offset += 0x10
    layer1 = _read_bytes(data, offset, 0x100, name="layer1")
    offset += 0x100
    layer2 = _read_bytes(data, offset, 0x200, name="layer2")
    offset += 0x200
    layer3 = _read_bytes(data, offset, 0x200, name="layer3")
    offset += 0x200
    layer4 = _read_bytes(data, offset, 0x200, name="layer4")

    return ThreeDGGrid(
        path=path,
        signature=signature,
        header=header,
        layer1=layer1,
        layer2=layer2,
        layer3=layer3,
        layer4=layer4,
    )


# WLD world coordinates run from 0 to 0x8000 (32768).
# Y-axis is inverted: y=0 → south (high row), y=0x8000 → north (row 0).
WLD_MAX = 32768.0


def load_wld(path: PathLike) -> ThreeWld:
    """Load a theater .WLD file.

    Binary layout (readWorldData in enworld.c):
      u16  worldWaypointCount
      u16  worldObjectCount
      u16  worldRouteTable[0]
      u16  worldRouteCount
      worldObjectCount × 16-byte WorldObject
      u16  worldSamCount
      worldSamCount × 36-byte worldSamTable (SAM/AA units)
      100  unitTypeTable
      100  worldUnitFlags
      750  worldStringBuf  (null-terminated names, indexed by unit_ref)
      … (gridFlags, worldGridSize, etc. — not parsed)
    """
    path = Path(path)
    data = path.read_bytes()
    off = 0

    def u16() -> int:
        nonlocal off
        v = int.from_bytes(data[off:off + 2], "little")
        off += 2
        return v

    def i16() -> int:
        nonlocal off
        v = int.from_bytes(data[off:off + 2], "little", signed=True)
        off += 2
        return v

    buf1 = u16()
    obj_count = u16()
    buf2 = u16()
    buf3 = u16()

    objects: list[WldObject] = []
    for _ in range(obj_count):
        if off + 16 > len(data):
            break
        objects.append(WldObject(
            unit_ref=u16(), x=u16(), y=u16(),
            unit_type=i16(), target_flags=i16(),
            occupant_type=i16(), patrol_count=i16(),
            object_idx=i16() & 0x7f,
        ))

    units: list[WldUnit] = []
    if off + 2 <= len(data):
        unit_count = u16()
        for _ in range(unit_count):
            if off + 36 > len(data):
                break
            wp  = i16(); x = u16(); y = u16(); alt = u16()
            off += 8  # xPrecise(4) + yPrecise(4)
            hdg = i16(); pitch = i16(); roll = i16()
            pt  = i16(); flags = i16(); spd = i16(); fuel = u16()
            off += 6  # reserved[6]
            units.append(WldUnit(
                waypoint_idx=wp, x=x, y=y, altitude=alt,
                heading=hdg, pitch=pitch, roll=roll,
                plane_type=pt, flags=flags, max_speed=spd, fuel=fuel,
            ))

    # Skip unitTypeTable (100) and worldUnitFlags (100)
    if off + 200 <= len(data):
        off += 200

    # Parse worldStringBuf (750 bytes of null-terminated names).
    names: list[str] = []
    STRING_BUF_SIZE = 750
    if off + STRING_BUF_SIZE <= len(data):
        str_buf = data[off: off + STRING_BUF_SIZE]
        pos = 0
        while pos < STRING_BUF_SIZE and len(names) < 100:
            end = str_buf.find(b'\x00', pos)
            if end == -1:
                end = STRING_BUF_SIZE
            names.append(str_buf[pos:end].decode('latin-1', errors='replace').strip())
            pos = end + 1

    return ThreeWld(path=path, buf1=buf1, buf2=buf2, buf3=buf3,
                    objects=objects, units=units, names=names)


# ── 3DG grid resolver ─────────────────────────────────────────────────────────
# Mirrors eg3dgrid.c process3dg().
# LOD dimensions (cells per axis):  LOD0=1024  LOD1=256  LOD2=64  LOD3=16
# LOD 4 (8×8) requires the theater-specific g_topLodGrid and is omitted here.
# LODs 0-3 only need the 3DG file layers and recurse at most to LOD 3.
_LOD_DIM = [1024, 256, 64, 16]  # index = LOD 0-3


def process_3dg(grid: ThreeDGGrid, lod: int, col: int, row: int) -> int:
    """Return the tile-category index for grid cell (col, row) at the given LOD.

    The returned value is the tile index within the matching 3DT category
    (category index == lod).  Out-of-bounds returns 0.
    """
    if lod < 0 or lod > 3:
        return 0
    dim = _LOD_DIM[lod]
    if col < 0 or row < 0 or col >= dim or row >= dim:
        return 0
    if lod == 3:
        # buf1_3dg is layer1: a flat 16×16 byte array
        idx = col + row * 16
        return grid.layer1[idx] if idx < len(grid.layer1) else 0
    # LOD 0-2: 4×4 sub-tile within the parent LOD cell
    parent = process_3dg(grid, lod + 1, col >> 2, row >> 2)
    # eg3dgrid.c case mapping:
    #   lod==2 → buf2_3dg = our layer2
    #   lod==1 → buf3_3dg = our layer3
    #   lod==0 → buf4_3dg = our layer4
    layers = [grid.layer4, grid.layer3, grid.layer2]  # indexed by lod 0,1,2
    layer = layers[lod]
    idx = (col & 3) + ((row & 3) << 2) + (parent << 4)
    return layer[idx] if idx < len(layer) else 0

def _decode_model(
    data: bytes,
    base_offset: int,
    index: int,
    extra_a: bytes,
    extra_b: bytes,
    extra_c: bytes,
    vertex_x: list[int],
    vertex_y: list[int],
    vertex_z: list[int],
) -> DecodedModel:
    """Decode one model stream from object_data.

    Stream layout (mirrors eg3drast.c processSceneObject pipeline):
      [render_mode:u8] [LOD headers: while byte&0x80: 3 bytes each]
      [opcode/count:u8  bits 4..0=face_count, >0x10 => wide 4-byte masks]
      [face_count × FaceNormal: nx,ny,nz,thr as i16]
      [vtx_al:u8  bit7=indexed, bits6..0=count]
        if indexed: count × (mask_size bytes + 1 byte ref → lookup tables)
        else:        count × (mask_size bytes + i16 x, i16 y, i16 z)
      [edge_count:u8] [edge_count × (mask_size + va:u8 + vb:u8)]
      [prim_count:u8]  (0xFF = RLE, not decoded here)
        face: opcode&3==1 → [count:u8] [count×edge_idx:u8] [color:u8]
        line: else        → [mask_size bytes] [edge_idx:u8] [color:u8]
    """
    pos = base_offset

    def u8() -> int:
        nonlocal pos
        if pos >= len(data):
            raise ValueError("unexpected end of model data")
        v = data[pos]; pos += 1
        return v

    def i16() -> int:
        nonlocal pos
        if pos + 2 > len(data):
            raise ValueError("unexpected end of model data")
        v = int.from_bytes(data[pos:pos + 2], "little", signed=True)
        pos += 2
        return v

    def skip(n: int) -> None:
        nonlocal pos
        pos += n

    skip(1)  # render-mode byte

    # LOD headers: any byte with bit 7 set is a 3-byte record; skip them all
    # to get the highest-detail (nearest) LOD data
    while pos < len(data) and data[pos] & 0x80:
        skip(3)

    # opcode/count byte: low 5 bits = face visibility count
    opcode_byte = u8()
    face_count = opcode_byte & 0x1f
    wide_vtx = face_count > 0x10
    mask_size = 4 if wide_vtx else 2

    # face visibility normals (fnx, fny, fnz, threshold) — 8 bytes each
    normals: list[FaceNormal] = []
    for _ in range(face_count):
        normals.append(FaceNormal(i16(), i16(), i16(), i16()))

    # vertex list
    vertices: list[ModelVertex] = []
    al = u8()
    vtx_count = al & 0x7f
    if al & 0x80:
        # indexed mode: ref byte → extra_a/b/c → vertex_x/y/z tables
        use_lookup = bool(extra_a and extra_b and extra_c
                         and vertex_x and vertex_y and vertex_z)
        for _ in range(vtx_count):
            skip(mask_size)
            ref = u8()
            if use_lookup:
                xa = extra_a[ref % len(extra_a)]
                yb = extra_b[ref % len(extra_b)]
                zc = extra_c[ref % len(extra_c)]
                x = vertex_x[xa % len(vertex_x)]
                y = vertex_y[yb % len(vertex_y)]
                z = vertex_z[zc % len(vertex_z)]
                # stored as uint16, reinterpret as signed
                x = x if x < 0x8000 else x - 0x10000
                y = y if y < 0x8000 else y - 0x10000
                z = z if z < 0x8000 else z - 0x10000
            else:
                x = y = z = 0
            vertices.append(ModelVertex(x, y, z))
    elif vtx_count:
        # inline mode: explicit i16 x, y, z per vertex
        for _ in range(vtx_count):
            skip(mask_size)
            vertices.append(ModelVertex(i16(), i16(), i16()))

    # edge list: va/vb are vertex slot indices
    edges: list[ModelEdge] = []
    edge_count = u8()
    for _ in range(edge_count):
        skip(mask_size)
        edges.append(ModelEdge(u8(), u8()))

    # primitive list
    faces: list[ModelFace] = []
    wire_lines: list[ModelWireLine] = []
    prim_count = u8()

    def _decode_prim_command(buf: bytes, p: int) -> int:
        """Decode one primitive command from buf at offset p; return new p."""
        if p >= len(buf):
            return p
        op = buf[p]; p += 1
        if (op & 3) == 1:
            # filled face: [count:u8] [count × edge_idx:u8] [color:u8]
            # bits [6:2] of opcode = face normal index used for back-face
            # culling.  If this index >= face_count the corresponding bit in
            # g_vtxSignMask was never cleared, so the face is always visible.
            normal_idx = (op & 0x7c) >> 2
            if p >= len(buf):
                return p
            n = buf[p]; p += 1
            if p + n + 1 > len(buf):
                return len(buf)
            ei = list(buf[p:p + n]); p += n
            faces.append(ModelFace(edge_indices=ei, color=buf[p], normal_index=normal_idx)); p += 1
        else:
            # wireframe line: [mask_size bytes] [edge_idx:u8] [color:u8]
            p += mask_size
            if p + 2 > len(buf):
                return len(buf)
            wire_lines.append(ModelWireLine(edge_index=buf[p], color=buf[p + 1]))
            p += 2
        return p

    if prim_count == 0xFF:
        # RLE-reordered shared-edge path.
        # Layout after the 0xFF byte (p already advanced past it):
        #   [root: 1 byte]                      RLE tree root node index
        #   [tree: face_count*2 bytes]          left/right child per node (0xFF=null)
        #   [coord: face_count*2 bytes]         int16 offsets from dataBase per group
        #   [cnts:  face_count bytes]           u8 run-count per group
        #   [dataBase: ...]                     packed primitive commands
        skip(1 + face_count * 2)              # root + adjacency tree
        coord_offs: list[int] = []
        for _ in range(face_count):
            if pos + 2 > len(data):
                break
            lo, hi = data[pos], data[pos + 1]; pos += 2
            off = lo | (hi << 8)
            if off >= 0x8000:
                off -= 0x10000
            coord_offs.append(off)
        run_cnts = [u8() for _ in range(face_count)]
        data_base = pos
        for i in range(len(coord_offs)):
            run_p = data_base + coord_offs[i]
            for _ in range(run_cnts[i] if i < len(run_cnts) else 0):
                run_p = _decode_prim_command(data, run_p)
    elif prim_count != 0:
        # Direct list: prim_count consecutive primitive commands.
        for _ in range(prim_count):
            pos = _decode_prim_command(data, pos)

    return DecodedModel(
        index=index, offset=base_offset,
        face_normals=normals, vertices=vertices,
        edges=edges, faces=faces, wire_lines=wire_lines,
    )


def decode_3d3_models(model: ThreeD3Model) -> list[DecodedModel]:
    """Decode all models indexed by header_words in a ThreeD3Model's object_data.

    header_words[i] is the byte offset of model i inside object_data.
    """
    data = model.object_data
    results = []
    for i, offset in enumerate(model.header_words):
        if offset >= len(data):
            continue
        try:
            results.append(_decode_model(
                data, offset, index=i,
                extra_a=model.extra_bytes_a,
                extra_b=model.extra_bytes_b,
                extra_c=model.extra_bytes_c,
                vertex_x=model.vertex_x,
                vertex_y=model.vertex_y,
                vertex_z=model.vertex_z,
            ))
        except (IndexError, ValueError):
            pass
    return results

def load_scene(model_path: PathLike, terrain_path: PathLike, grid_path: PathLike) -> dict[str, object]:
    return {
        "model": load_3d3(model_path),
        "terrain": load_3dt(terrain_path),
        "grid": load_3dg(grid_path),
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect F-15 Strike Eagle 2 3D asset files")
    parser.add_argument("--model", help="Path to terrain .3D3 file (CE.3D3 etc.)")
    parser.add_argument("--flt-model", help="Path to flight .3D3 file (15FLT.3D3) — aircraft & missile models")
    parser.add_argument("--photo-model", help="Path to photo .3D3 file (PHOTO.3D3) — hi-res target models")
    parser.add_argument("--terrain", help="Path to a .3DT file")
    parser.add_argument("--grid", help="Path to a .3DG file")
    parser.add_argument("--show", action="store_true", help="Open a simple viewer window")
    parser.add_argument("--decode", action="store_true",
                    help="Decode and print model streams from a .3D3 file")
    parser.add_argument("--wld", help="Path to a theater .WLD file (overlaid on world map)")

    return parser


def _render_grid_surface(grid: ThreeDGGrid, width: int = 320, height: int = 240) -> Optional[object]:
    if pygame is None:
        return None

    pygame.init()
    surface = pygame.display.set_mode((width, height))
    pygame.display.set_caption("F-15 SE2 grid preview")
    surface.fill((0, 0, 0))

    cell_w = max(1, width // 16)
    cell_h = max(1, height // 16)
    for index, value in enumerate(grid.layer2[: 16 * 16]):
        x = (index % 16) * cell_w
        y = (index // 16) * cell_h
        color = (value, value // 2, value // 3)
        pygame.draw.rect(surface, color, (x, y, cell_w, cell_h))

    pygame.display.flip()
    return surface

# Default 256-entry palette used by the model viewer when the game
# Full 256-entry VGA palette generated by src/vgapal.c (vgapal 256).
# Standard VGA colour layout: 0-15 = EGA colours, 16-31 = grey ramp,
# 32-55 = full-saturation spectrum, 56-247 = half/quarter-intensity cycles,
# 248-255 = black (unused).
_DEFAULT_PALETTE: list[tuple[int, int, int]] = [
    (  0,  0,  0), (  0,  0,170), (  0,170,  0), (  0,170,170),
    (170,  0,  0), (170,  0,170), (170, 85,  0), (170,170,170),
    ( 85, 85, 85), ( 85, 85,255), ( 85,255, 85), ( 85,255,255),
    (255, 85, 85), (255, 85,255), (255,255, 85), (255,255,255),
    (  0,  0,  0), ( 20, 20, 20), ( 32, 32, 32), ( 44, 44, 44),
    ( 56, 56, 56), ( 69, 69, 69), ( 81, 81, 81), ( 97, 97, 97),
    (113,113,113), (130,130,130), (146,146,146), (162,162,162),
    (182,182,182), (203,203,203), (227,227,227), (255,255,255),
    (  0,  0,255), ( 65,  0,255), (125,  0,255), (190,  0,255),
    (255,  0,255), (255,  0,190), (255,  0,125), (255,  0, 65),
    (255,  0,  0), (255, 65,  0), (255,125,  0), (255,190,  0),
    (255,255,  0), (190,255,  0), (125,255,  0), ( 65,255,  0),
    (  0,255,  0), (  0,255, 65), (  0,255,125), (  0,255,190),
    (  0,255,255), (  0,190,255), (  0,125,255), (  0, 65,255),
    (125,125,255), (158,125,255), (190,125,255), (223,125,255),
    (255,125,255), (255,125,223), (255,125,190), (255,125,158),
    (255,125,125), (255,158,125), (255,190,125), (255,223,125),
    (255,255,125), (223,255,125), (190,255,125), (158,255,125),
    (125,255,125), (125,255,158), (125,255,190), (125,255,223),
    (125,255,255), (125,223,255), (125,190,255), (125,158,255),
    (182,182,255), (199,182,255), (219,182,255), (235,182,255),
    (255,182,255), (255,182,235), (255,182,219), (255,182,199),
    (255,182,182), (255,199,182), (255,219,182), (255,235,182),
    (255,255,182), (235,255,182), (219,255,182), (199,255,182),
    (182,255,182), (182,255,199), (182,255,219), (182,255,235),
    (182,255,255), (182,235,255), (182,219,255), (182,199,255),
    (  0,  0,113), ( 28,  0,113), ( 56,  0,113), ( 85,  0,113),
    (113,  0,113), (113,  0, 85), (113,  0, 56), (113,  0, 28),
    (113,  0,  0), (113, 28,  0), (113, 56,  0), (113, 85,  0),
    (113,113,  0), ( 85,113,  0), ( 56,113,  0), ( 28,113,  0),
    (  0,113,  0), (  0,113, 28), (  0,113, 56), (  0,113, 85),
    (  0,113,113), (  0, 85,113), (  0, 56,113), (  0, 28,113),
    ( 56, 56,113), ( 69, 56,113), ( 85, 56,113), ( 97, 56,113),
    (113, 56,113), (113, 56, 97), (113, 56, 85), (113, 56, 69),
    (113, 56, 56), (113, 69, 56), (113, 85, 56), (113, 97, 56),
    (113,113, 56), ( 97,113, 56), ( 85,113, 56), ( 69,113, 56),
    ( 56,113, 56), ( 56,113, 69), ( 56,113, 85), ( 56,113, 97),
    ( 56,113,113), ( 56, 97,113), ( 56, 85,113), ( 56, 69,113),
    ( 81, 81,113), ( 89, 81,113), ( 97, 81,113), (105, 81,113),
    (113, 81,113), (113, 81,105), (113, 81, 97), (113, 81, 89),
    (113, 81, 81), (113, 89, 81), (113, 97, 81), (113,105, 81),
    (113,113, 81), (105,113, 81), ( 97,113, 81), ( 89,113, 81),
    ( 81,113, 81), ( 81,113, 89), ( 81,113, 97), ( 81,113,105),
    ( 81,113,113), ( 81,105,113), ( 81, 97,113), ( 81, 89,113),
    (  0,  0, 65), ( 16,  0, 65), ( 32,  0, 65), ( 48,  0, 65),
    ( 65,  0, 65), ( 65,  0, 48), ( 65,  0, 32), ( 65,  0, 16),
    ( 65,  0,  0), ( 65, 16,  0), ( 65, 32,  0), ( 65, 48,  0),
    ( 65, 65,  0), ( 48, 65,  0), ( 32, 65,  0), ( 16, 65,  0),
    (  0, 65,  0), (  0, 65, 16), (  0, 65, 32), (  0, 65, 48),
    (  0, 65, 65), (  0, 48, 65), (  0, 32, 65), (  0, 16, 65),
    ( 32, 32, 65), ( 40, 32, 65), ( 48, 32, 65), ( 56, 32, 65),
    ( 65, 32, 65), ( 65, 32, 56), ( 65, 32, 48), ( 65, 32, 40),
    ( 65, 32, 32), ( 65, 40, 32), ( 65, 48, 32), ( 65, 56, 32),
    ( 65, 65, 32), ( 56, 65, 32), ( 48, 65, 32), ( 40, 65, 32),
    ( 32, 65, 32), ( 32, 65, 40), ( 32, 65, 48), ( 32, 65, 56),
    ( 32, 65, 65), ( 32, 56, 65), ( 32, 48, 65), ( 32, 40, 65),
    ( 44, 44, 65), ( 48, 44, 65), ( 52, 44, 65), ( 60, 44, 65),
    ( 65, 44, 65), ( 65, 44, 60), ( 65, 44, 52), ( 65, 44, 48),
    ( 65, 44, 44), ( 65, 48, 44), ( 65, 52, 44), ( 65, 60, 44),
    ( 65, 65, 44), ( 60, 65, 44), ( 52, 65, 44), ( 48, 65, 44),
    ( 44, 65, 44), ( 44, 65, 48), ( 44, 65, 52), ( 44, 65, 60),
    ( 44, 65, 65), ( 44, 60, 65), ( 44, 52, 65), ( 44, 48, 65),
    (  0,  0,  0), (  0,  0,  0), (  0,  0,  0), (  0,  0,  0),
    (  0,  0,  0), (  0,  0,  0), (  0,  0,  0), (  0,  0,  0),
]


def _compute_tile_bg_colors(
    terrain: ThreeDTerrain,
    lod: int,
    models_by_shape: dict[int, "DecodedModel"],
) -> dict[int, tuple[int, int, int]]:
    """For each tile_idx, find the dominant face color across all its models.

    The color is slightly darkened so it reads as a background (the actual 3D
    models will be drawn on top at full brightness).
    """
    result: dict[int, tuple[int, int, int]] = {}
    if lod >= len(terrain.categories):
        return result
    cat = terrain.categories[lod]
    for tile_idx, tile in enumerate(cat):
        counts: dict[int, int] = {}
        for obj in tile.objects:
            mdl = models_by_shape.get(obj.shape)
            if mdl:
                for face in mdl.faces:
                    ci = face.color % len(_DEFAULT_PALETTE)
                    counts[ci] = counts.get(ci, 0) + 1
        if counts:
            # Exclude index 0 (black) unless it's the only one
            non_black = {k: v for k, v in counts.items() if k != 0}
            best = max(non_black or counts, key=lambda k: (non_black or counts)[k])
            r, g, b = _DEFAULT_PALETTE[best]
            # Darken: use as background behind the 3D models
            result[tile_idx] = (max(0, r - 60), max(0, g - 60), max(0, b - 60))
    return result


# Per-tile-index fallback colors (used when no model data is loaded).
# 0-15 = actual terrain categories; 0x10/0x11 = sea/out-of-bounds.
_TILE_COLORS: list[tuple[int, int, int]] = [
    ( 80, 120,  60), (100, 145,  75), ( 70, 110,  50), ( 60, 100,  45),  # 0-3  grassland
    (130,  95,  55), (155, 115,  65), (175, 135,  85), (115,  95,  75),  # 4-7  dry/desert
    ( 50,  90, 150), ( 60, 100, 160), ( 70, 110, 170), ( 45,  80, 140),  # 8-11 water
    (120, 120, 120), (145, 145, 135), (105, 105, 105), (165, 155, 145),  # 12-15 urban
    ( 25,  40,  70), ( 18,  32,  58),                                    # 0x10/0x11 sea
]


def _show_world_viewer(
    terrain: ThreeDTerrain,
    grid: ThreeDGGrid,
    wld: Optional[ThreeWld] = None,
    models: Optional[list["DecodedModel"]] = None,
    flt_models: Optional[list["DecodedModel"]] = None,
    photo_models: Optional[list["DecodedModel"]] = None,
) -> None:
    """3-D perspective world-map viewer with FPS camera navigation.

    3D mode keys
    ------------
    W / S          move forward / backward
    A / D          strafe left / right
    Q / E          move up / down
    ← →            rotate camera left / right (yaw)
    ↑ ↓            tilt camera up / down (pitch)
    TAB            switch to 2D top-down view
    L              toggle LOD 3 (16×16) / LOD 2 (64×64)
    ESC            quit

    2D mode keys
    ------------
    ← → ↑ ↓        pan
    + / -           zoom
    TAB             switch back to 3D view
    L               toggle LOD
    ESC             quit
    """
    import math

    if pygame is None:
        print("pygame is not installed")
        return

    pygame.init()
    W, H = 800, 600
    surface = pygame.display.set_mode((W, H))
    pygame.display.set_caption("F-15 SE2 world map")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 16)

    # ── Constants ─────────────────────────────────────────────────────────────
    CELL_SIZE = 1024.0     # world units per grid cell
    # Game-unit → world-unit scale derived from projectModelVertices:
    #   g_tileWorldSize = 0x1000 >> g_tileZoomShift = 0x1000 >> 2 = 1024 (LOD3)
    #   vertex_screen_px = vertex_game_unit >> 2  →  MODEL_SCALE = CELL_SIZE/0x1000
    MODEL_SCALE = CELL_SIZE / 0x1000   # = 0.25  (game units → world units)
    FOV = 600.0            # perspective focal length (pixels)
    NEAR = 10.0            # near-plane clip distance
    VIEW_DIST_CELLS = 10   # render radius in cells
    MOVE_SPEED = CELL_SIZE * 2
    TURN_SPEED = 1.5

    # ── Data ──────────────────────────────────────────────────────────────────
    models_by_shape: dict[int, DecodedModel] = (
        {m.index: m for m in models} if models else {}
    )

    # Flight models (15FLT.3D3) — aircraft and missile shapes.
    # Scale factor: flt models use smaller vertex coords than terrain tiles;
    # multiply up so aircraft are visible at world-map zoom level.
    FLT_MODEL_SCALE = MODEL_SCALE * 6   # tuneable: ~6× terrain scale
    flt_models_by_shape: dict[int, DecodedModel] = (
        {m.index: m for m in flt_models} if flt_models else {}
    )
    # Photo models (PHOTO.3D3) — high-detail target models.
    photo_models_by_shape: dict[int, DecodedModel] = (
        {m.index: m for m in photo_models} if photo_models else {}
    )

    # Per-model y-floor: shift model up so its lowest altitude vertex (model.z)
    # sits at world Y=0 (ground level).
    # Axis convention from projectModelVertices / drawNearestTileObject:
    #   model.x  = east-west    → world X
    #   model.y  = north-south  → world Z   (word2 in vertex stream)
    #   model.z  = altitude     → world Y   (word3, skipped in 2D map projection)
    @dataclass
    class _MdlInfo:
        y_floor: float  # world-Y shift so lowest altitude vertex is at ground

    def _build_mdl_info(bank: dict[int, DecodedModel], scale: float) -> dict[int, _MdlInfo]:
        result: dict[int, _MdlInfo] = {}
        for shape_idx, m in bank.items():
            if not m.vertices:
                result[shape_idx] = _MdlInfo(y_floor=0.0)
            else:
                min_alt = min(v.z for v in m.vertices)
                result[shape_idx] = _MdlInfo(y_floor=-min_alt * scale)
        return result

    mdl_info: dict[int, _MdlInfo] = _build_mdl_info(models_by_shape, MODEL_SCALE)
    flt_mdl_info: dict[int, _MdlInfo] = _build_mdl_info(flt_models_by_shape, FLT_MODEL_SCALE)
    photo_mdl_info: dict[int, _MdlInfo] = _build_mdl_info(photo_models_by_shape, MODEL_SCALE)

    # Pre-compute tile background colors from model face data for all LODs.
    # This gives terrain-accurate colors derived from the dominant face color
    # of each tile's models (instead of the static _TILE_COLORS fallback).
    tile_bg_by_lod: dict[int, dict[int, tuple[int, int, int]]] = {
        l: _compute_tile_bg_colors(terrain, l, models_by_shape)
        for l in range(4)
    }

    # ── State ─────────────────────────────────────────────────────────────────
    lod = 3
    view_3d = True

    # 3D camera
    dim = _LOD_DIM[lod]
    cam_x = dim / 2 * CELL_SIZE
    cam_y = CELL_SIZE * 2.5
    cam_z = (dim / 2 - 2) * CELL_SIZE
    yaw   = 0.0    # 0 = looking toward +Z
    pitch = -0.35  # slightly downward

    # 2D view state
    cell_px = min(W, H) / dim
    pan_x = 0.0
    pan_y = 0.0

    # ── Camera helpers ────────────────────────────────────────────────────────
    def _cam_basis() -> tuple[float, ...]:
        """Return (rx,ry,rz, ux,uy,uz, fx,fy,fz) camera basis vectors."""
        sy = math.sin(yaw);   cy = math.cos(yaw)
        sp = math.sin(pitch); cp = math.cos(pitch)
        fx = sy * cp;  fy = sp;  fz = cy * cp   # forward
        rx = cy;       ry = 0.0; rz = -sy        # right
        # up = forward × right  (gives +Y world-up when camera is level)
        ux = fy * rz - fz * ry
        uy = fz * rx - fx * rz
        uz = fx * ry - fy * rx
        return rx, ry, rz, ux, uy, uz, fx, fy, fz

    def _to_cam(
        wx: float, wy: float, wz: float,
        rx: float, ry: float, rz: float,
        ux: float, uy: float, uz: float,
        fx: float, fy: float, fz: float,
    ) -> tuple[float, float, float]:
        dx = wx - cam_x; dy = wy - cam_y; dz = wz - cam_z
        return (
            dx * rx + dy * ry + dz * rz,
            dx * ux + dy * uy + dz * uz,
            dx * fx + dy * fy + dz * fz,
        )

    def _proj(
        ccx: float, ccy: float, ccz: float
    ) -> tuple[int, int] | None:
        if ccz < NEAR:
            return None
        return (int(W // 2 + ccx * FOV / ccz),
                int(H // 2 - ccy * FOV / ccz))

    # ── 3D draw ───────────────────────────────────────────────────────────────
    def draw_3d() -> None:
        surface.fill((30, 50, 80))   # sky

        basis = _cam_basis()
        rx, ry, rz, ux, uy, uz, fx, fy, fz = basis

        # ── Inner model-drawing helper ────────────────────────────────────────
        def _draw_mdl_at(
            mdl: "DecodedModel",
            owx: float, owy: float, owz: float,
            y_floor: float = 0.0,
            scale: float = MODEL_SCALE,
        ) -> None:
            """Project and draw a decoded model at world position (owx, owy, owz)."""
            verts_cam: list[tuple[float, float, float]] = []
            verts_proj: list[tuple[int, int] | None] = []
            for v in mdl.vertices:
                wx = owx + v.x * scale
                wy = owy + v.z * scale + y_floor
                wz = owz + v.y * scale
                cc = _to_cam(wx, wy, wz, *basis)
                verts_cam.append(cc)
                verts_proj.append(_proj(*cc))

            face_list: list[tuple[float, list[tuple[int, int]], tuple[int, int, int]]] = []
            for face in mdl.faces:
                seen_vi: set[int] = set()
                poly_vi: list[int] = []
                for ei in face.edge_indices:
                    if ei >= len(mdl.edges):
                        continue
                    e = mdl.edges[ei]
                    for vi in (e.va, e.vb):
                        if vi not in seen_vi and vi < len(verts_cam):
                            seen_vi.add(vi)
                            poly_vi.append(vi)
                valid_vi = [vi for vi in poly_vi if verts_proj[vi] is not None]
                if len(valid_vi) < 3:
                    continue
                pts_s = [verts_proj[vi] for vi in valid_vi]  # type: ignore[misc]
                cx_ = sum(p[0] for p in pts_s) / len(pts_s)  # type: ignore[index]
                cy_ = sum(p[1] for p in pts_s) / len(pts_s)  # type: ignore[index]
                pts_s.sort(key=lambda p: math.atan2(p[1] - cy_, p[0] - cx_))  # type: ignore[index]
                avg_z = sum(verts_cam[vi][2] for vi in valid_vi) / len(valid_vi)
                color = _DEFAULT_PALETTE[face.color % len(_DEFAULT_PALETTE)]
                face_list.append((avg_z, pts_s, color))  # type: ignore[arg-type]

            face_list.sort(reverse=True)
            for _, pts_s, color in face_list:
                pygame.draw.polygon(surface, color, pts_s)

            for edge in mdl.edges:
                pa = verts_proj[edge.va] if edge.va < len(verts_proj) else None
                pb = verts_proj[edge.vb] if edge.vb < len(verts_proj) else None
                if pa and pb:
                    pygame.draw.line(surface, (0, 0, 0), pa, pb)

        # Collect cells sorted far-to-near (painter's algorithm).
        cells: list[tuple[float, int, int]] = []
        for row in range(dim):
            for col in range(dim):
                ccx = (col + 0.5) * CELL_SIZE - cam_x
                ccz = (row + 0.5) * CELL_SIZE - cam_z
                dist2 = ccx * ccx + ccz * ccz
                if dist2 > (VIEW_DIST_CELLS * CELL_SIZE) ** 2:
                    continue
                cells.append((dist2, col, row))
        cells.sort(reverse=True)

        for _, col, row in cells:
            tile_idx = process_3dg(grid, lod, col, row)
            bg = (tile_bg_by_lod.get(lod, {}).get(tile_idx)
                  or _TILE_COLORS[min(tile_idx, len(_TILE_COLORS) - 1)])

            x0 = col * CELL_SIZE;       x1 = (col + 1) * CELL_SIZE
            z0 = row * CELL_SIZE;       z1 = (row + 1) * CELL_SIZE

            # Project the 4 ground-level corners.
            corners = [
                _to_cam(x0, 0, z0, *basis), _to_cam(x1, 0, z0, *basis),
                _to_cam(x1, 0, z1, *basis), _to_cam(x0, 0, z1, *basis),
            ]
            pts = [_proj(*c) for c in corners]
            valid = [p for p in pts if p is not None]

            if len(valid) >= 3:
                pygame.draw.polygon(surface, bg, valid)
                for i in range(len(valid)):
                    pygame.draw.line(
                        surface, (0, 0, 0), valid[i], valid[(i + 1) % len(valid)], 1
                    )

            # Draw tile objects.
            if lod < len(terrain.categories):
                cat = terrain.categories[lod]
                if tile_idx < len(cat):
                    for obj in cat[tile_idx].objects:
                        # World position of the tile object.
                        # obj.x = east-west, obj.y = north-south, obj.z = altitude
                        # (same axes as projectModelVertices / drawNearestTileObject)
                        owx = col * CELL_SIZE + obj.x * MODEL_SCALE
                        owz = row * CELL_SIZE + obj.y * MODEL_SCALE
                        owy = obj.z * MODEL_SCALE

                        mdl = models_by_shape.get(obj.shape)
                        if mdl and mdl.vertices:
                            yf = mdl_info[obj.shape].y_floor
                            _draw_mdl_at(mdl, owx, owy, owz, y_floor=yf, scale=MODEL_SCALE)
                        else:
                            cc = _to_cam(owx, owy, owz, *basis)
                            p = _proj(*cc)
                            if p:
                                c = (255, 220, 60) if obj.shape < 8 else (255, 130, 60)
                                pygame.draw.circle(surface, c, p, 3)

        # WLD objects — render CE.3D3 model (via object_idx) or marker post.
        MARKER_H = CELL_SIZE * 0.15  # marker height in world units
        if wld is not None:
            def _wld_color(obj: WldObject) -> tuple[int, int, int]:
                if obj.is_airbase:           return (255, 80, 80)
                if obj.target_flags & 0x400: return (100, 160, 255)
                if obj.unit_type != 0:       return (255, 160, 40)
                return (255, 220, 60)

            for i, obj in enumerate(wld.objects):
                if obj.x == 0 and obj.y == 0:
                    continue  # skip null/placeholder entries
                owx = obj.x / WLD_MAX * dim * CELL_SIZE
                owz = (WLD_MAX - obj.y) / WLD_MAX * dim * CELL_SIZE
                c = _wld_color(obj)

                # obj.object_idx is a type-category index (into objectTypeTable[]).
                # It also happens to match the CE.3D3 shape index for static objects
                # (SAM=53, airport=62, port=68).  BUT target-marker objects (tf & 0x0001)
                # all share objectIdx=21, which is the generic target-indicator crosshair
                # shape — not a type-specific model.  Skip 3D rendering for those.
                is_target_marker = bool(obj.target_flags & 0x0001)
                wld_mdl = None if is_target_marker else models_by_shape.get(obj.object_idx)
                if wld_mdl and wld_mdl.vertices:
                    yf = mdl_info[obj.object_idx].y_floor
                    _draw_mdl_at(wld_mdl, owx, 0.0, owz, y_floor=yf, scale=MODEL_SCALE)
                    lbl_pt = _proj(*_to_cam(owx, MARKER_H, owz, *basis))
                else:
                    # Fallback: vertical marker post
                    p0 = _proj(*_to_cam(owx, 0,        owz, *basis))
                    p1 = _proj(*_to_cam(owx, MARKER_H, owz, *basis))
                    if p0 and p1:
                        pygame.draw.line(surface, c, p0, p1, 2)
                        pygame.draw.circle(surface, c, p1, 4)
                    elif p0:
                        pygame.draw.circle(surface, c, p0, 5)
                    lbl_pt = p1 or p0

                # Label (name from string table) near the marker top
                if lbl_pt:
                    name = wld.name_for(i, obj)
                    if name:
                        lbl = font.render(name, True, c)
                        surface.blit(lbl, (lbl_pt[0] + 5, lbl_pt[1] - 8))

            # Flight units — resolve position from waypoint_idx when unit has no direct coords.
            c_unit = (255, 60, 200)
            for u in wld.units:
                ux, uy = u.x, u.y
                if ux == 0 and uy == 0:
                    if 0 < u.waypoint_idx < len(wld.objects):
                        ref = wld.objects[u.waypoint_idx]
                        ux, uy = ref.x, ref.y
                if ux == 0 and uy == 0:
                    continue
                owx = ux / WLD_MAX * dim * CELL_SIZE
                owz = (WLD_MAX - uy) / WLD_MAX * dim * CELL_SIZE

                # Try to render the actual 3D aircraft model from flt_models.
                mdl_id = aircraft_model_id(u.plane_type)
                flt_mdl = flt_models_by_shape.get(mdl_id) if mdl_id >= 0 else None
                if flt_mdl and flt_mdl.vertices:
                    yf = flt_mdl_info[mdl_id].y_floor
                    _draw_mdl_at(flt_mdl, owx, 0.0, owz, y_floor=yf, scale=FLT_MODEL_SCALE)
                    # Label above the model
                    apex = _proj(*_to_cam(owx, MARKER_H * 1.5, owz, *basis))
                    if apex:
                        lbl = font.render(aircraft_name(u.plane_type), True, c_unit)
                        surface.blit(lbl, (apex[0] + 5, apex[1] - 8))
                else:
                    # Fallback: marker post + label
                    p0 = _proj(*_to_cam(owx, 0, owz, *basis))
                    p1 = _proj(*_to_cam(owx, MARKER_H * 1.5, owz, *basis))
                    if p0 and p1:
                        pygame.draw.line(surface, c_unit, p0, p1, 1)
                    lbl_pt = p1 or p0
                    if lbl_pt:
                        pygame.draw.circle(surface, c_unit, lbl_pt, 4)
                        lbl = font.render(aircraft_name(u.plane_type), True, c_unit)
                        surface.blit(lbl, (lbl_pt[0] + 5, lbl_pt[1] - 8))

        hud = font.render(
            f"3D  LOD={lod} ({dim}×{dim})  "
            f"WASD:move  QE:↕  ←→:yaw  ↑↓:pitch  TAB:2D  L:lod  ESC",
            True, (220, 220, 220),
        )
        surface.blit(hud, (5, 5))
        pygame.display.flip()

    # ── 2D draw ───────────────────────────────────────────────────────────────
    def draw_2d() -> None:
        surface.fill((10, 20, 40))
        half_map = dim * cell_px / 2

        for row in range(dim):
            sy = row * cell_px - half_map - pan_y + H / 2
            if sy + cell_px < 0 or sy > H:
                continue
            for col in range(dim):
                sx = col * cell_px - half_map - pan_x + W / 2
                if sx + cell_px < 0 or sx > W:
                    continue
                tile_idx = process_3dg(grid, lod, col, row)
                color = (tile_bg_by_lod.get(lod, {}).get(tile_idx)
                         or _TILE_COLORS[min(tile_idx, len(_TILE_COLORS) - 1)])
                r = pygame.Rect(int(sx), int(sy),
                                max(1, int(cell_px) - 1), max(1, int(cell_px) - 1))
                pygame.draw.rect(surface, color, r)

                if cell_px >= 4 and lod < len(terrain.categories):
                    cat = terrain.categories[lod]
                    if tile_idx < len(cat):
                        for obj in cat[tile_idx].objects:
                            if obj.z != 0:
                                continue
                            ox = sx + cell_px / 2 + obj.x * cell_px / 0x1000
                            oy = sy + cell_px / 2 + obj.y * cell_px / 0x1000
                            mdl = models_by_shape.get(obj.shape)
                            if mdl is not None and cell_px >= 16:
                                _draw_model_topdown_2d(mdl, ox, oy, cell_px)
                            else:
                                dot_r = max(1, int(cell_px / 8))
                                dot_c = (255, 220, 60) if obj.shape < 8 else (255, 130, 60)
                                pygame.draw.circle(surface, dot_c, (int(ox), int(oy)), dot_r)

        if wld is not None:
            half_map2 = dim * cell_px / 2

            def _wld_to_screen(wx_wld: int, wy_wld: int) -> tuple[float, float]:
                sx = wx_wld / WLD_MAX * dim * cell_px - half_map2 - pan_x + W / 2
                sy = (WLD_MAX - wy_wld) / WLD_MAX * dim * cell_px - half_map2 - pan_y + H / 2
                return sx, sy

            def _wld_obj_color(obj: WldObject) -> tuple[int, int, int]:
                if obj.is_airbase:           return (255, 80, 80)
                if obj.target_flags & 0x400: return (100, 160, 255)
                if obj.unit_type != 0:       return (255, 160, 40)
                return (255, 220, 60)

            for i, obj in enumerate(wld.objects):
                if obj.x == 0 and obj.y == 0:
                    continue
                wx, wy = _wld_to_screen(obj.x, obj.y)
                if not (-20 <= wx < W + 20 and -20 <= wy < H + 20):
                    continue
                c = _wld_obj_color(obj)
                ix, iy = int(wx), int(wy)

                # Draw CE.3D3 model top-down if available, else dot/star.
                # Skip model for target-marker objects (tf & 0x0001): they all share
                # objectIdx=21 (generic target-indicator crosshair), not a real model.
                is_target_marker = bool(obj.target_flags & 0x0001)
                wld_mdl = None if is_target_marker else models_by_shape.get(obj.object_idx)
                if wld_mdl is not None and wld_mdl.vertices and cell_px >= 4:
                    _draw_model_topdown_2d(wld_mdl, ix, iy, cell_px)
                elif obj.is_airbase:
                    r = 6
                    for angle in range(0, 360, 72):
                        a = math.radians(angle)
                        pygame.draw.line(surface, c, (ix, iy),
                                         (int(ix + r * math.cos(a)), int(iy + r * math.sin(a))), 2)
                else:
                    pygame.draw.circle(surface, c, (ix, iy), 4)
                    pygame.draw.circle(surface, (0, 0, 0), (ix, iy), 4, 1)
                # Show name if cell is big enough
                if cell_px >= 32:
                    name = wld.name_for(i, obj)
                    if name:
                        lbl = font.render(name, True, c)
                        surface.blit(lbl, (ix + 6, iy - 6))

            for u in wld.units:
                ux, uy = u.x, u.y
                if ux == 0 and uy == 0:
                    if 0 < u.waypoint_idx < len(wld.objects):
                        ref = wld.objects[u.waypoint_idx]
                        ux, uy = ref.x, ref.y
                if ux == 0 and uy == 0:
                    continue
                wx, wy = _wld_to_screen(ux, uy)
                if 0 <= wx < W and 0 <= wy < H:
                    pygame.draw.circle(surface, (255, 60, 200), (int(wx), int(wy)), 4)
                    if cell_px >= 16:
                        lbl = font.render(aircraft_name(u.plane_type), True, (255, 60, 200))
                        surface.blit(lbl, (int(wx) + 5, int(wy) - 6))

        hud = font.render(
            f"2D  LOD {lod} ({dim}×{dim})  cell={cell_px:.1f}px  "
            f"←→↑↓:pan  +/-:zoom  TAB:3D  L:lod  ESC",
            True, (200, 200, 200),
        )
        surface.blit(hud, (5, 5))
        pygame.display.flip()

    def _draw_model_topdown_2d(m: DecodedModel, cx: float, cy: float, csz: float) -> None:
        """Draw model top-down (bird's eye): model.x → screen X, model.y → screen Y.
        model.z (altitude) is used only for painter's sort (higher = drawn on top).
        Scale: same ratio as MODEL_SCALE — csz/0x1000 pixels per game unit."""
        verts = m.vertices
        if not verts:
            return
        scale = csz / 0x1000  # game units → pixels (same as MODEL_SCALE in 3D)

        # ── Filled faces, sorted by avg altitude (low altitude first) ─────────
        if m.faces:
            face_list: list[tuple[float, list[tuple[int, int]], tuple[int, int, int]]] = []
            for face in m.faces:
                seen_vi: set[int] = set()
                poly_vi: list[int] = []
                for ei in face.edge_indices:
                    if ei >= len(m.edges):
                        continue
                    e = m.edges[ei]
                    for vi in (e.va, e.vb):
                        if vi not in seen_vi and vi < len(verts):
                            seen_vi.add(vi)
                            poly_vi.append(vi)
                if len(poly_vi) < 3:
                    continue
                pts = [(int(cx + verts[vi].x * scale), int(cy + verts[vi].y * scale))
                       for vi in poly_vi]
                # Sort by polar angle so the polygon winds correctly
                cxp = sum(p[0] for p in pts) / len(pts)
                cyp = sum(p[1] for p in pts) / len(pts)
                pts.sort(key=lambda p: math.atan2(p[1] - cyp, p[0] - cxp))
                avg_alt = sum(verts[vi].z for vi in poly_vi) / len(poly_vi)
                pal = _DEFAULT_PALETTE
                color = pal[face.color % len(pal)]
                face_list.append((avg_alt, pts, color))
            face_list.sort()  # low altitude first (high altitude drawn on top)
            for _, pts, color in face_list:
                pygame.draw.polygon(surface, color, pts)
            # Edge outlines
            for edge in m.edges:
                va = verts[edge.va]; vb = verts[edge.vb]
                pygame.draw.line(
                    surface, (0, 0, 0),
                    (int(cx + va.x * scale), int(cy + va.y * scale)),
                    (int(cx + vb.x * scale), int(cy + vb.y * scale)),
                )
        else:
            # Fallback: wire edges
            for edge in m.edges:
                va = verts[edge.va]; vb = verts[edge.vb]
                pygame.draw.line(
                    surface, (200, 220, 160),
                    (int(cx + va.x * scale), int(cy + va.y * scale)),
                    (int(cx + vb.x * scale), int(cy + vb.y * scale)),
                )

    # ── Initial render ────────────────────────────────────────────────────────
    draw_3d()

    running = True
    while running:
        dt = min(clock.tick(30) / 1000.0, 0.1)   # cap dt at 100 ms

        redraw = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_TAB:
                    view_3d = not view_3d
                    redraw = True

                elif event.key == pygame.K_l:
                    lod = 2 if lod == 3 else 3
                    dim = _LOD_DIM[lod]  # type: ignore[assignment]  # nonlocal update
                    cell_px = min(W, H) / dim  # type: ignore[assignment]
                    pan_x = pan_y = 0.0  # type: ignore[assignment]
                    redraw = True

                elif not view_3d:
                    if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                        cell_px *= 1.5; redraw = True  # type: ignore[assignment]
                    elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        cell_px = max(1.0, cell_px / 1.5); redraw = True  # type: ignore[assignment]
                    elif event.key == pygame.K_LEFT:
                        pan_x -= 40.0; redraw = True  # type: ignore[assignment]
                    elif event.key == pygame.K_RIGHT:
                        pan_x += 40.0; redraw = True  # type: ignore[assignment]
                    elif event.key == pygame.K_UP:
                        pan_y -= 40.0; redraw = True  # type: ignore[assignment]
                    elif event.key == pygame.K_DOWN:
                        pan_y += 40.0; redraw = True  # type: ignore[assignment]

        if view_3d:
            keys = pygame.key.get_pressed()
            sy = math.sin(yaw); cy_v = math.cos(yaw)

            moved = False
            # AZERTY layout: Z=forward, S=backward, Q=strafe-left, D=strafe-right
            #                 A=up, E=down
            if keys[pygame.K_z]:
                cam_x += sy * MOVE_SPEED * dt; cam_z += cy_v * MOVE_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_s]:
                cam_x -= sy * MOVE_SPEED * dt; cam_z -= cy_v * MOVE_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_q]:
                cam_x -= cy_v * MOVE_SPEED * dt; cam_z += sy * MOVE_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_d]:
                cam_x += cy_v * MOVE_SPEED * dt; cam_z -= sy * MOVE_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_a] or keys[pygame.K_PAGEUP]:
                cam_y += MOVE_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_e] or keys[pygame.K_PAGEDOWN]:
                cam_y -= MOVE_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_LEFT]:
                yaw -= TURN_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_RIGHT]:
                yaw += TURN_SPEED * dt; moved = True  # type: ignore[assignment]
            if keys[pygame.K_UP]:
                pitch = min(math.pi / 2 - 0.05, pitch + TURN_SPEED * dt); moved = True  # type: ignore[assignment]
            if keys[pygame.K_DOWN]:
                pitch = max(-math.pi / 2 + 0.05, pitch - TURN_SPEED * dt); moved = True  # type: ignore[assignment]

            if moved or redraw:
                draw_3d()
        else:
            if redraw:
                draw_2d()

    pygame.quit()





def _show_model_viewer(
    models: list[DecodedModel],
    palette: Optional[list[tuple[int, int, int]]] = None,
) -> None:
    import math

    if pygame is None:
        print("pygame is not installed; falling back to text output")
        for m in models:
            print(m.describe())
        return

    if not models:
        print("no models decoded")
        return

    pal = palette if palette is not None else _DEFAULT_PALETTE
    FOV = 500.0

    pygame.init()
    W, H = 800, 600
    surface = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 18)

    idx = 0
    angle_y = 0.0
    rotating = True
    show_filled = True
    show_wires = False
    cull_back = False

    def _rotate_y(
        verts: list[ModelVertex], ay: float
    ) -> list[tuple[float, float, float]]:
        ca, sa = math.cos(ay), math.sin(ay)
        return [(v.x * ca + v.z * sa, v.y, -v.x * sa + v.z * ca) for v in verts]

    def _proj(
        x: float, y: float, z: float, cx: int, cy: int, scale: float
    ) -> tuple[int, int]:
        """Perspective projection; Y is flipped so model-up maps to screen-up."""
        dz = z + FOV
        if dz < 1.0:
            dz = 1.0
        return (int(cx + x * scale * FOV / dz),
                int(cy - y * scale * FOV / dz))

    def render(m: DecodedModel, ay: float) -> None:
        surface.fill((15, 15, 25))
        verts = m.vertices
        if not verts:
            pygame.display.flip()
            return

        rv = _rotate_y(verts, ay)

        # Auto-scale to fill ~70 % of the smaller viewport dimension.
        xs = [p[0] for p in rv]
        ys = [p[1] for p in rv]
        span = max(
            max(xs) - min(xs) if xs else 1.0,
            max(ys) - min(ys) if ys else 1.0,
            1.0,
        )
        scale = min(W, H) * 0.35 / span
        cx, cy = W // 2, H // 2

        # Translate model so its centroid sits at z=0 for the projection.
        z_off = sum(p[2] for p in rv) / len(rv)
        centered = [(p[0], p[1], p[2] - z_off) for p in rv]

        def proj_idx(i: int) -> tuple[int, int]:
            p = centered[i]
            return _proj(p[0], p[1], p[2], cx, cy, scale)

        # --- Build face list with depth and screen-space points --------
        # Each face lists edge indices; each edge has va and vb (vertex slot
        # indices).  We collect both endpoints per edge, deduplicating in
        # insertion order.  This is necessary for fan-style polygons where
        # multiple edges share a common tip vertex (e.g. the nose cone): in
        # that case all e.va are the same tip, so taking va-only collapses the
        # polygon to a single point.  Taking (va, vb) gives the correct shape.
        #
        # Culling mirrors rotatePoint3d in eg3drast.c: each face primitive's
        # opcode bits[6:2] select a face normal from m.face_normals.  The game
        # starts with all-visible (signMask=-1) and clears a bit per back-
        # facing normal.  When cull_back is on we replicate this: rotate the
        # stored face normal by angle_y, then test its z component against the
        # camera direction (0,0,1).  If normal_index >= len(face_normals) the
        # slot was never computed → face is ALWAYS visible (never culled).
        ca, sa = math.cos(ay), math.sin(ay)

        def _is_back_facing(face_: ModelFace) -> bool:
            ni = face_.normal_index
            if ni >= len(m.face_normals):
                return False  # always visible
            fn = m.face_normals[ni]
            # Rotate the stored face normal by the same angle_y as the mesh.
            # The camera looks in +Z world direction, so we test the rotated
            # normal's Z component: if nz_rot > 0 the face points toward the
            # camera (front-facing).  nz_rot <= 0 → back-facing → cull.
            nz_rot = -fn.nx * sa + fn.nz * ca
            return nz_rot <= 0

        draw_faces: list[tuple[float, list[tuple[int, int]], int]] = []
        for face in m.faces:
            if cull_back and _is_back_facing(face):
                continue
            pts3: list[tuple[float, float, float]] = []
            seen_vi: set[int] = set()
            for ei in face.edge_indices:
                if ei < len(m.edges):
                    e = m.edges[ei]
                    for vi in (e.va, e.vb):
                        if vi not in seen_vi and vi < len(centered):
                            seen_vi.add(vi)
                            pts3.append(centered[vi])
            if len(pts3) < 3:
                continue
            spts = [_proj(p[0], p[1], p[2], cx, cy, scale) for p in pts3]
            # Sort projected vertices by polar angle around their centroid so
            # that pygame.draw.polygon receives them in a consistent winding
            # order.  The scan-line rasterizer in the C code accepts edges in
            # any order, but pygame requires a non-self-intersecting polygon.
            # Angle-sort is equivalent to convex-hull order, which matches the
            # game's convex polygon geometry.
            scx = sum(p[0] for p in spts) / len(spts)
            scy = sum(p[1] for p in spts) / len(spts)
            spts.sort(key=lambda p: math.atan2(p[1] - scy, p[0] - scx))
            avg_z = sum(p[2] for p in pts3) / len(pts3)
            draw_faces.append((avg_z, spts, face.color))

        # Painter's algorithm: draw farthest faces first.
        draw_faces.sort(key=lambda t: t[0], reverse=True)

        if show_filled:
            for _, spts, color_idx in draw_faces:
                base = pal[color_idx & 0xFF]
                if len(spts) >= 3:
                    pygame.draw.polygon(surface, base, spts)
                    # Thin dark outline for silhouette.
                    outline = (
                        max(0, base[0] - 50),
                        max(0, base[1] - 50),
                        max(0, base[2] - 50),
                    )
                    pygame.draw.polygon(surface, outline, spts, 1)

        if show_wires or not show_filled:
            wire_color = (0, 200, 80) if not show_filled else (0, 100, 40)
            for e in m.edges:
                if e.va < len(centered) and e.vb < len(centered):
                    pygame.draw.line(
                        surface, wire_color,
                        proj_idx(e.va), proj_idx(e.vb),
                    )

        hud = font.render(
            f"model #{m.index} @ 0x{m.offset:04x}  "
            f"vtx={len(m.vertices)} edges={len(m.edges)} "
            f"faces={len(m.faces)}  [{idx + 1}/{len(models)}]  "
            f"← →:nav  R:rotate({'on' if rotating else 'off'})  "
            f"W:wire({'on' if show_wires else 'off'})  "
            f"F:fill({'on' if show_filled else 'off'})  "
            f"C:cull({'on' if cull_back else 'off'})  ESC:quit",
            True, (180, 180, 180),
        )
        surface.blit(hud, (5, 5))
        pygame.display.flip()

    render(models[idx], angle_y)
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_RIGHT:
                    idx = (idx + 1) % len(models)
                elif event.key == pygame.K_LEFT:
                    idx = (idx - 1) % len(models)
                elif event.key == pygame.K_r:
                    rotating = not rotating
                elif event.key == pygame.K_w:
                    show_wires = not show_wires
                elif event.key == pygame.K_f:
                    show_filled = not show_filled
                elif event.key == pygame.K_c:
                    cull_back = not cull_back

        if rotating:
            angle_y += dt * 1.2  # ~1.2 rad/s

        render(models[idx], angle_y)

    pygame.quit()

def show_viewer(model_path: Optional[PathLike], terrain_path: Optional[PathLike], grid_path: Optional[PathLike]) -> None:
    if pygame is None:
        print("pygame is not installed; falling back to text output")
        return

    model = load_3d3(model_path) if model_path else None
    terrain = load_3dt(terrain_path) if terrain_path else None
    grid = load_3dg(grid_path) if grid_path else None

    if model is not None:
        print(model.describe())
    if terrain is not None:
        print(terrain.describe())
    if grid is not None:
        print(grid.describe())

    if grid is not None:
        _render_grid_surface(grid)
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

        pygame.quit()


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    # ── text output ────────────────────────────────────────────────
    if args.model and not args.show:
        print(load_3d3(args.model).describe())
    if args.terrain and not args.show:
        print(load_3dt(args.terrain).describe())
    if args.grid and not args.show:
        print(load_3dg(args.grid).describe())
    if args.wld and not args.show:
        print(load_wld(args.wld).describe())

    if args.decode and args.model:
        for m in decode_3d3_models(load_3d3(args.model)):
            print(m.describe())

    # ── viewers ────────────────────────────────────────────────────
    if args.show:
        if args.terrain and args.grid:
            # World map viewer (3DG + 3DT, optional WLD overlay, optional models)
            wld = load_wld(args.wld) if args.wld else None
            mdls = decode_3d3_models(load_3d3(args.model)) if args.model else None
            flt_mdls = decode_3d3_models(load_3d3(args.flt_model)) if args.flt_model else None
            photo_mdls = decode_3d3_models(load_3d3(args.photo_model)) if args.photo_model else None
            _show_world_viewer(load_3dt(args.terrain), load_3dg(args.grid), wld, mdls, flt_mdls, photo_mdls)
        elif args.model:
            # 3D model viewer
            _show_model_viewer(decode_3d3_models(load_3d3(args.model)))
        else:
            print("--show requires --model or both --terrain and --grid")

    if not any([args.model, args.terrain, args.grid, args.show, args.wld, args.decode]):
        parser.print_help()


if __name__ == "__main__":
    main()
