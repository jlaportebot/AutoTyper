"""The AutoTyper icon artwork.

Only the drawing code lives here; ``tools/make_icons.py`` renders it into the
Windows, macOS and Linux icon files.
"""

from PIL import Image, ImageDraw

BACKGROUND = "#0e0f12"
ACCENT = "#c8f560"
MUTED = "#3a3f4b"
CANVAS = 512


def _rounded_tile(draw: ImageDraw.ImageDraw, inset: int) -> None:
    """Draw the dark rounded tile that backs every icon size."""
    draw.rounded_rectangle(
        (inset, inset, CANVAS - inset, CANVAS - inset),
        radius=CANVAS // 6,
        fill=BACKGROUND,
    )


def _type_lines(draw: ImageDraw.ImageDraw, top: int, line_h: int, gap: int) -> None:
    """Draw three typed lines that shrink like real text being entered."""
    left = CANVAS * 0.22
    right = CANVAS * 0.78
    widths = (1.0, 0.78, 0.55)
    for index, ratio in enumerate(widths):
        y0 = top + index * (line_h + gap)
        color = ACCENT if index == 0 else MUTED
        draw.rounded_rectangle(
            (left, y0, left + (right - left) * ratio, y0 + line_h),
            radius=line_h // 2,
            fill=color,
        )


def _caret(draw: ImageDraw.ImageDraw, top: int, line_h: int, gap: int) -> None:
    """Draw the blinking-caret bar at the end of the first line."""
    x0 = CANVAS * 0.78
    y0 = top + line_h + gap
    draw.rounded_rectangle(
        (x0, y0, x0 + CANVAS * 0.045, y0 + line_h),
        radius=CANVAS * 0.02,
        fill=ACCENT,
    )


def build_master() -> Image.Image:
    """Render the 512x512 master artwork."""
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _rounded_tile(draw, inset=CANVAS // 24)
    line_h = CANVAS // 16
    gap = CANVAS // 9
    top = CANVAS * 0.27
    _type_lines(draw, top=top, line_h=line_h, gap=gap)
    _caret(draw, top=top, line_h=line_h, gap=gap)
    return image
