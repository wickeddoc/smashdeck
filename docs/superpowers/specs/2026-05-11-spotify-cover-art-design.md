# Spotify cover-art display

**Date:** 2026-05-11
**Status:** Approved design, awaiting implementation plan
**Scope:** Display the currently playing track's album cover art on the
Stream Deck's Spotify page, replacing the album-name text label on key 31.

## Goals

- Show the cover art of the current track on key 31 of the Spotify page.
- Update the art automatically when the track changes (same trigger as the
  existing PropertiesChanged listener).
- Avoid unnecessary HTTPS round-trips when the art URL hasn't changed.
- Add no new pip dependencies.
- Gracefully fall back to a blank key when art is unavailable.

## Non-goals

- No bigger layout (no 2×2 tile, no multi-key cover). Single key 31 only.
- No new caching infrastructure beyond "last fetched URL" memoisation.
- No retry/backoff logic. A failed fetch becomes a blank key until the next
  track-change signal naturally re-tries.
- No async/asyncio. The fetch runs synchronously on the existing listener
  thread.
- No changes to the artist (key 15) or title (key 23) labels.
- No on-disk caching of fetched images.

## Design decisions (resolved during brainstorming)

1. **Layout:** Replace key 31's album-name text with the cover image. Artist
   (15) and title (23) labels stay.
2. **HTTP fetch:** Use `urllib.request.urlopen()` from the stdlib. No new deps.
3. **Concurrency:** Fetch inline in the existing listener thread. First render
   after a track change is delayed by the HTTPS round-trip (~100–300 ms),
   but the UI is already off the main render path, so this is acceptable.
4. **Cache:** Just remember the last fetched URL and its decoded image.
   Re-fetches only happen when the URL actually changes.

## Architecture

Three small surfaces change.

### `SpotifyMpris` (in `pages/spotify.py`)

- `PlayerSnapshot` gains a new field: `art_url: str = ""`.
- `snapshot()`'s metadata block adds extraction of `mpris:artUrl`. If the
  value is a non-empty string, it is stored on the snapshot; otherwise the
  default empty string remains.

### `SpotifyPage` (in `pages/spotify.py`)

New attributes on the page (initialised in `__init__` to `""` and `None`):

```python
self._art_url: str = ""
self._art_image: Optional[Image.Image] = None
```

New helper method:

```python
@staticmethod
def _fetch_art(url: str) -> Optional[Image.Image]:
    """Fetch and decode a cover-art image. Returns None on any failure."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        traceback.print_exc()
        return None
```

The flow inside `_listen` (and the initial `activate()` snapshot path) is
extended to update `_art_url` / `_art_image` when the snapshot's `art_url`
differs from the cached one. The pair is updated atomically:

```python
if snap.art_url != self._art_url:
    self._art_url = snap.art_url
    self._art_image = self._fetch_art(snap.art_url)
```

`render(snap)` no longer passes a label to key 31. It passes the PIL image
(possibly `None`):

```python
self.ctrl.set_key_image(31, pil_image=self._art_image)
```

When `_art_image` is `None`, key 31 renders blank (this matches the
existing "no album text" behaviour).

### `main.py` controller

`set_key_image` gains an optional parameter:

```python
def set_key_image(
    self,
    key,
    icon_filename=None,
    label=None,
    color=(0, 0, 0),
    highlight=None,
    pil_image=None,
):
```

If `pil_image` is provided, it becomes the source image instead of opening
`icon_filename` or creating a blank. `PILHelper.create_scaled_key_image`
handles the resize from whatever size Spotify served (commonly 300×300 or
640×640) down to the deck's native key size (144×144 on XL).

Precedence when multiple sources are supplied:

```
pil_image (if not None)  >  icon_filename (if not None)  >  blank colour
```

All existing call sites continue to work unchanged because `pil_image`
defaults to `None`.

## Data flow

