"""
convert.py – Command-line interface for the Live Photo converter.

Usage:
    python convert.py <image> [--output-dir DIR]

Examples:
    python convert.py photo.jpg
    python convert.py photo.png --output-dir ./output
"""

import argparse
import os
import sys

from live_photo import create_live_photo


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a standard photo into an Apple Live Photo pair (JPEG + MOV)."
    )
    parser.add_argument("image", help="Path to the source image file.")
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Directory to write the output files (default: same directory as the input image).",
    )
    args = parser.parse_args()

    image_path = os.path.abspath(args.image)
    if not os.path.isfile(image_path):
        print(f"Error: file not found: {image_path}", file=sys.stderr)
        return 1

    output_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.dirname(image_path)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Converting '{image_path}' …")
    try:
        jpeg_path, mov_path = create_live_photo(image_path, output_dir)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Done!")
    print(f"  Still image : {jpeg_path}")
    print(f"  Video clip  : {mov_path}")
    print()
    print("Transfer both files to your iPhone (e.g. via AirDrop or iCloud Drive).")
    print("iOS will recognise them as a Live Photo when they share the same name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
