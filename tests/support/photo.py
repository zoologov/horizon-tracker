"""Reads a photo the adapter saved: the colours on a grid across it, decoded by a browser page.

The page decodes the PNG (an ``Image`` drawn onto a 2D canvas), so a test asks the same
engine that encoded the frame and carries no PNG codec of its own.
"""

import base64
from typing import cast

from playwright.sync_api import Page

Colour = tuple[int, int, int]

# Each sample is taken at the centre of one cell of a GRID by GRID partition of the photo.
GRID = 8
# How far a channel may stray from the expected colour and still count as it.
CHANNEL_TOLERANCE = 8

_SAMPLE = """async ({ data, grid }) => {
    const image = new Image();
    image.src = "data:image/png;base64," + data;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0);
    const samples = [];
    for (let row = 0; row < grid; row += 1) {
        for (let column = 0; column < grid; column += 1) {
            const x = Math.floor(((column + 0.5) * image.width) / grid);
            const y = Math.floor(((row + 0.5) * image.height) / grid);
            const pixel = context.getImageData(x, y, 1, 1).data;
            samples.push([pixel[0], pixel[1], pixel[2]]);
        }
    }
    return samples;
}"""


def grid_colours(page: Page, png: bytes) -> list[Colour]:
    """The RGB colour at the centre of every cell of a GRID by GRID partition of ``png``."""
    data = base64.b64encode(png).decode("ascii")
    samples = cast(list[list[int]], page.evaluate(_SAMPLE, {"data": data, "grid": GRID}))
    return [(red, green, blue) for red, green, blue in samples]


def colours_unlike(page: Page, png: bytes, expected: Colour) -> list[Colour]:
    """The grid colours of ``png`` that are not ``expected``, within CHANNEL_TOLERANCE."""
    return [
        colour
        for colour in grid_colours(page, png)
        if any(
            abs(got - want) > CHANNEL_TOLERANCE for got, want in zip(colour, expected, strict=True)
        )
    ]
