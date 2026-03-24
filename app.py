"""
app.py – Flask web application for the Live Photo converter.

Run:
    pip install -r requirements.txt
    python app.py

Then open http://localhost:5000 in a browser.
"""

import os
import tempfile
import zipfile

from flask import Flask, jsonify, render_template, request, send_file

from live_photo import create_live_photo

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "webp", "bmp", "tiff", "tif"}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    if "photo" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["photo"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    if not _allowed(file.filename):
        return jsonify(
            {"error": f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}
        ), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, file.filename)
        file.save(input_path)

        try:
            jpeg_path, mov_path = create_live_photo(input_path, tmpdir)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 500

        zip_path = os.path.join(tmpdir, "live_photo.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(jpeg_path, os.path.basename(jpeg_path))
            zf.write(mov_path, os.path.basename(mov_path))

        return send_file(
            zip_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name="live_photo.zip",
        )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
