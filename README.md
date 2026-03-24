# Live Photo Converter

Convert any standard photo into an **Apple Live Photo** — a paired JPEG + MOV file
that iOS recognises as a Live Photo and lets you send on iMessage.

---

## How it works

An Apple Live Photo is two files that share the same **Content Identifier UUID**:

| File | Metadata |
|------|---------|
| `photo.jpg` | XMP `apple-fi:Identifier = <UUID>` (injected directly into the JPEG APP1 segment) |
| `photo.mov` | `com.apple.quicktime.content.identifier = <UUID>` and `com.apple.quicktime.still-image-time = 1.0` (written via FFmpeg QuickTime Keys) |

This tool generates a 3-second video from the still image, embeds matching UUIDs in
both files, and packages them in a ZIP for download.

---

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) – video generation and MOV metadata

Install FFmpeg (macOS):

```bash
brew install ffmpeg
```

Install FFmpeg (Ubuntu/Debian):

```bash
sudo apt-get install ffmpeg
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Web app

```bash
python app.py
```

Open <http://localhost:5000>, drag-and-drop a photo, click **Convert**, and download the ZIP.

---

## Command-line usage

```bash
python convert.py photo.jpg
# Output: photo.jpg  +  photo.mov  (in the same directory)

python convert.py photo.png --output-dir ./output
```

---

## Using the Live Photo on iPhone

1. Unzip the downloaded archive — you get `photo.jpg` and `photo.mov`.
2. **AirDrop both files together** to your iPhone (select both before sharing).
3. iOS automatically saves them as a Live Photo in your Camera Roll.
4. Open iMessage → tap the photo icon → select the Live Photo → send! 🎉

> **Tip:** You can also use iCloud Drive to transfer both files, then save them from
> the Files app. iOS recognises the pair as a Live Photo when both files have the same
> base name and the matching Content Identifier in their metadata.

---

## Running tests

```bash
python -m pytest tests/ -v
```
