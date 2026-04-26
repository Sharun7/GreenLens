"""
greenwash_detector/data_download.py — EuroSAT Training Data Generator.

Generates synthetic satellite-like training images for the 6 GreenLens
land-use classes. No internet connection required.

Each class has characteristic RGB colour statistics that approximate real
Sentinel-2 imagery, giving ResNet-18 enough signal to learn class boundaries.

For production quality, replace the generated images with real EuroSAT data
(manually download EuroSAT.zip from https://zenodo.org/record/7711810 and
re-run with --real-zip path/to/EuroSAT.zip).

Usage:
    python greenwash_detector/data_download.py
    python greenwash_detector/data_download.py --output data/eurosat_greenlens --count 300
    python greenwash_detector/data_download.py --real-zip path/to/EuroSAT.zip --output data/eurosat_greenlens
"""

import argparse
import random
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

from PIL import Image
import numpy as np

GREENLENS_CLASSES = [
    "solar_farm", "wind_farm", "forest", "water_body", "urban", "bare_land"
]

# ── Per-class RGB statistics (approximate Sentinel-2 RGB, scaled 0-255) ──────
# Based on typical EuroSAT class distributions
CLASS_RGB_STATS = {
    "solar_farm":  {"mean": [50,  55,  60],  "std": [15, 15, 12]},   # dark grey-blue panels
    "wind_farm":   {"mean": [120, 135, 95],  "std": [25, 22, 20]},   # green grassland + turbines
    "forest":      {"mean": [55,  100, 55],  "std": [18, 20, 15]},   # dense green
    "water_body":  {"mean": [40,  70,  130], "std": [12, 18, 25]},   # blue water
    "urban":       {"mean": [130, 120, 115], "std": [30, 28, 26]},   # grey/tan built-up
    "bare_land":   {"mean": [160, 148, 120], "std": [28, 25, 22]},   # tan/brown soil
}

IMG_SIZE   = 64   # EuroSAT native patch size


def _generate_patch(gl_class: str, rng: random.Random, idx: int) -> Image.Image:
    """Generate a synthetic 64×64 RGB patch for a given class."""
    stats = CLASS_RGB_STATS[gl_class]
    mean  = stats["mean"]
    std   = stats["std"]

    np_rng = np.random.default_rng(rng.randint(0, 2**31))

    # Base colour field
    patch = np.zeros((IMG_SIZE, IMG_SIZE, 3), dtype=np.float32)
    for c in range(3):
        patch[:, :, c] = np_rng.normal(mean[c], std[c], (IMG_SIZE, IMG_SIZE))

    # Add low-frequency spatial structure (blobs/gradients) for realism
    for _ in range(3):
        x0 = rng.randint(0, IMG_SIZE - 1)
        y0 = rng.randint(0, IMG_SIZE - 1)
        r  = rng.randint(5, 20)
        intensity = rng.uniform(-25, 25)
        for x in range(max(0, x0 - r), min(IMG_SIZE, x0 + r)):
            for y in range(max(0, y0 - r), min(IMG_SIZE, y0 + r)):
                if (x - x0) ** 2 + (y - y0) ** 2 < r ** 2:
                    patch[x, y, :] += intensity * 0.5

    patch = np.clip(patch, 0, 255).astype(np.uint8)
    return Image.fromarray(patch, "RGB")


def generate_synthetic(output_dir: str, count: int = 300, seed: int = 42) -> None:
    """Generate synthetic training images for all 6 GreenLens classes."""
    output_root = Path(output_dir)
    rng = random.Random(seed)

    print(f"Generating {count} synthetic training images per class ...")
    print(f"Output: {output_root.resolve()}\n")

    total = 0
    for gl_class in GREENLENS_CLASSES:
        class_dir = output_root / gl_class
        class_dir.mkdir(parents=True, exist_ok=True)

        for idx in range(count):
            img      = _generate_patch(gl_class, rng, idx)
            img_path = class_dir / f"{gl_class}_{idx:05d}.jpg"
            img.save(img_path, "JPEG", quality=90)
            total += 1

        print(f"  {gl_class:15s}: {count} images generated")

    print(f"\nDone. Total images: {total}")
    print("\nFine-tune the CNN with:")
    print("  from greenwash_detector.satellite_classifier import SatelliteClassifier")
    print("  clf = SatelliteClassifier()")
    print(f"  clf.fine_tune(\'{output_dir}\')")
    print("  clf.save_model(\'models/satellite_classifier.pt\')")


