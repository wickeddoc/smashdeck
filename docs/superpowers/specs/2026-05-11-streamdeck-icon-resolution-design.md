# Stream Deck icon resolution: native 144×144 with multi-model support

**Date:** 2026-05-11
**Status:** Approved design, awaiting implementation plan
**Scope:** Make the icon set natively rendered at the Stream Deck XL resolution
(144×144), while remaining usable on smaller models (Original, Mini) by relying
on the Stream Deck library's built-in scaler. Identify the connected deck at
startup.

## Goals

- Stop relying on implicit 72→144 upscaling of icon PNGs on the XL.
- Generate icons natively at 144×144 with sharp lines and proportions.
- Detect and log the connected Stream Deck model and its native key size.
- Continue to work on Original / Mini / Mk.2 decks via runtime downscale.
- Remove the magic number `72` from `main.py`'s blank-source fallback.

## Non-goals

- Changing fonts, label margins, or any other visual layout parameters.
- Hard-failing when a non-XL deck is connected.
- Re-designing any icon. Each icon's shape stays identical; only its
  resolution doubles.
- Maintaining a second 72×72 icon set on disk. The library scales as needed.

## Design decisions (resolved during brainstorming)

1. **Model behavior:** Accept any visual Stream Deck. Log the model and its
   reported native key size at startup. Unknown models print a warning but
   continue.
2. **Storage:** One icon set on disk at 144×144. Smaller decks get downscaled
   versions at render time via `PILHelper.create_scaled_key_image`.
3. **Coordinate strategy:** Mechanically double every coordinate literal in
   `generate_icons.py`. The internal design coordinates become 144-based.
4. **SIZE override:** Allow `SIZE` in `generate_icons.py` to be overridden by
   the `ICON_SIZE` environment variable, defaulting to 144. Useful if a user
   really wants to regenerate at a different size.

## Architecture

Three files change. Nothing else moves.

### `generate_icons.py`

- `SIZE = int(os.environ.get("ICON_SIZE", 144))`.
- Every numeric coordinate inside icon-drawing functions is multiplied by 2
  relative to the existing 72-based values. Example: an ellipse from `(16, 10)`
  to `(56, 50)` becomes `(32, 20)` to `(112, 100)`. Line widths and font sizes
  also double.
- Print line at the top updated: `"Generating Stream Deck icons ({SIZE}×{SIZE})…"`.

### `main.py`

- After `self.deck.open()`, read the deck's identity and native size:

  ```python
  deck_type = self.deck.deck_type()
  key_size = self.deck.key_image_format()["size"]  # tuple (w, h)
  print(f"Stream Deck: {deck_type} (key images: {key_size[0]}×{key_size[1]})")
  ```

- Save `self._key_size = key_size` on the controller.
- A small whitelist of known model substrings is used purely for a friendlier
  startup message. Anything not matching prints
  `"Warning: untested Stream Deck model '<name>'; proceeding anyway."` and
  continues. The whitelist: `"XL"`, `"Mk.2"`, `"Original"`, `"Mini"`,
  `"Plus"`. Match is case-insensitive substring on `deck.deck_type()`.
- `set_key_image`'s blank-source line changes from
  `Image.new("RGB", (72, 72), color)` to
  `Image.new("RGB", self._key_size, color)`. The image is still passed to
  `PILHelper.create_scaled_key_image`, which will no-op when the source
  already matches the deck's native size.

### `icons/`

All existing PNGs are regenerated at 144×144 by running the updated
`generate_icons.py`. No new icon names are added. Old 72-pixel PNGs are
overwritten in place.

### `CLAUDE.md`

The "Regenerating Icons" section is updated:

- "Icons are 72x72 PNGs…" → "Icons are 144×144 PNGs (Stream Deck XL native).
  Smaller decks get downscaled automatically by the library at render time."
- Add a one-liner: `ICON_SIZE=72 python generate_icons.py` to regenerate at a
  different resolution if needed.

## Multi-deck behavior

The Stream Deck library's `key_image_format()` returns the deck's native key
size. `PILHelper.create_scaled_key_image` already resizes any source image to
that native size. No conditional branching in our code is needed.

Behavior matrix:

| Deck model           | Native key size | Source (on disk) | Render-time op    |
| -------------------- | --------------- | ---------------- | ----------------- |
| Stream Deck XL       | 144×144         | 144×144          | no scaling (1:1)  |
| Stream Deck Mk.2     | 72×72           | 144×144          | 2:1 downscale     |
| Stream Deck Original | 72×72           | 144×144          | 2:1 downscale     |
| Stream Deck Mini     | 80×80           | 144×144          | downscale         |
| Stream Deck Plus     | 120×120         | 144×144          | downscale         |
| (unknown)            | per the device  | 144×144          | library's choice  |

Downscaling 144→72 via Pillow's default resampler produces a noticeably
sharper result than today's implicit 72→144 upscale on the XL.

## Error handling

- **No Stream Deck found.** Existing behavior preserved: `RuntimeError("No Stream Deck found")` is raised by `start()`. No change.
- **Unknown model.** Warning printed, app continues. The library may still
  produce reasonable output.
- **Deck reports no visual output (`deck.is_visual() is False`).** Out of
  scope. The app already assumes a visual deck; no new check is added here.
- **`generate_icons.py` with bad `ICON_SIZE`.** A non-integer value will
  raise `ValueError` from `int()`. Acceptable: the script is run manually
  and the message is clear.

## Concurrency

No new threads or shared state. All changes are synchronous and one-shot.

## Testing

Manual verification on the connected Stream Deck XL:

1. `python generate_icons.py` → outputs 144×144 PNGs to `icons/`.
   `file icons/play.png` reports `144 x 144`.
2. `ICON_SIZE=72 python generate_icons.py` → outputs 72×72 PNGs (sanity check
   that the override path works). Then re-run with the default to restore 144.
3. `python main.py` → prints a startup line like
   `Stream Deck: Stream Deck XL (key images: 144×144)`.
4. Visual check: nav bar icons and Spotify page icons look sharper than before
   on the XL (no blur from upscaling).
5. Labels still render at the bottom of keys (font/margin behavior unchanged).
6. Switching pages still works; nothing else is affected.

No automated tests are added; the project still has none, consistent with the
prior Spotify-DBus change.

## File summary

- **Modify:** `generate_icons.py` — `SIZE` parameterized, every coord doubled.
- **Modify:** `main.py` — startup logging, `_key_size` attribute, blank-source
  uses the deck's native size.
- **Modify:** `CLAUDE.md` — icon-size doc update and `ICON_SIZE` hint.
- **Regenerate:** all PNGs in `icons/`.

## Out of scope / future work

- Cover-art display feature (separate request, not bundled).
- Font / label-margin tuning for the higher resolution. The current font
  feels small on 144×144 but the visual choice has been acceptable so far;
  bumping it can be a follow-up if desired.
- A separate fixed 72×72 icon set on disk for smaller decks.
