# pages/faces.py
"""Key faces shared by pages that show text or pictures: a label with
wrapped text (TextFace), and a picture filling the key with a caption strip
(PictureFace), e.g. album art or an artist photo. render_face draws them, and
the Monitor page's tiles, as 144 px images for ``set_key_image(pil_image=)``.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageOps

from pages.monitor.tiles import BOLD, FONT, GREY, SIZE, WHITE, fit_font, render_tile

SPOTIFY_GREEN = (30, 215, 96)
MIN_TEXT = 16  # px at 144; smaller is unreadable once scaled to the XL's 96 px


@dataclass(frozen=True)
class TextFace:
    label: str
    text: str


@dataclass(frozen=True)
class PictureFace:
    """The picture with the caption on a strip; without a picture (not
    fetched yet, or none exists) the same key as TextFace(label, caption)."""
    label: str
    caption: str
    picture: Image.Image | None


# --- drawing -------------------------------------------------------------------

def _ellipsize(text: str, font, width: int) -> str:
    if font.getlength(text) <= width:
        return text
    while text and font.getlength(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(text: str, font, width: int, max_lines: int) -> list[str]:
    """Greedy word wrap; a too-long last line ends in an ellipsis."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and font.getlength(trial) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(lines[-1] + "…", font, width)
    return lines


def _text_image(face: TextFace) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), "black")
    d = ImageDraw.Draw(img)
    mid = SIZE // 2
    d.text((mid, 21), face.label, font=fit_font(face.label, FONT, 19, SIZE - 8),
           fill=GREY, anchor="mm")
    width = SIZE - 12
    lines = _wrap(face.text, fit_font("", BOLD, 26, width), width, max_lines=3)
    top = 82 - (len(lines) - 1) * 16
    for i, line in enumerate(lines):
        font = fit_font(line, BOLD, 26, width, min_size=MIN_TEXT)
        d.text((mid, top + i * 32), _ellipsize(line, font, width), font=font,
               fill=SPOTIFY_GREEN, anchor="mm")
    return img


def _picture_image(face: PictureFace) -> Image.Image:
    if face.picture is None:
        return _text_image(TextFace(face.label, face.caption))
    img = ImageOps.fit(face.picture.convert("RGB"), (SIZE, SIZE))
    if face.caption:
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([(0, SIZE - 34), (SIZE, SIZE)], fill=(0, 0, 0, 190))
        font = fit_font(face.caption, BOLD, 20, SIZE - 8, min_size=MIN_TEXT)
        d.text((SIZE // 2, SIZE - 17), _ellipsize(face.caption, font, SIZE - 8),
               font=font, fill=WHITE, anchor="mm")
    return img


def render_face(face) -> Image.Image:
    """A 144 px key image for a text face, picture face or monitor tile."""
    if isinstance(face, TextFace):
        return _text_image(face)
    if isinstance(face, PictureFace):
        return _picture_image(face)
    return render_tile(face)