# ── EuroSAT → GreenLens label map (for --real-zip mode) ──────────────────────
LABEL_MAP = {
    "Forest":               "forest",
    "HerbaceousVegetation": "forest",
    "Pasture":              "forest",
    "River":                "water_body",
    "SeaLake":              "water_body",
    "Residential":          "urban",
    "Highway":              "urban",
    "Industrial":           "solar_farm",
    "AnnualCrop":           "bare_land",
    "PermanentCrop":        "bare_land",
}


def load_from_zip(zip_path: str, output_dir: str, limit: int = 500, seed: int = 42) -> None:
    """
    Organise a manually-downloaded EuroSAT.zip into GreenLens class folders.
    Download EuroSAT.zip from: https://zenodo.org/record/7711810
    """
    output_root = Path(output_dir)
    cache_dir   = output_root / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for cls in GREENLENS_CLASSES:
        (output_root / cls).mkdir(parents=True, exist_ok=True)

    print(f"Extracting {zip_path} ...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(cache_dir)

    # Find extracted root
    candidates = [d for d in cache_dir.iterdir() if d.is_dir()]
    eurosat_root = candidates[0] if candidates else cache_dir
    class_dirs   = [d for d in eurosat_root.iterdir() if d.is_dir()]
    print(f"Found {len(class_dirs)} classes: {[d.name for d in class_dirs]}")

    buckets: dict[str, list] = defaultdict(list)
    for class_dir in class_dirs:
        gl_class = LABEL_MAP.get(class_dir.name)
        if gl_class:
            imgs = (sorted(class_dir.glob("*.jpg")) + sorted(class_dir.glob("*.tif"))
                    + sorted(class_dir.glob("*.png")))
            buckets[gl_class].extend(imgs)

    rng = random.Random(seed)
    total = 0
    for gl_class in GREENLENS_CLASSES:
        if gl_class == "wind_farm":
            continue
        items = buckets.get(gl_class, [])
        if limit > 0 and len(items) > limit:
            items = rng.sample(items, limit)
        for idx, src in enumerate(items):
            dst = output_root / gl_class / f"{gl_class}_{idx:05d}.jpg"
            try:
                Image.open(src).convert("RGB").save(dst, "JPEG", quality=90)
            except Exception:
                shutil.copy2(src, dst)
            total += 1
        print(f"  {gl_class:15s}: {len(items)} images")

    # wind_farm placeholder
    wind_dir = output_root / "wind_farm"
    forest_imgs = sorted((output_root / "forest").glob("*.jpg"))
    for img_path in rng.sample(forest_imgs, min(50, len(forest_imgs))):
        shutil.copy2(img_path, wind_dir / f"wind_{img_path.name}")
    print(f"  {'wind_farm':15s}: placeholder from forest")
    print(f"\nDone. {total} images organised into {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare EuroSAT training data for GreenLens CNN."
    )
    parser.add_argument(
        "--output", default="data/eurosat_greenlens",
        help="Output directory (default: data/eurosat_greenlens)",
    )
    parser.add_argument(
        "--count", type=int, default=300,
        help="Images per class in synthetic mode (default: 300)",
    )
    parser.add_argument(
        "--real-zip", default=None, metavar="ZIP_PATH",
        help="Path to manually-downloaded EuroSAT.zip (from zenodo.org/record/7711810)",
    )
    parser.add_argument(
        "--limit", type=int, default=500,
        help="Max images per class in --real-zip mode (default: 500)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
    )
    args = parser.parse_args()

    if args.real_zip:
        load_from_zip(args.real_zip, args.output, limit=args.limit, seed=args.seed)
    else:
        generate_synthetic(args.output, count=args.count, seed=args.seed)


if __name__ == "__main__":
    main()
