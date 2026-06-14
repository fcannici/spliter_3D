from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    p = argparse.ArgumentParser()
    p.add_argument("frames_dir")
    p.add_argument("--out")
    p.add_argument("--cols", type=int, default=5)
    p.add_argument("--thumb-width", type=int, default=320)
    args = p.parse_args()

    frames = sorted(Path(args.frames_dir).glob("*.jpg"))
    if not frames:
        raise SystemExit("no frames")
    thumbs = []
    for f in frames:
        img = Image.open(f).convert("RGB")
        ratio = args.thumb_width / img.width
        size = (args.thumb_width, int(img.height * ratio))
        img = img.resize(size)
        canvas = Image.new("RGB", (size[0], size[1] + 22), "white")
        canvas.paste(img, (0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((4, size[1] + 4), f.name, fill="black")
        thumbs.append(canvas)

    cols = args.cols
    rows = (len(thumbs) + cols - 1) // cols
    w = cols * thumbs[0].width
    h = rows * thumbs[0].height
    sheet = Image.new("RGB", (w, h), "white")
    for i, img in enumerate(thumbs):
        x = (i % cols) * img.width
        y = (i // cols) * img.height
        sheet.paste(img, (x, y))
    out = Path(args.out) if args.out else Path(args.frames_dir).with_suffix(".contact.jpg")
    sheet.save(out, quality=90)
    print(out)


if __name__ == "__main__":
    main()
