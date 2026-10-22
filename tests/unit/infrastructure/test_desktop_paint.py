"""When a remote-surface screenshot counts as painted.

The capture polls an element screenshot and keeps it once a 32 by 32 sample of that
PNG has at least 8 pixels whose strongest channel is at least 24. These cases build
the PNG themselves, so the count does not depend on a browser's rasteriser.
"""

import struct
import zlib

import pytest

from horizon_tracker.infrastructure.horizon_playwright import _png_frame_is_nonblank

_SIDE = 32
_LIT = 24


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _apply_filter(filter_type: int, raw: bytes, previous: bytes, channels: int) -> bytes:
    """The PNG filter that ``_png_frame_is_nonblank`` has to undo."""
    stored = bytearray(len(raw))
    for index, value in enumerate(raw):
        left = raw[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        else:
            predictor = _paeth(left, up, up_left)
        stored[index] = (value - predictor) & 255
    return bytes(stored)


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def _png(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int, int]],
    *,
    filter_type: int = 0,
) -> bytes:
    """An 8-bit RGBA PNG of ``pixels`` in row-major order, one filter on every row."""
    channels = 4
    raw_rows: list[bytes] = []
    previous = bytes(width * channels)
    filtered = bytearray()
    for y in range(height):
        raw = bytearray()
        for x in range(width):
            raw.extend(pixels[y * width + x])
        raw_rows.append(bytes(raw))
        filtered.append(filter_type)
        filtered.extend(_apply_filter(filter_type, raw_rows[-1], previous, channels))
        previous = raw_rows[-1]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(bytes(filtered))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )


def _frame(
    pixels: list[tuple[int, int, int, int]], *, side: int = _SIDE, filter_type: int = 0
) -> bytes:
    return _png(side, side, pixels, filter_type=filter_type)


def _black() -> tuple[int, int, int, int]:
    return (0, 0, 0, 255)


def _with_lit(count: int, pixel: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    """``count`` copies of ``pixel`` at the start of the first row, and black elsewhere."""
    pixels = [_black() for _ in range(_SIDE * _SIDE)]
    for index in range(count):
        pixels[index] = pixel
    return pixels


def test_seven_lit_pixels_are_still_blank() -> None:
    assert _png_frame_is_nonblank(_frame(_with_lit(7, (_LIT, 0, 0, 255)))) is False


def test_eight_lit_pixels_are_a_painted_frame() -> None:
    assert _png_frame_is_nonblank(_frame(_with_lit(8, (_LIT, 0, 0, 255)))) is True


def test_a_channel_below_the_bar_does_not_count() -> None:
    dim = (_LIT - 1, _LIT - 1, _LIT - 1, 255)
    assert _png_frame_is_nonblank(_frame(_with_lit(8, dim))) is False


def test_alpha_does_not_count_and_does_not_hide_a_lit_channel() -> None:
    opaque_black = _with_lit(8, (0, 0, 0, 255))
    clear_red = _with_lit(8, (_LIT, 0, 0, 0))

    assert _png_frame_is_nonblank(_frame(opaque_black)) is False
    assert _png_frame_is_nonblank(_frame(clear_red)) is True


def test_a_frame_lit_only_past_the_top_left_sample_is_painted() -> None:
    # 64 by 32. A top-left 32 by 32 crop is black. The sample grid reaches the lit half.
    width, height = 64, 32
    pixels = [(0, 0, 0, 255) for _ in range(width * height)]
    for y in range(height):
        for x in range(width // 2, width):
            pixels[y * width + x] = (255, 0, 0, 255)

    assert _png_frame_is_nonblank(_png(width, height, pixels)) is True


@pytest.mark.parametrize("filter_type", [1, 2, 3, 4])
def test_a_filtered_row_is_read_after_the_filter_is_undone(filter_type: int) -> None:
    # Eight pixels clear the bar only after the filter is reversed. The stored bytes
    # alone stay under it, so a decoder that skips the filter reports a blank frame.
    # Sub sits on the first row. The other filters sit on the last row, over a dim
    # row, so the row after a bright one cannot wrap into a lit stored byte.
    pixels = [_black() for _ in range(_SIDE * _SIDE)]
    if filter_type == 1:
        for index in range(8):
            pixels[index] = (_LIT, 0, 0, 255)
    else:
        above = (_SIDE - 2) * _SIDE
        last = (_SIDE - 1) * _SIDE
        for offset in range(8):
            pixels[above + offset] = (20, 0, 0, 255)
            pixels[last + offset] = (40, 0, 0, 255)

    assert _png_frame_is_nonblank(_frame(pixels, filter_type=filter_type)) is True


def test_bytes_that_are_not_a_png_are_refused() -> None:
    with pytest.raises(ValueError):
        _png_frame_is_nonblank(b"not a png")
