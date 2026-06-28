from __future__ import annotations
from f15se_helpers import _read_bytes, _read_u8, _read_u16, _read_i16
from pathlib import Path
from f15se_entities import (
    ThreeD3Model,
    ThreeDTerrain,
    ThreeDGGrid,
    ThreeWld,
    DecodedModel, 
    WldObject,
    WldUnit,
    TerrainTile,
    TileEntry,
    FaceNormal,
    ModelVertex,
    ModelEdge,
    ModelFace,
    ModelWireLine,
    PathLike
)
from f15se_constant import (
    TILE_OBJECT_SIZE,
    MAX_TILE_DATA
)
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

