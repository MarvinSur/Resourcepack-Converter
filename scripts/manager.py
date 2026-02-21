#!/usr/bin/env python3
"""
manager.py
==========
Orchestrates the full conversion pipeline:
  1. Download & extract the pack
  2. Detect pack type and base version
  3. Strip incompatible assets (OptiFine CIT, shaders)
  4. Build overlay structure (root + per-version overlays)
  5. Convert item models → assets/minecraft/items/*.json
  6. Handle ModelEngine assets
  7. Package final ZIP
"""

import os, sys, shutil, zipfile, json, logging, argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from detector        import detect_pack_type, detect_base_version, strip_optifine_cit, strip_shaders, OVERLAY_RANGES
from link_converter  import convert_to_direct
from item_converter  import convert_pack_item_models
from overlay_builder import build_full_structure
from modelengine     import process_me_v4, process_me_v3


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_pack(url: str, dest: str) -> str:
    import urllib.request
    direct_url = convert_to_direct(url)
    logger.info(f"Downloading: {direct_url[:100]}")
    zip_path = os.path.join(dest, "input_pack.zip")
    urllib.request.urlretrieve(direct_url, zip_path)
    logger.info(f"Downloaded → {zip_path}  ({os.path.getsize(zip_path)//1024} KB)")
    return zip_path


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_pack(zip_path: str, dest: str) -> str:
    """Extract and return the effective pack root (handles inner subfolder)."""
    pack_dir = os.path.join(dest, "pack")
    os.makedirs(pack_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(pack_dir)

    # Some packs zip their root inside a single subfolder
    contents = os.listdir(pack_dir)
    if len(contents) == 1:
        inner = os.path.join(pack_dir, contents[0])
        if os.path.isdir(inner) and os.path.exists(os.path.join(inner, "pack.mcmeta")):
            logger.info(f"Pack root inside subfolder: {contents[0]}")
            return inner

    return pack_dir


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

def package_output(output_dir: str, final_path: str):
    with zipfile.ZipFile(final_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                full    = os.path.join(root, file)
                arcname = os.path.relpath(full, output_dir)
                zf.write(full, arcname)
    logger.info(f"Packaged → {final_path}  ({os.path.getsize(final_path)//1024} KB)")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(pack_url: str, staging_dir: str = "staging", output_name: str = "converted_pack.zip"):

    os.makedirs(staging_dir, exist_ok=True)
    zip_path   = os.path.join(staging_dir, "input_pack.zip")
    output_dir = os.path.join(staging_dir, "output")

    # ── Step 1: Download ────────────────────────────────────────────────────
    logger.info("=== STEP 1: Download ===")
    if not os.path.exists(zip_path):
        download_pack(pack_url, staging_dir)

    # ── Step 2: Extract ─────────────────────────────────────────────────────
    logger.info("=== STEP 2: Extract ===")
    pack_dir_base = os.path.join(staging_dir, "pack")
    if os.path.exists(pack_dir_base):
        shutil.rmtree(pack_dir_base)
    pack_dir = extract_pack(zip_path, staging_dir)

    # ── Step 3: Detect ──────────────────────────────────────────────────────
    logger.info("=== STEP 3: Detect ===")
    pack_type_info    = detect_pack_type(pack_dir)
    base_version_info = detect_base_version(pack_dir)

    pack_types  = pack_type_info["types"]
    base_format = base_version_info["format"]

    logger.info(f"Pack types : {pack_types}")
    logger.info(f"Base format: {base_format} ({base_version_info['version']})")

    # ── Step 3b: Strip incompatible assets ──────────────────────────────────
    cit_removed     = strip_optifine_cit(pack_dir)
    shaders_removed = strip_shaders(pack_dir)
    if cit_removed:
        logger.warning(f"⚠ Removed {cit_removed} OptiFine CIT file(s)")
    if shaders_removed:
        logger.warning(f"⚠ Removed {shaders_removed} shader file(s)")

    # ── Step 4: Build overlay structure ─────────────────────────────────────
    logger.info("=== STEP 4: Build overlay structure ===")
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    description = "§aMortaz Development Converter"

    build_full_structure(pack_dir, output_dir, {
        "format":            base_format,
        "version":           base_version_info["version"],
        "has_overlays":      base_version_info["has_overlays"],
        "existing_overlays": base_version_info["existing_overlays"],
        "description":       description,
        "pack_type":         pack_types,
    })

    # ── Step 5: Convert item models ──────────────────────────────────────────
    logger.info("=== STEP 5: Convert item models ===")
    #
    # convert_pack_item_models will:
    #   • write assets/minecraft/items/*.json  → root (and overlay_v1_21_4 if needed)
    #   • copy original predicate models       → ALL old overlays
    #
    # We determine which overlay IDs need item.json (1.21.2+) vs predicates.
    new_item_json_overlays = [o["id"] for o in OVERLAY_RANGES if o["item_json"]]
    old_predicate_overlays = [o["id"] for o in OVERLAY_RANGES if not o["item_json"]]

    convert_pack_item_models(
        pack_dir   = pack_dir,
        output_dir = output_dir,
        # These args are kept for API compat but logic is now inside item_converter
        overlay_id_new = "overlay_v1_21_4",
        overlay_id_old = "overlay_v1_20_5",
    )

    # ── Step 5b: Also write item.json into overlay_v1_21_2 ──────────────────
    # 1.21.2 and 1.21.3 (format 42–45) ALSO use the new item.json format.
    # We copy root assets/minecraft/items/ into overlay_v1_21_2 if that
    # overlay exists in the output (i.e. base_format > 45).
    ov_1_21_2_dir = os.path.join(output_dir, "overlay_v1_21_2")
    root_items_dir = os.path.join(output_dir, "assets", "minecraft", "items")
    if os.path.exists(ov_1_21_2_dir) and os.path.exists(root_items_dir):
        ov_items_dst = os.path.join(ov_1_21_2_dir, "assets", "minecraft", "items")
        if os.path.exists(ov_items_dst):
            shutil.rmtree(ov_items_dst)
        shutil.copytree(root_items_dir, ov_items_dst)
        logger.info("Copied items/ → overlay_v1_21_2")

    # ── Step 6: ModelEngine ─────────────────────────────────────────────────
    if "modelengine_v4" in pack_types:
        logger.info("=== STEP 6: ModelEngine v4 ===")
        process_me_v4(pack_dir, output_dir)
    elif "modelengine_v3" in pack_types:
        logger.info("=== STEP 6: ModelEngine v3 ===")
        process_me_v3(pack_dir, output_dir)
    else:
        logger.info(f"=== STEP 6: Skipped (types: {pack_types}) ===")

    # ── Step 7: Package ─────────────────────────────────────────────────────
    logger.info("=== STEP 7: Package ===")
    final_path = os.path.join(staging_dir, output_name)
    package_output(output_dir, final_path)

    logger.info("=== DONE ===")
    logger.info(f"Output: {final_path}")
    return final_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resourcepack-Converter")
    parser.add_argument("--url",     required=True,                    help="Pack download URL")
    parser.add_argument("--output",  default="converted_pack.zip",     help="Output filename")
    parser.add_argument("--staging", default="staging",                help="Staging directory")
    args = parser.parse_args()

    run(
        pack_url    = args.url,
        staging_dir = args.staging,
        output_name = args.output,
    )
