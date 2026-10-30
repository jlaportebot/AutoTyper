"""Generate every AutoTyper icon format from the master artwork.

Usage:
    python tools/make_icons.py

Writes into assets/:
    autotyper-logo.png  512x512 master artwork (README, release notes)
    autotyper.ico       multi-resolution Windows icon
    autotyper.icns      macOS app icon
    autotyper.png       512x512 icon for the Linux AppDir

All files are committed so release builds never need Pillow.
"""

import io
from pathlib import Path

try:
    from .make_icon import CANVAS, build_master
except ImportError:  # run as a script: python tools/make_icons.py
    from make_icon import CANVAS, build_master

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

LOGO_NAME = "autotyper-logo.png"
ICO_NAME = "autotyper.ico"
ICNS_NAME = "autotyper.icns"
LINUX_PNG_NAME = "autotyper.png"

__all__ = [
    "CANVAS",
    "ICO_SIZES",
    "build_master",
    "encode_icns",
    "encode_ico",
    "encode_png",
    "main",
    "write_all",
]


def _encode(image, **options):
    """Serialise ``image`` to bytes with the given Pillow save options."""
    buffer = io.BytesIO()
    image.save(buffer, **options)
    return buffer.getvalue()


def encode_png(image):
    """PNG bytes of the artwork."""
    return _encode(image, format="PNG")


def encode_ico(image):
    """Multi-resolution Windows ICO bytes."""
    return _encode(image, format="ICO", sizes=ICO_SIZES)


def encode_icns(image):
    """macOS ICNS bytes, including the retina variants."""
    return _encode(image, format="ICNS")


def write_all(directory=ASSETS_DIR):
    """Render and write every icon into ``directory``; returns the written paths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    master = build_master()
    png = encode_png(master)
    outputs = {
        LOGO_NAME: png,
        LINUX_PNG_NAME: png,
        ICO_NAME: encode_ico(master),
        ICNS_NAME: encode_icns(master),
    }
    written = []
    for name, data in outputs.items():
        path = directory / name
        path.write_bytes(data)
        written.append(path)
    return written


def main():
    for path in write_all():
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
