"""
tests/test_live_photo.py – Unit tests for the Live Photo converter.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image

# Ensure the project root is on the path when running with pytest from any CWD.
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live_photo import (
    _XMP_NS_HEADER,
    _APP1_MARKER,
    _build_xmp_packet,
    _embed_xmp_identifier,
    _remove_existing_xmp,
    create_live_photo,
    _check_dependencies,
)

# Skip markers for optional system tools
_ffmpeg_available = shutil.which("ffmpeg") is not None
_exiftool_available = shutil.which("exiftool") is not None

requires_ffmpeg = unittest.skipUnless(_ffmpeg_available, "ffmpeg not installed")
requires_exiftool = unittest.skipUnless(_exiftool_available, "exiftool not installed")


class TestDependencies(unittest.TestCase):
    @requires_ffmpeg
    def test_ffmpeg_available(self):
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        self.assertEqual(result.returncode, 0, "ffmpeg must be installed")

    @requires_ffmpeg
    def test_check_dependencies_passes(self):
        # Should not raise when ffmpeg is present
        _check_dependencies()


class TestXmpHelpers(unittest.TestCase):
    """Unit tests for the XMP building / injection helpers."""

    def test_build_xmp_packet_contains_identifier(self):
        uid = "DEADBEEF-1234-5678-ABCD-EF0123456789"
        packet = _build_xmp_packet(uid)
        self.assertIn(uid, packet)
        self.assertIn("apple-fi:Identifier", packet)
        self.assertIn("http://ns.apple.com/faceinfo/1.0/", packet)

    @requires_exiftool
    def test_embed_and_read_back(self):
        """Embedded XMP identifier must survive a read-back through exiftool."""
        uid = "TEST-XMP-UUID-0000"
        img = Image.new("RGB", (64, 64), color=(0, 128, 255))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "img.jpg")
            img.save(path, "JPEG")
            _embed_xmp_identifier(path, uid)
            r = subprocess.run(
                ["exiftool", "-XMP-apple-fi:Identifier", "-s3", path],
                capture_output=True, text=True,
            )
            self.assertEqual(r.stdout.strip(), uid)

    @requires_exiftool
    def test_embed_xmp_overwrites_existing(self):
        """Embedding XMP twice should overwrite the first identifier cleanly."""
        img = Image.new("RGB", (32, 32))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "img.jpg")
            img.save(path, "JPEG")
            _embed_xmp_identifier(path, "UUID-FIRST")
            _embed_xmp_identifier(path, "UUID-SECOND")  # overwrites first
            r = subprocess.run(
                ["exiftool", "-XMP-apple-fi:Identifier", "-s3", path],
                capture_output=True, text=True,
            )
            self.assertEqual(r.stdout.strip(), "UUID-SECOND")


@requires_ffmpeg
class TestCreateLivePhoto(unittest.TestCase):
    """Integration-style tests that run the full pipeline on a tiny test image."""

    def _make_test_image(self, directory: str, filename="test_input.jpg") -> str:
        """Create a tiny 64x64 solid-colour JPEG for testing."""
        img = Image.new("RGB", (64, 64), color=(100, 149, 237))
        path = os.path.join(directory, filename)
        img.save(path, "JPEG")
        return path

    def test_returns_two_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_test_image(tmpdir)
            jpeg, mov = create_live_photo(src, tmpdir)
            self.assertTrue(os.path.isfile(jpeg), "JPEG output must exist")
            self.assertTrue(os.path.isfile(mov), "MOV output must exist")

    def test_output_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_test_image(tmpdir)
            jpeg, mov = create_live_photo(src, tmpdir)
            self.assertTrue(jpeg.lower().endswith(".jpg"))
            self.assertTrue(mov.lower().endswith(".mov"))

    def test_output_files_not_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_test_image(tmpdir)
            jpeg, mov = create_live_photo(src, tmpdir)
            self.assertGreater(os.path.getsize(jpeg), 0)
            self.assertGreater(os.path.getsize(mov), 0)

    @requires_exiftool
    def test_matching_content_identifiers(self):
        """Both the JPEG and the MOV must carry the same Content Identifier UUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_test_image(tmpdir)
            jpeg, mov = create_live_photo(src, tmpdir)

            # Read UUID from JPEG XMP
            jpeg_id = subprocess.run(
                ["exiftool", "-XMP-apple-fi:Identifier", "-s3", jpeg],
                capture_output=True, text=True,
            ).stdout.strip()

            # Read UUID from MOV QuickTime Keys
            mov_id = subprocess.run(
                ["exiftool", "-Keys:ContentIdentifier", "-s3", mov],
                capture_output=True, text=True,
            ).stdout.strip()

            self.assertTrue(jpeg_id, "JPEG must have a Content Identifier in XMP")
            self.assertTrue(mov_id, "MOV must have a Content Identifier in QuickTime Keys")
            self.assertEqual(jpeg_id, mov_id, "JPEG and MOV Content Identifiers must match")

    @requires_exiftool
    def test_still_image_time_set(self):
        """The MOV must have a StillImageTime metadata entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_test_image(tmpdir)
            _, mov = create_live_photo(src, tmpdir)

            still_time = subprocess.run(
                ["exiftool", "-Keys:StillImageTime", "-s3", mov],
                capture_output=True, text=True,
            ).stdout.strip()

            self.assertTrue(still_time, "MOV must have Keys:StillImageTime metadata")

    def test_png_input_accepted(self):
        """PNG input should be converted without errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Image.new("RGB", (64, 64), color=(255, 100, 50))
            png_path = os.path.join(tmpdir, "test.png")
            img.save(png_path, "PNG")
            jpeg, mov = create_live_photo(png_path, tmpdir)
            self.assertTrue(os.path.isfile(jpeg))
            self.assertTrue(os.path.isfile(mov))

    @requires_exiftool
    def test_unique_identifiers_per_call(self):
        """Each conversion call should produce a different UUID."""
        with tempfile.TemporaryDirectory() as tmpdir1, \
             tempfile.TemporaryDirectory() as tmpdir2:

            img1 = Image.new("RGB", (64, 64), color=(10, 20, 30))
            src1 = os.path.join(tmpdir1, "a.jpg")
            img1.save(src1)

            img2 = Image.new("RGB", (64, 64), color=(30, 20, 10))
            src2 = os.path.join(tmpdir2, "b.jpg")
            img2.save(src2)

            jpeg1, _ = create_live_photo(src1, tmpdir1)
            jpeg2, _ = create_live_photo(src2, tmpdir2)

            id1 = subprocess.run(
                ["exiftool", "-XMP-apple-fi:Identifier", "-s3", jpeg1],
                capture_output=True, text=True,
            ).stdout.strip()
            id2 = subprocess.run(
                ["exiftool", "-XMP-apple-fi:Identifier", "-s3", jpeg2],
                capture_output=True, text=True,
            ).stdout.strip()

            self.assertNotEqual(id1, id2, "Each conversion must produce a unique UUID")


@requires_ffmpeg
class TestFlaskApp(unittest.TestCase):
    """Tests for the Flask web application."""

    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_index_returns_200(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_index_contains_title(self):
        resp = self.client.get("/")
        self.assertIn(b"Live Photo", resp.data)

    def test_convert_no_file_returns_400(self):
        resp = self.client.post("/convert")
        self.assertEqual(resp.status_code, 400)

    def test_convert_unsupported_type_returns_400(self):
        data = {"photo": (b"fake data", "file.pdf")}
        resp = self.client.post(
            "/convert",
            data=data,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    def test_convert_valid_image_returns_zip(self):
        """Upload a tiny JPEG and expect a ZIP file in response."""
        import io
        img = Image.new("RGB", (64, 64), color=(200, 100, 50))
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        buf.seek(0)

        data = {"photo": (buf, "test.jpg")}
        resp = self.client.post(
            "/convert",
            data=data,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, "application/zip")


if __name__ == "__main__":
    unittest.main()
