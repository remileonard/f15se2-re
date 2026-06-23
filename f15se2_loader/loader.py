from __future__ import annotations

import argparse
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

    categories: list[list[TerrainTile]] = []
    tile_counts: list[list[int]] = []
    byte_offset = 0
    for category_size in category_sizes:
        if category_size > 0x20:
            raise ValueError(f"Category size {category_size} exceeds 0x20")

        counts = [_read_u16(data, offset + index * 2) for index in range(category_size)]
        offset += category_size * 2
        tile_counts.append(counts)

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


def load_scene(model_path: PathLike, terrain_path: PathLike, grid_path: PathLike) -> dict[str, object]:
    return {
        "model": load_3d3(model_path),
        "terrain": load_3dt(terrain_path),
        "grid": load_3dg(grid_path),
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect F-15 Strike Eagle 2 3D asset files")
    parser.add_argument("--model", help="Path to a .3D3 file")
    parser.add_argument("--terrain", help="Path to a .3DT file")
    parser.add_argument("--grid", help="Path to a .3DG file")
    parser.add_argument("--show", action="store_true", help="Open a simple viewer window")
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

    if args.model:
        print(load_3d3(args.model).describe())
    if args.terrain:
        print(load_3dt(args.terrain).describe())
    if args.grid:
        print(load_3dg(args.grid).describe())

    if args.show:
        show_viewer(args.model, args.terrain, args.grid)

    if not any([args.model, args.terrain, args.grid, args.show]):
        parser.print_help()


if __name__ == "__main__":
    main()
