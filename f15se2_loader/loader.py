from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional
from f15se_helpers import aircraft_name
from f15se_entities import (
    ThreeDTerrain,
    ThreeDGGrid,
    ThreeWld,
    DecodedModel, 
    WldObject,
    ModelVertex,
    ModelFace,
    PathLike
)
from f15se_constant import (
    _AIRCRAFT_MODEL_IDS,
    _DEFAULT_PALETTE,
    _LOD_DIM,
    _TILE_GRID_DIM,
    _THEATER_GRIDS,
    WLD_MAX
)
from data_loader import (
    load_3d3,
    load_3dt,
    load_3dg,
    load_wld,
    decode_3d3_models,
)
try:
    import pygame  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pygame = None


def aircraft_model_id(plane_type: int) -> int:
    """Return the 15FLT.3D3 shape index for a plane_type, or -1 if none."""
    if 0 <= plane_type < len(_AIRCRAFT_MODEL_IDS):
        return _AIRCRAFT_MODEL_IDS[plane_type]
    return -1

def process_3dg(grid: ThreeDGGrid, lod: int, col: int, row: int) -> int:
    """Return the tile-category index for grid cell (col, row) at the given LOD.

    The returned value is the tile index within the matching 3DT category
    (category index == lod).  Out-of-bounds returns 0.  Mirrors eg3dgrid.c
    process3dg(), including the LOD 4 top grid (g_topLodGrid) with its +2 offset.
    """
    if lod < 0 or lod > 4:
        return 0
    if lod == 4:
        # LOD 4 reads the 8×8 theater top grid with a +2 cell offset.
        col += 2
        row += 2
    dim = _LOD_DIM[lod]
    if col < 0 or row < 0 or col >= dim or row >= dim:
        return 0
    if lod == 4:
        idx = col + (row << 3)
        return grid.top_grid[idx] if idx < len(grid.top_grid) else 0
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
    parser.add_argument("--theater", type=int, default=0,
                        help="Theater index 0-7 selecting the LOD-4 top grid (default 0)")

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


