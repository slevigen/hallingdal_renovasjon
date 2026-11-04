"""Build the integration's pictures from the official sorting pictograms.

Usage: .venv/bin/python scripts/build_images.py merker

Input is the folder with the official ``*_web.png`` files (pictogram square(s)
with a caption underneath). Output, in custom_components/.../images:

- ``<key>.png``       256x256 entity picture. HA crops it to a circle, so pairs
                      are re-composed side by side on a split background.
- ``card/<key>.png``  the untouched square(s) for the Lovelace card; pairs are
                      two squares with a transparent gap.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

OUT = Path(__file__).parent.parent / "custom_components/hallingdal_renovasjon/images"
SOURCES = {
    "restavfall": "Restavfall_web.png",
    "matavfall": "Matavfall_web.png",
    "papir": "Papp_papir_drikkekartong_web.png",
    "plast": "Plastemballasje_web.png",
    "glass_metall": "Glass_metallemballasje_web.png",
}
PICTURE = 256
TILE = 256
GAP = 12


def squares(path: Path) -> list[Image.Image]:
    """Return the coloured pictogram square(s), without caption or anti-aliased edge."""
    im = Image.open(path).convert("RGB")
    w, _ = im.size

    def coloured(x: int, y: int) -> bool:
        return (
            min(im.getpixel((x, y))) < 200
            or max(im.getpixel((x, y))) - min(im.getpixel((x, y))) > 60
        )

    y = next(yy for yy in range(im.height) if coloured(w // 4, yy))
    row = y + 4
    runs: list[list[int]] = []
    for x in range(w):
        if coloured(x, row):
            if runs and runs[-1][1] == x - 1:
                runs[-1][1] = x
            else:
                runs.append([x, x])
    out = []
    for x0, x1 in (r for r in runs if r[1] - r[0] > 50):
        size = x1 - x0 - 2  # drop 1px anti-aliased border on each side
        out.append(im.crop((x0 + 1, y + 1, x0 + 1 + size, y + 1 + size)))
    return out


def pictogram_mask(square: Image.Image) -> tuple[tuple[int, int, int], Image.Image]:
    bg = square.getpixel((3, 3))
    diff = ImageChops.difference(square, Image.new("RGB", square.size, bg)).convert("L")
    mask = diff.point(lambda v: min(255, v * 2))
    return bg, mask.crop(mask.getbbox())


def entity_picture(parts: list[Image.Image]) -> Image.Image:
    if len(parts) == 1:
        return parts[0].resize((PICTURE, PICTURE), Image.LANCZOS)
    (bl, ml), (br, mr) = pictogram_mask(parts[0]), pictogram_mask(parts[1])
    canvas = Image.new("RGB", (PICTURE, PICTURE), bl)
    canvas.paste(br, (PICTURE // 2, 0, PICTURE, PICTURE))
    # Same scale for both, sized so the wider one fits its half inside the circle.
    scale = min(PICTURE * 0.36 / max(ml.width, mr.width), PICTURE * 0.5 / max(ml.height, mr.height))
    for mask, cx in ((ml, 0.29), (mr, 0.71)):
        m = mask.resize((round(mask.width * scale), round(mask.height * scale)), Image.LANCZOS)
        canvas.paste(
            (255, 255, 255), (round(PICTURE * cx - m.width / 2), round((PICTURE - m.height) / 2)), m
        )
    return canvas


def card_tile(parts: list[Image.Image]) -> Image.Image:
    width = TILE * len(parts) + GAP * (len(parts) - 1)
    tile = Image.new("RGBA", (width, TILE), (0, 0, 0, 0))
    for i, part in enumerate(parts):
        tile.paste(part.resize((TILE, TILE), Image.LANCZOS), (i * (TILE + GAP), 0))
    return tile


def main(source_dir: str) -> None:
    (OUT / "card").mkdir(parents=True, exist_ok=True)
    for key, name in SOURCES.items():
        parts = squares(Path(source_dir) / name)
        assert len(parts) in (1, 2), (name, len(parts))
        entity_picture(parts).save(OUT / f"{key}.png", optimize=True)
        card_tile(parts).save(OUT / "card" / f"{key}.png", optimize=True)
        print(key, [p.size for p in parts])


if __name__ == "__main__":
    main(sys.argv[1])
