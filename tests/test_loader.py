import struct
import tempfile
import unittest
from pathlib import Path

from f15se2_loader import load_3d3, load_3dg, load_3dt


class LoaderTests(unittest.TestCase):
    def test_load_3d3(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "demo.3D3"
            payload = bytearray()
            payload.extend(struct.pack("<H", 0x3333))
            payload.extend(struct.pack("<H", 2))
            payload.extend(struct.pack("<HH", 1, 2))
            payload.extend(struct.pack("<H", 4))
            payload.extend(b"ABCD")
            payload.extend(struct.pack("<B", 0))
            path.write_bytes(payload)

            model = load_3d3(path)
            self.assertEqual(model.signature, 0x3333)
            self.assertEqual(model.header_words, [1, 2])
            self.assertEqual(model.object_data, b"ABCD")

    def test_load_3dt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "demo.3DT"
            payload = bytearray()
            payload.extend(struct.pack("<H", 0x3131))
            payload.extend(struct.pack("<HHHHH", 1, 0, 0, 0, 0))
            payload.extend(struct.pack("<H", 2))
            payload.extend(struct.pack("<hhhH", 1, 2, 3, 4))
            payload.extend(struct.pack("<hhhH", 5, 6, 7, 8))
            path.write_bytes(payload)

            terrain = load_3dt(path)
            self.assertEqual(terrain.signature, 0x3131)
            self.assertEqual(terrain.category_sizes[0], 1)
            self.assertEqual(terrain.tile_counts[0][0], 2)
            self.assertEqual(terrain.categories[0][0].object_count, 2)
            self.assertEqual(terrain.categories[0][0].objects[0].shape, 4)

    def test_load_3dg(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "demo.3DG"
            payload = bytearray()
            payload.extend(struct.pack("<H", 0x3232))
            payload.extend(b"A" * 0x10)
            payload.extend(b"B" * 0x100)
            payload.extend(b"C" * 0x200)
            payload.extend(b"D" * 0x200)
            payload.extend(b"E" * 0x200)
            path.write_bytes(payload)

            grid = load_3dg(path)
            self.assertEqual(grid.signature, 0x3232)
            self.assertEqual(len(grid.header), 0x10)
            self.assertEqual(len(grid.layer2), 0x200)
            self.assertEqual(grid.render_preview(2, 2), "43 43\n43 43")

    def test_load_3dt_with_truncated_object_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "demo.3DT"
            payload = bytearray()
            payload.extend(struct.pack("<H", 0x3131))
            payload.extend(struct.pack("<HHHHH", 1, 0, 0, 0, 0))
            payload.extend(struct.pack("<H", 1))
            payload.extend(struct.pack("<h", 1))
            path.write_bytes(payload)

            with self.assertRaisesRegex(ValueError, "Unexpected end of file while reading i16"):
                load_3dt(path)



if __name__ == "__main__":
    unittest.main()