def _render_model_faces(
    surface,
    mdl: "DecodedModel",
    project_vertex,
    palette: list[tuple[int, int, int]] = _DEFAULT_PALETTE,
    is_back_facing=None,
    outline: bool = True,
) -> None:
    """Render a decoded model's filled faces (painter's algorithm).

    This is the single shared model renderer used by every viewer: the
    standalone --model viewer, the 3D world map and the 2D top-down map.
    The only thing that differs between call sites is how a vertex is mapped
    to the screen, supplied via ``project_vertex``:

        project_vertex(i) -> (screen_point | None, depth)

    where ``depth`` is the painter-sort key (larger == drawn first / farther).
    Faces are filled with ``palette[face.color]`` and outlined with a slightly
    darker shade, exactly like the original model viewer.
    """
    import math

    n = len(mdl.vertices)
    proj: list[tuple[int, int] | None] = [None] * n
    depth: list[float] = [0.0] * n
    for i in range(n):
        r = project_vertex(i)
        if r is not None and r[0] is not None:
            proj[i] = r[0]
            depth[i] = r[1]

    face_list: list[tuple[float, list[tuple[int, int]], tuple[int, int, int]]] = []
    for face in mdl.faces:
        if is_back_facing is not None and is_back_facing(face):
            continue
        seen: set[int] = set()
        poly_vi: list[int] = []
        for ei in face.edge_indices:
            if ei >= len(mdl.edges):
                continue
            e = mdl.edges[ei]
            for vi in (e.va, e.vb):
                if vi not in seen and vi < n:
                    seen.add(vi)
                    poly_vi.append(vi)
        valid_vi = [vi for vi in poly_vi if proj[vi] is not None]
        if len(valid_vi) < 3:
            continue
        pts = [proj[vi] for vi in valid_vi]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        avg_z = sum(depth[vi] for vi in valid_vi) / len(valid_vi)
        face_list.append((avg_z, pts, palette[face.color % len(palette)]))

    face_list.sort(key=lambda t: t[0], reverse=True)
    for _, pts, color in face_list:
        pygame.draw.polygon(surface, color, pts)
        if outline:
            dark = (max(0, color[0] - 50), max(0, color[1] - 50), max(0, color[2] - 50))
            pygame.draw.polygon(surface, dark, pts, 1)


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
    W, H = 1024, 768
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
    NEAR = 10           # near-plane clip distance
    VIEW_DIST_CELLS = 100   # render radius in cells
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
            def _pv(i: int):
                v = mdl.vertices[i]
                wx = owx + v.x * scale
                wy = owy + v.z * scale + y_floor
                wz = owz + v.y * scale
                cc = _to_cam(wx, wy, wz, *basis)
                # camera-space z is the painter depth (larger == farther)
                return (_proj(*cc), cc[2])

            _render_model_faces(surface, mdl, _pv, _DEFAULT_PALETTE)

        # The map is drawn as several LOD passes, coarse → fine, exactly like
        # drawMapTiles(): LOD 4 (8×8 theater grid) is the always-present map
        # background, then LOD 3 / LOD 2 add coastline and inland detail on top.
        def _draw_tile_pass_3d(pass_lod: int) -> None:
            if pass_lod >= len(terrain.lod):
                return
            cat = terrain.lod[pass_lod]
            tdim = _TILE_GRID_DIM[pass_lod]
            tworld = (_LOD_DIM[lod] * CELL_SIZE) / tdim
            tscale = tworld / 0x1000
            radius2 = (VIEW_DIST_CELLS * CELL_SIZE) ** 2
            cells: list[tuple[float, int, int]] = []
            for row in range(tdim):
                for col in range(tdim):
                    ccx = (col + 0.5) * tworld - cam_x
                    ccz = (row + 0.5) * tworld - cam_z
                    d2 = ccx * ccx + ccz * ccz
                    if d2 > radius2:
                        continue
                    cells.append((d2, col, row))
            cells.sort(reverse=True)
            for _, col, row in cells:
                tile_idx = process_3dg(grid, pass_lod, col, row)
                if tile_idx >= len(cat):
                    continue
                # Tile center anchor — matches drawMapTiles() (+ tileSize >> 1).
                cx = (col + 0.5) * tworld
                cz = (row + 0.5) * tworld
                for obj in cat[tile_idx].objects:
                    if obj.z != 0:
                        continue
                    owx = cx + obj.x * tscale
                    owz = cz + obj.y * tscale
                    mdl = models_by_shape.get(obj.shape)
                    if mdl and mdl.vertices:
                        _draw_mdl_at(mdl, owx, 0.0, owz, y_floor=0.0, scale=tscale)
                    else:
                        p = _proj(*_to_cam(owx, 0.0, owz, *basis))
                        if p:
                            c = (255, 220, 60) if obj.shape < 8 else (255, 130, 60)
                            pygame.draw.circle(surface, c, p, 3)

        for pass_lod in (4, 3, 2, 1, 0):
            if pass_lod >= lod:
                _draw_tile_pass_3d(pass_lod)
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

        # Same coarse→fine LOD passes as the 3D view (LOD 4 background first).
        def _draw_tile_pass_2d(pass_lod: int) -> None:
            if pass_lod >= len(terrain.lod):
                return
            cat = terrain.lod[pass_lod]
            tdim = _TILE_GRID_DIM[pass_lod]
            tile_px = (dim * cell_px) / tdim
            tunits = tile_px / 0x1000
            for row in range(tdim):
                sy = row * tile_px - half_map - pan_y + H / 2
                if sy + tile_px < 0 or sy > H:
                    continue
                for col in range(tdim):
                    sx = col * tile_px - half_map - pan_x + W / 2
                    if sx + tile_px < 0 or sx > W:
                        continue
                    tile_idx = process_3dg(grid, pass_lod, col, row)
                    if tile_idx >= len(cat):
                        continue
                    cxp = sx + tile_px / 2
                    cyp = sy + tile_px / 2
                    for obj in cat[tile_idx].objects:
                        if obj.z != 0:
                            continue
                        ox = cxp + obj.x * tunits
                        oy = cyp + obj.y * tunits
                        mdl = models_by_shape.get(obj.shape)
                        if mdl is not None and mdl.vertices:
                            _draw_model_topdown_2d(mdl, ox, oy, tile_px)
                        else:
                            dot_r = max(1, int(tile_px / 8))
                            dot_c = (255, 220, 60) if obj.shape < 8 else (255, 130, 60)
                            pygame.draw.circle(surface, dot_c, (int(ox), int(oy)), dot_r)

        for pass_lod in (4, 3, 2, 1, 0):
            if pass_lod >= lod:
                _draw_tile_pass_2d(pass_lod)

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
        model.z (altitude) is the painter depth (higher altitude drawn on top).
        Scale: same ratio as MODEL_SCALE — csz/0x1000 pixels per game unit."""
        verts = m.vertices
        if not verts:
            return
        scale = csz / 0x1000  # game units → pixels (same as MODEL_SCALE in 3D)

        if m.faces:
            def _pv(i: int):
                v = verts[i]
                # negate altitude so lower faces are drawn first (higher on top)
                return ((int(cx + v.x * scale), int(cy + v.y * scale)), -v.z)
            _render_model_faces(surface, m, _pv, _DEFAULT_PALETTE)
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

        if show_filled:
            def _pv(i: int):
                p = centered[i]
                return (_proj(p[0], p[1], p[2], cx, cy, scale), p[2])
            _render_model_faces(
                surface, m, _pv, pal,
                is_back_facing=(_is_back_facing if cull_back else None),
            )

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
            grid = load_3dg(args.grid)
            # Populate the LOD-4 top grid from the theater table (not in the 3DG file).
            grid.top_grid = bytes(_THEATER_GRIDS[args.theater & 7])
            _show_world_viewer(load_3dt(args.terrain), grid, wld, mdls, flt_mdls, photo_mdls)
        elif args.model:
            # 3D model viewer
            _show_model_viewer(decode_3d3_models(load_3d3(args.model)))
        else:
            print("--show requires --model or both --terrain and --grid")

    if not any([args.model, args.terrain, args.grid, args.show, args.wld, args.decode]):
        parser.print_help()


if __name__ == "__main__":
    main()
