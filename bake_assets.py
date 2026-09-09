"""
Build script for the SDC Kiosk App.

Reads the editable source file (`SDC Kiosk App.html`), inlines every image,
icon, and logo asset as a compressed base64 data URI, and writes the result
to `SDC Kiosk App - Self Contained.html` -- the file that actually gets
deployed to the kiosk. Videos are intentionally left as relative file paths
(they live in the separate, gitignored `Video Files/` folder on the kiosk
machine and are far too large to inline).

Usage:
    pip install Pillow   # first time only
    python bake_assets.py
"""

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
SRC_HTML = ROOT / "SDC Kiosk App.html"
OUT_HTML = ROOT / "SDC Kiosk App - Self Contained.html"

# (folder name, max dimension in px, output format, quality)
# Photos are shown at up to ~420px tall / full column width, so 1600px on
# the long edge is generous headroom even on a retina display.
IMAGE_FOLDERS = [
    {"dir": "Image Files", "max_dim": 1600, "format": "JPEG", "quality": 78},
    {"dir": "Customer Logo Files", "max_dim": 500, "format": None, "quality": 85},
]
ICON_DIR = "Icon Files"  # SVGs -- embedded as-is, no raster resizing
ROOT_LOGO = "Blue SDC Logo.png"  # referenced directly by filename in the JSX, not via a helper
ROOT_LOGO_MAX_DIM = 600


def encode_svg(path: Path) -> str:
    data = path.read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")


def encode_raster(path: Path, max_dim: int, force_format: str | None, quality: int) -> str:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)  # bake in camera rotation before we drop the EXIF that stores it

        if max(im.size) > max_dim:
            im.thumbnail((max_dim, max_dim), Image.LANCZOS)

        out_format = force_format or ("PNG" if im.mode in ("RGBA", "P") else "JPEG")

        buf = io.BytesIO()
        if out_format == "JPEG":
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
            mime = "image/jpeg"
        else:
            im.save(buf, format="PNG", optimize=True)
            mime = "image/png"

        return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_asset_map() -> dict:
    assets = {}

    for folder in IMAGE_FOLDERS:
        dir_path = ROOT / folder["dir"]
        if not dir_path.is_dir():
            continue
        for f in sorted(dir_path.iterdir()):
            if not f.is_file():
                continue
            key = f"{folder['dir']}/{f.name}"
            if f.suffix.lower() == ".svg":
                assets[key] = encode_svg(f)
            else:
                assets[key] = encode_raster(f, folder["max_dim"], folder["format"], folder["quality"])
            print(f"  baked {key}")

    icon_dir = ROOT / ICON_DIR
    if icon_dir.is_dir():
        for f in sorted(icon_dir.iterdir()):
            if not f.is_file():
                continue
            key = f"{ICON_DIR}/{f.name}"
            assets[key] = encode_svg(f) if f.suffix.lower() == ".svg" else encode_raster(f, 200, None, 85)
            print(f"  baked {key}")

    return assets


def main():
    print("Baking assets...")
    assets = build_asset_map()

    root_logo_path = ROOT / ROOT_LOGO
    root_logo_uri = None
    if root_logo_path.is_file():
        root_logo_uri = encode_raster(root_logo_path, ROOT_LOGO_MAX_DIM, "PNG", 85)
        print(f"  baked {ROOT_LOGO}")

    html = SRC_HTML.read_text(encoding="utf-8")

    asset_lines = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in assets.items())
    asset_script = (
        "<script>\n"
        "window.SDC_ASSETS = {\n"
        f"{asset_lines}\n"
        "};\n"
        "</script>\n"
    )

    anchor = '</script>\n\n<script src="https://unpkg.com/react@18.3.1/umd/react.development.js" crossorigin="anonymous"></script>'
    if anchor not in html:
        raise SystemExit("Could not find the anchor point before the React <script> tag -- did the source file structure change?")
    html = html.replace(anchor, f"</script>\n\n{asset_script}\n<script src=\"https://unpkg.com/react@18.3.1/umd/react.development.js\" crossorigin=\"anonymous\"></script>", 1)

    html = html.replace(
        'const IMG_PATH = p => `Image Files/${p}`;',
        'const IMG_PATH = p => window.SDC_ASSETS["Image Files/" + p] || `Image Files/${p}`;',
        1,
    )
    html = html.replace(
        'const ICON_PATH = p => `Icon Files/${p}`;',
        'const ICON_PATH = p => window.SDC_ASSETS["Icon Files/" + p] || `Icon Files/${p}`;',
        1,
    )
    html = html.replace(
        'const LOGO_PATH = p => `Customer Logo Files/${p}`;',
        'const LOGO_PATH = p => window.SDC_ASSETS["Customer Logo Files/" + p] || `Customer Logo Files/${p}`;',
        1,
    )
    # VID_PATH is intentionally left untouched -- videos are never inlined.

    if root_logo_uri:
        html = html.replace(f'src="{ROOT_LOGO}"', f'src="{root_logo_uri}"', 1)

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"\nWrote {OUT_HTML.name} ({OUT_HTML.stat().st_size / 1_000_000:.1f} MB, {len(assets)} assets baked)")


if __name__ == "__main__":
    main()
