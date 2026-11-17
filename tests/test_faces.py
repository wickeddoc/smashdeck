# tests/test_faces.py
"""Key faces drawn for real: text faces and picture-with-caption faces."""
import pytest
from PIL import Image

from pages.faces import PictureFace, TextFace, render_face

PICTURE = Image.new("RGB", (640, 640), (120, 40, 160))
WIDE = Image.new("RGB", (1920, 1080), (40, 120, 160))


@pytest.mark.parametrize("face", [
    TextFace("Artist", "Zombie Hyperdrive"),
    TextFace("Artist", "A Band With A Name Far Too Long To Fit On One Small Key"),
    TextFace("Artist", "Supercalifragilisticexpialidocious"),
    PictureFace("Song", "Gigawatt", PICTURE),
    PictureFace("Song", "A title that is much too long for the strip", PICTURE),
    PictureFace("Artist", "Wide photo", WIDE),
    PictureFace("Song", "No cover yet", None),
])
def test_faces_render_as_key_images(face):
    img = render_face(face)
    assert img.size == (144, 144)
    assert img.getbbox() is not None  # not an all-black key


def test_picture_face_without_a_picture_is_its_text_face():
    as_picture = render_face(PictureFace("Artist", "Zombie Hyperdrive", None))
    as_text = render_face(TextFace("Artist", "Zombie Hyperdrive"))
    assert as_picture.tobytes() == as_text.tobytes()


def test_picture_face_fills_the_key_with_the_picture():
    img = render_face(PictureFace("Song", "", PICTURE))  # no caption strip
    assert img.getpixel((72, 130)) == (120, 40, 160)
