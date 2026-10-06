"""Deterministic motion-graphics templates, rendered with Pillow.

No browser, no HTML/CSS: text is measured with real font metrics, so
overflow is detected rather than clipped silently. Every template renders
transparent PNG frames, which ffmpeg overlays onto the shot. A caption that
does not fit fails the shot instead of shipping broken typography.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


class GraphicsError(RuntimeError):
    """Raised when a template cannot render the given copy."""


# Safe margins as fractions of the canvas: captions stay clear of platform
# chrome on 4:5 and 9:16 alike.
MARGIN_X = 0.08
MARGIN_BOTTOM = 0.12
MAX_CAPTION_LINES = 2


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int
) -> list[str]:
    """Greedy word wrap measured in pixels. A single word wider than the
    box is a failure, not a hyphenation decision we get to make."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), trial, font=font)[2]
        if width <= max_width:
            current = trial
        else:
            if not current:
                raise GraphicsError(
                    f"word {word!r} is wider than the caption box"
                )
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_lines(
    draw: ImageDraw.ImageDraw, lines: list[str], font: Any, max_width: int
) -> list[str]:
    """Split caption lines to fit, enforcing the two-line maximum and the
    no-orphan rule (the last line may not be a single short word)."""
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap(draw, line, font, max_width))
    if len(wrapped) > MAX_CAPTION_LINES:
        raise GraphicsError(
            f"caption needs {len(wrapped)} lines, maximum is {MAX_CAPTION_LINES}"
        )
    if len(wrapped) == MAX_CAPTION_LINES and len(wrapped[-1].split()) == 1:
        last = wrapped.pop()
        if not wrapped:
            raise GraphicsError("caption is a single orphan word")
        wrapped[-1] = f"{wrapped[-1]} {last}"
        # Re-measure: joining may have overflowed the box.
        width = draw.textbbox((0, 0), wrapped[-1], font=font)[2]
        if width > max_width:
            raise GraphicsError("caption cannot fit without an orphan word")
    return wrapped


def caption_rail(
    lines: list[str],
    canvas: tuple[int, int],
    *,
    brand: dict[str, Any] | None = None,
) -> Image.Image:
    """Lower-third caption card: transparent PNG at canvas size.

    Colors come from the brand config; InDataFlow is never the default.
    """
    brand = brand or {}
    width, height = canvas
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    box_width = int(width * (1 - 2 * MARGIN_X))
    font_size = max(28, width // 18)
    font = _font(font_size)
    fitted = _fit_lines(draw, [line for line in lines if line.strip()], font, box_width)
    if not fitted:
        raise GraphicsError("caption has no text")

    fg = tuple(brand.get("text_color", (255, 255, 255, 255)))
    bg = tuple(brand.get("card_color", (10, 20, 40, 200)))
    pad = font_size // 2
    line_height = int(font_size * 1.35)
    block_height = line_height * len(fitted) + pad * 2
    y0 = int(height * (1 - MARGIN_BOTTOM) - block_height)
    x0 = int(width * MARGIN_X)
    x1 = width - x0
    draw.rounded_rectangle([x0, y0, x1, y0 + block_height], radius=pad, fill=bg)
    baseline = y0 + pad
    for line in fitted:
        draw.text((x0 + pad, baseline), line, font=font, fill=fg)
        baseline += line_height
    return card


def save_png(image: Image.Image, destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG")
    return target
