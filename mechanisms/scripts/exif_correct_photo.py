#!/usr/bin/env python3
"""exif_correct_photo.py -- pre-rotate a phone photo per its EXIF Orientation tag before an
agent looks at it, so an image-reading tool that shows raw sensor pixels (skipping EXIF) cannot
produce a confidently-wrong orientation read.

WHY THIS EXISTS (2026-08-07, third known instance of this exact failure on this project):
An agent's image-reading tool may render a JPEG's raw pixel grid without applying the file's
EXIF Orientation tag. Phones commonly store the sensor's native landscape capture plus an
Orientation flag (e.g. 6 = "rotate 90 CW to display correctly") rather than pre-rotating the
pixels. Skip the tag and every rotation/mirror judgment made from that render is confidently
wrong -- not obviously wrong, CONFIDENTLY wrong, because the image still looks like a coherent
photo, just rotated. See lessons/exif-orientation-not-calibrated-2026-07-23.md (conductor-bs) --
that lesson already named this exact fix in prose on 2026-07-23; it recurred 2026-08-07 anyway,
which is why this exists as a script instead of a paragraph to remember. Per this repo's own
Voluntary-vs-Structural doctrine (mechanisms/README.md): a lesson that must be recalled at the
right moment is the intervention that already failed twice.

USAGE
    python exif_correct_photo.py <input.jpg> [output.jpg]
    python exif_correct_photo.py <input.jpg> --report-only

    --report-only   print the raw size + EXIF orientation tag/meaning and exit; write nothing.
                    Use this first if you just need to know WHETHER a photo needs correcting.

Without --report-only, writes a corrected copy (default: <input>_corrected.<ext> beside the
input) with EXIF Orientation applied to the pixels and the tag then cleared (so a second
correction pass, or a downstream viewer that DOES honour EXIF, cannot double-rotate it). Prints
the raw size, the tag, and the output path -- read an image-tool's result off the CORRECTED file,
never the original, when you cannot verify the tool applies EXIF itself.

Requires: Pillow (`pip install Pillow`). Read-only on the input; never overwrites it.
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow is required: pip install Pillow", file=sys.stderr)
    sys.exit(2)

ORIENTATION_MEANING = {
    1: "Normal (no rotation)",
    2: "Mirrored horizontal",
    3: "Rotated 180",
    4: "Mirrored vertical",
    5: "Mirrored horizontal + rotated 270 CW",
    6: "Rotated 90 CW",
    7: "Mirrored horizontal + rotated 90 CW",
    8: "Rotated 270 CW (90 CCW)",
}
EXIF_ORIENTATION_TAG = 274


def describe(path: Path) -> tuple[int, int | None]:
    img = Image.open(path)
    orient = img.getexif().get(EXIF_ORIENTATION_TAG)
    return img.size, orient


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="the photo to check/correct")
    ap.add_argument("output", type=Path, nargs="?", help="corrected output path (default: <input>_corrected.<ext>)")
    ap.add_argument("--report-only", action="store_true", help="print orientation info, write nothing")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"no such file: {args.input}", file=sys.stderr)
        return 2

    size, orient = describe(args.input)
    meaning = ORIENTATION_MEANING.get(orient, "no orientation tag / unknown code" if orient is None else f"unknown code {orient}")
    print(f"raw size (w,h): {size}")
    print(f"EXIF Orientation tag ({EXIF_ORIENTATION_TAG}): {orient}")
    print(f"meaning: {meaning}")

    if args.report_only:
        return 0

    if orient is None or orient == 1:
        print("no correction needed (orientation is already normal or absent)")
        return 0

    img = Image.open(args.input)
    fixed = ImageOps.exif_transpose(img)  # applies the tag to pixels, clears it on save
    out = args.output or args.input.with_stem(args.input.stem + "_corrected")
    fixed.save(out)
    print(f"corrected size (w,h): {fixed.size}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