```
PropertiesChanged signal
  └─ _listen drains queue
     └─ mpris.snapshot()  (now reads mpris:artUrl)
        └─ if snap.art_url != self._art_url:
             pil = _fetch_art(snap.art_url)        # ~100-300 ms HTTPS GET
             self._art_url   = snap.art_url
             self._art_image = pil
        └─ render(snap)
             └─ set_key_image(31, pil_image=self._art_image)
                └─ PILHelper scales the image to 144×144
                └─ Stream Deck draws it
```

On signals that do not change the art URL (volume changes, position
updates, shuffle/loop toggles), the URL comparison short-circuits and no
network traffic happens.

## Error handling

- **No `mpris:artUrl` in Metadata.** `snap.art_url == ""`. `_fetch_art`
  returns `None` immediately. Key 31 renders blank.
- **HTTPS fetch fails** (timeout, network down, non-200, malformed bytes,
  Pillow decode error). `_fetch_art`'s broad `except Exception` catches it,
  prints a traceback, and returns `None`. The page does not crash. Key 31
  goes blank for that track; the next signal with a different URL will try
  again.
- **Spotify quits.** Snapshot returns the safe-default `PlayerSnapshot()`
  with `art_url == ""`. Same as "no art" path.
- **Track change while a fetch is in flight.** The fetch is inline, so a
  new signal cannot start until the current `_listen` iteration returns.
  Worst case: one signal arrives during a slow fetch and waits in the
  queue for up to 5 s (the fetch timeout). Acceptable — the queue is
  drained on the next iteration. This is a conscious trade-off for the
  simpler single-thread design.
- **Concurrency.** The listener thread is the only writer of `_art_url`
  and `_art_image`. The main thread reads `_art_image` indirectly through
  `render()` when a key is pressed. Under the GIL, attribute assignment is
  atomic, so a concurrent read sees either the old or the new value — never
  a partial state. At worst, one render frame is stale.

## Scope notes

- **No bounded LRU cache.** The "last URL" memoisation is enough to avoid
  re-fetches during a single album playthrough. Cross-album scrubbing will
  re-fetch — that is an acceptable cost for now.
- **No new pip deps.** `urllib.request` and `io.BytesIO` are stdlib;
  Pillow is already a project dependency.
- **No changes to `requirements.txt` or `CLAUDE.md`.** Nothing
  architecturally new is exposed to users.
- **No new icon assets.** Cover images come from Spotify's CDN at runtime.

## Testing

Manual verification on the connected Stream Deck XL with Spotify running:

1. Open the Spotify page → key 31 shows the cover art of the current
   track, no album text.
2. Skip to the next track → within ~1 s key 31 updates to the new cover.
3. Press play/pause on the deck → cover stays put (URL didn't change, no
   refetch).
4. Network down (e.g. `nmcli networking off`) → next track change leaves
   key 31 blank without crashing; a `URLError` traceback appears on
   stderr.
5. Network restored, next track change → cover reappears.
6. Quit Spotify → key 31 goes blank along with the rest of the page state.
7. Open Spotify, start playback → cover appears within a few seconds.

No automated tests are added; the project still has none, consistent with
the prior Spotify-DBus and icon-resolution changes.

## File summary

- **Modify:** `pages/spotify.py` —
  - `PlayerSnapshot.art_url: str = ""`
  - `snapshot()` extracts `mpris:artUrl`
  - `SpotifyPage.__init__` adds `_art_url` and `_art_image`
  - `SpotifyPage._fetch_art()` new helper
  - `_listen()` and `activate()` paths update the art on URL change
  - `render(snap)` passes `_art_image` to `set_key_image(31, …)` instead
    of a text label
  - New imports: `io`, `urllib.request`
- **Modify:** `main.py` —
  - `set_key_image` gains `pil_image: Optional[Image.Image] = None`
    parameter; precedence is pil_image > icon_filename > blank.

No other files touched.

## Out of scope / future work

- Multi-key cover-art tile (the 2×2 design alternative).
- Bounded LRU image cache.
- Asynchronous / background-thread fetching (would remove the up-to-300 ms
  delay on first render after a track change).
- On-disk cache so cover art survives app restarts.
- Other MPRIS players (Tidal, YouTube Music, etc.) — code is Spotify-only
  by design.
