"""
live_photo.py – Core logic for converting a standard photo into an Apple Live Photo pair.

An Apple Live Photo consists of two files that share a common Content Identifier UUID:
  1. A JPEG image with  XMP apple-fi:Identifier = <UUID>
     (written directly into a JPEG APP1/XMP segment by this module — no exiftool needed)
  2. A MOV video with   com.apple.quicktime.content.identifier = <UUID>
                        com.apple.quicktime.still-image-time    = 1.0
     (written via FFmpeg's -movflags use_metadata_tags)

Both files must carry the **same** UUID for iOS to recognise them as a Live Photo pair.
"""

import os
import shutil
import struct
import subprocess
import tempfile
import uuid


# JPEG segment constants
_SOI = b"\xff\xd8"
_APP1_MARKER = b"\xff\xe1"
_XMP_NS_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"

# XMP namespace for the Apple Live Photo Content Identifier
_APPLE_FI_NS = "http://ns.apple.com/faceinfo/1.0/"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_live_photo(image_path: str, output_dir: str) -> tuple[str, str]:
    """Convert *image_path* into an Apple Live Photo pair.

    Parameters
    ----------
    image_path : str
        Path to the source image (JPEG, PNG, HEIC, WEBP, BMP, TIFF ...).
    output_dir : str
        Directory where the output JPEG and MOV will be written.

    Returns
    -------
    (jpeg_path, mov_path) : tuple[str, str]
        Absolute paths to the paired JPEG and MOV files.

    Raises
    ------
    RuntimeError
        If ffmpeg is not available or any sub-process fails.
    """
    _check_dependencies()

    identifier = str(uuid.uuid4()).upper()
    base = os.path.splitext(os.path.basename(image_path))[0]
    jpeg_out = os.path.join(output_dir, f"{base}.jpg")
    mov_out = os.path.join(output_dir, f"{base}.mov")

    _convert_to_jpeg(image_path, jpeg_out)
    _create_video_with_metadata(jpeg_out, mov_out, identifier)
    _embed_xmp_identifier(jpeg_out, identifier)

    return jpeg_out, mov_out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_dependencies() -> None:
    """Raise RuntimeError if ffmpeg is not on the PATH."""
    for tool in ("ffmpeg",):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"'{tool}' is required but not found on PATH. "
                f"Install it and try again."
            )


def _convert_to_jpeg(input_path: str, output_path: str) -> None:
    """Convert the source image to a high-quality JPEG.

    FFmpeg cannot overwrite a file that is also an input, so when the resolved
    input and output paths are identical (e.g. a JPEG uploaded into the same
    temp directory) we write to a sibling temp file first, then replace it.
    """
    if os.path.realpath(input_path) == os.path.realpath(output_path):
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(output_path), suffix=".jpg")
        os.close(fd)
        try:
            _run(["ffmpeg", "-y", "-i", input_path, "-qscale:v", "2", tmp])
            shutil.move(tmp, output_path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    else:
        _run(["ffmpeg", "-y", "-i", input_path, "-qscale:v", "2", output_path])


def _create_video_with_metadata(
    image_path: str, output_path: str, identifier: str
) -> None:
    """Generate a 3-second MOV from *image_path* with Live Photo QuickTime metadata.

    FFmpeg's ``-movflags use_metadata_tags`` causes it to write the supplied
    ``-metadata`` entries directly into the QuickTime Keys atom, which is exactly
    where ``com.apple.quicktime.content.identifier`` and
    ``com.apple.quicktime.still-image-time`` must live for iOS to recognise the
    pair as a Live Photo.

    The scale filter ensures even pixel dimensions (required by libx264).
    """
    _run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-t", "3",
        "-r", "30",
        "-movflags", "use_metadata_tags",
        "-metadata", f"com.apple.quicktime.content.identifier={identifier}",
        "-metadata", "com.apple.quicktime.still-image-time=1.0",
        output_path,
    ])


def _embed_xmp_identifier(jpeg_path: str, identifier: str) -> None:
    """Inject the Live Photo Content Identifier into the JPEG XMP APP1 segment.

    The XMP packet uses the ``apple-fi`` namespace
    (``http://ns.apple.com/faceinfo/1.0/``) which carries the ``Identifier``
    tag read by iOS to locate the paired MOV.  This is written directly into
    the JPEG binary so there is no runtime dependency on exiftool.
    """
    xmp_packet = _build_xmp_packet(identifier).encode("utf-8")

    with open(jpeg_path, "rb") as fh:
        jpeg_data = fh.read()

    if jpeg_data[:2] != _SOI:
        raise RuntimeError(f"Not a valid JPEG file: {jpeg_path}")

    # Remove any pre-existing XMP segment
    clean = _remove_existing_xmp(jpeg_data)

    # Build the new APP1 XMP segment
    segment_payload = _XMP_NS_HEADER + xmp_packet
    segment_length = len(segment_payload) + 2  # +2 for the length field itself
    app1_segment = _APP1_MARKER + struct.pack(">H", segment_length) + segment_payload

    # Insert the new APP1 segment immediately after the SOI marker
    patched = clean[:2] + app1_segment + clean[2:]

    with open(jpeg_path, "wb") as fh:
        fh.write(patched)


# ---------------------------------------------------------------------------
# XMP helpers
# ---------------------------------------------------------------------------

def _build_xmp_packet(identifier: str) -> str:
    """Return the minimal XMP packet string carrying the apple-fi:Identifier."""
    return (
        '<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about=""\n'
        f'        xmlns:apple-fi="{_APPLE_FI_NS}">\n'
        f"      <apple-fi:Identifier>{identifier}</apple-fi:Identifier>\n"
        "    </rdf:Description>\n"
        "  </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>'
    )


def _remove_existing_xmp(data: bytes) -> bytes:
    """Return *data* with any existing XMP APP1 segment stripped out."""
    result = bytearray(data[:2])  # preserve SOI
    i = 2
    while i < len(data):
        if i + 1 >= len(data):
            result.extend(data[i:])
            break
        marker = data[i : i + 2]
        # SOI / EOI / standalone markers have no length field
        if marker == b"\xff\xd9":  # EOI
            result.extend(data[i:])
            break
        # Markers without a length field (stand-alone)
        if marker[0] != 0xFF or marker[1] in (0x00, 0xFF):
            result.extend(data[i : i + 1])
            i += 1
            continue
        if i + 4 > len(data):
            result.extend(data[i:])
            break
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        end = i + 2 + seg_len
        # Drop APP1 segments that carry XMP data
        if marker == _APP1_MARKER:
            payload_start = i + 4
            if data[payload_start : payload_start + len(_XMP_NS_HEADER)] == _XMP_NS_HEADER:
                i = end
                continue
        result.extend(data[i:end])
        i = end
    return bytes(result)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
