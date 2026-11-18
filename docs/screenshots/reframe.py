"""Square up a photo of the Stream Deck XL for the README.

Finds the 32 key screens, fits a perspective transform that puts them on an
even 8x4 grid, and crops every photo to the same frame (logo to bottom row),
so the screenshots line up. The result is a small JPEG without EXIF, so no
GPS position or camera details end up in the repo.

Needs numpy and OpenCV, which SmashDeck itself doesn't, so run it with uv:

    uv run --no-project --with numpy --with opencv-python-headless --with pillow \
        python docs/screenshots/reframe.py PHOTO.jpg docs/screenshots/page_NAME.jpg

Take the photo straight on, with the whole deck in the picture.
"""
import sys

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

PREVIEW = 6                 # keys are found on a 1/6 size copy
THRESHOLDS = (45, 40, 50, 35, 55, 30)   # brightness that separates screens from bezels
P = 184                     # key pitch in the result, px
KY = 1.03                   # vertical / horizontal key pitch of the XL
LEFT, RIGHT = 0.75, 0.75    # frame margins around the outer key centres, in pitches
TOP, BOTTOM = 1.40, 0.80
OVERSAMPLE = 4              # warp at 4x, then downscale


def key_screens(small, threshold):
    """Centres of the bright, roughly square blobs, row by row."""
    value = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[:, :, 2]
    mask = cv2.morphologyEx((value > threshold).astype(np.uint8), cv2.MORPH_OPEN,
                            np.ones((7, 7), np.uint8))
    count, _, stats, centres = cv2.connectedComponentsWithStats(mask)
    blobs = [centres[i] for i in range(1, count)
             if 4000 < stats[i][4] < 16000 and 0.7 < stats[i][2] / stats[i][3] < 1.4]
    if len(blobs) != 32:
        return None
    blobs.sort(key=lambda c: c[1])
    rows = [sorted(blobs[r * 8:(r + 1) * 8], key=lambda c: c[0]) for r in range(4)]
    return np.array([c for row in rows for c in row], dtype=np.float64) * PREVIEW


def find_keys(photo):
    small = cv2.resize(photo, (photo.shape[1] // PREVIEW, photo.shape[0] // PREVIEW),
                       interpolation=cv2.INTER_AREA)
    for threshold in THRESHOLDS:
        found = key_screens(small, threshold)
        if found is not None:
            return found
    raise SystemExit("couldn't find all 32 keys; is the whole deck in the photo?")


def reframe(src, out):
    photo = cv2.imread(src)
    if photo is None:
        raise SystemExit(f"can't read {src}")
    found = find_keys(photo)
    s = OVERSAMPLE
    grid = np.array([((LEFT + c) * P * s, (TOP + r) * P * KY * s)
                     for r in range(4) for c in range(8)], dtype=np.float64)
    H, inliers = cv2.findHomography(found, grid, cv2.RANSAC, 0.06 * P * s)
    if H is None or inliers.sum() < 24:
        raise SystemExit("the keys don't form a grid; take the photo straight on")
    w = round((LEFT + 7 + RIGHT) * P)
    h = round((TOP + 3 + BOTTOM) * P * KY)
    inside = cv2.warpPerspective(np.full(photo.shape[:2], 255, np.uint8), H, (w * s, h * s),
                                 flags=cv2.INTER_NEAREST)
    if (inside == 0).any():
        raise SystemExit("the frame reaches past the photo's edge; leave more room around the deck")
    big = cv2.warpPerspective(photo, H, (w * s, h * s), flags=cv2.INTER_LINEAR)
    small = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)
    image = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    image.save(out, "JPEG", quality=85, optimize=True, progressive=True)  # no EXIF/XMP/ICC
    print(f"{out}: {w}x{h}, {int(inliers.sum())}/32 keys on the grid")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    reframe(sys.argv[1], sys.argv[2])
