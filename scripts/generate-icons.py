"""Generate placeholder icons for Tauri build.

Creates the required icon files in frontend/src-tauri/icons/.
For production, replace these with proper designed icons.

Requires: pip install Pillow
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    print("Creating minimal placeholder files instead...")

    icons_dir = Path(__file__).parent.parent / "frontend" / "src-tauri" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    import struct

    def make_minimal_png(width: int, height: int) -> bytes:
        """Create a minimal valid 1-color PNG."""
        import zlib

        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            c = chunk_type + data
            crc = zlib.crc32(c) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        raw = b""
        for _ in range(height):
            raw += b"\x00" + b"\x2d\x8c\xc9" * width
        idat = zlib.compress(raw)

        return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

    def make_ico(sizes: list[int]) -> bytes:
        """Create a minimal .ico file."""
        pngs = [make_minimal_png(s, s) for s in sizes]
        header = struct.pack("<HHH", 0, 1, len(sizes))
        offset = 6 + 16 * len(sizes)
        entries = b""
        data = b""
        for i, (s, png) in enumerate(zip(sizes, pngs)):
            w = s if s < 256 else 0
            h = s if s < 256 else 0
            entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset)
            offset += len(png)
            data += png
        return header + entries + data

    for name, size in [("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256)]:
        (icons_dir / name).write_bytes(make_minimal_png(size, size))
        print(f"  Created {name}")

    (icons_dir / "icon.ico").write_bytes(make_ico([16, 32, 48, 256]))
    print("  Created icon.ico")

    (icons_dir / "icon.icns").write_bytes(b"")
    print("  Created icon.icns (placeholder)")

    # NSIS images - create minimal BMP stubs
    for name, w, h in [("nsis-header.bmp", 150, 57), ("nsis-sidebar.bmp", 164, 314)]:
        row_bytes = ((w * 3 + 3) // 4) * 4
        row = bytes([0x2D, 0x8C, 0xC9] * w) + b"\x00" * (row_bytes - w * 3)
        pixel_data = row * h
        file_size = 54 + len(pixel_data)
        bmp = struct.pack(
            "<2sIHHIIiiBBIIiiII",
            b"BM", file_size, 0, 0, 54,
            40, w, h, 1, 24, 0, len(pixel_data), 0, 0, 0, 0,
        )
        (icons_dir / name).write_bytes(bmp + pixel_data)
        print(f"  Created {name}")

    print("\nPlaceholder icons generated. Replace with proper designs for production.")
    exit(0)

icons_dir = Path(__file__).parent.parent / "frontend" / "src-tauri" / "icons"
icons_dir.mkdir(parents=True, exist_ok=True)

BG_COLOR = (45, 140, 201)
FG_COLOR = (255, 255, 255)

def create_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    padding = size // 8
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=size // 6,
        fill=BG_COLOR,
    )

    font_size = size // 3
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    text = "M"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=FG_COLOR, font=font)

    return img

for name, size in [("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256)]:
    create_icon(size).save(icons_dir / name)
    print(f"Created {name}")

icon_256 = create_icon(256)
icon_48 = create_icon(48)
icon_32 = create_icon(32)
icon_16 = create_icon(16)

icon_256.save(icons_dir / "icon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
print("Created icon.ico")

(icons_dir / "icon.icns").write_bytes(b"")
print("Created icon.icns (placeholder)")

for name, w, h in [("nsis-header.bmp", 150, 57), ("nsis-sidebar.bmp", 164, 314)]:
    img = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", min(w, h) // 3)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, h // 3), "MoldGen", fill=FG_COLOR, font=font)
    img.save(icons_dir / name)
    print(f"Created {name}")

print("\nIcons generated! Replace with proper designs for production.")
