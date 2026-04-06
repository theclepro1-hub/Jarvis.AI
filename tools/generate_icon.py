from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "images" / "jarvis_master_icon.png"
ICON_DIR = ROOT / "assets" / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_ICO = ICON_DIR / "jarvis_unity.ico"
OUTPUT_PNG = ICON_DIR / "jarvis_unity_256.png"


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    square = crop_center_square(image)
    square.resize((256, 256), Image.Resampling.LANCZOS).save(OUTPUT_PNG)
    square.save(
        OUTPUT_ICO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"ICON_OK {OUTPUT_ICO}")


def crop_center_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


if __name__ == "__main__":
    main()
