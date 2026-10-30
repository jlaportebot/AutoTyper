"""Tests for the icon generator that feeds the Windows, macOS and Linux builds."""

import io
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # Pillow is only needed to regenerate icons, not to run the app
    Image = None

if Image is not None:
    from tools import make_icons

MASTER_SIZE = 512
ICNS_MAGIC = b"icns"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ICO_MAGIC = b"\x00\x00\x01\x00"


@unittest.skipIf(Image is None, "Pillow is not installed")
class MasterArtwork(unittest.TestCase):
    def test_master_is_a_square_rgba_image(self):
        master = make_icons.build_master()
        self.assertEqual(master.size, (MASTER_SIZE, MASTER_SIZE))
        self.assertEqual(master.mode, "RGBA")

    def test_master_corners_are_transparent_for_the_rounded_tile(self):
        master = make_icons.build_master()
        self.assertEqual(master.getpixel((0, 0))[3], 0)


@unittest.skipIf(Image is None, "Pillow is not installed")
class EncodedBuffers(unittest.TestCase):
    def setUp(self):
        self.master = make_icons.build_master()

    def test_ico_buffer_holds_every_windows_size(self):
        data = make_icons.encode_ico(self.master)
        self.assertTrue(data.startswith(ICO_MAGIC))
        icon = Image.open(io.BytesIO(data))
        self.assertEqual(icon.format, "ICO")
        self.assertEqual(set(icon.info["sizes"]), set(make_icons.ICO_SIZES))

    def test_icns_buffer_is_a_valid_macos_icon(self):
        data = make_icons.encode_icns(self.master)
        self.assertTrue(data.startswith(ICNS_MAGIC))
        icon = Image.open(io.BytesIO(data))
        self.assertEqual(icon.format, "ICNS")
        self.assertIn((MASTER_SIZE, MASTER_SIZE, 1), icon.info["sizes"])

    def test_png_buffer_is_the_512_pixel_linux_icon(self):
        data = make_icons.encode_png(self.master)
        self.assertTrue(data.startswith(PNG_MAGIC))
        icon = Image.open(io.BytesIO(data))
        self.assertEqual(icon.size, (MASTER_SIZE, MASTER_SIZE))


@unittest.skipIf(Image is None, "Pillow is not installed")
class WriteAll(unittest.TestCase):
    def test_writes_every_format_and_returns_the_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = make_icons.write_all(Path(tmp))
            names = sorted(path.name for path in written)
            self.assertEqual(
                names,
                ["autotyper-logo.png", "autotyper.icns", "autotyper.ico", "autotyper.png"],
            )
            for path in written:
                self.assertGreater(path.stat().st_size, 0)

    def test_creates_the_output_directory_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "assets"
            make_icons.write_all(target)
            self.assertTrue(target.is_dir())

    def test_raises_when_the_output_directory_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "assets"
            blocker.write_text("not a directory")
            with self.assertRaises(OSError):
                make_icons.write_all(blocker)


if __name__ == "__main__":
    unittest.main()
