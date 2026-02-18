#!/usr/bin/env python3

import os, sys, shutil, zipfile, json, logging, argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from detector       import detect_pack_type, detect_base_version, strip_optifine_cit, strip_shaders
from link_converter import convert_to_direct
from item_converter import convert_pack_item_models
from overlay_builder import build_full_structure
from modelengine    import process_me_v4, process_me_v3


def download_pack(url: str, dest: str) -> str:
    """Download pack from URL (after converting to direct link)."""
    import urllib.request

    direct_url = convert_to_direct(url)
    logger.info(f"Downloading from: {direct_url[:80]}")

    zip_path = os.path.join(dest, "input_pack.zip")
    urllib.request.urlretrieve(direct_url, zip_path)
    logger.info(f"Downloaded to: {zip_path} ({os.path.getsize(zip_path) // 1024} KB)")
    return zip_path


def extract_pack(zip_path: str, dest: str) -> str:
    """Extract zip to dest, return extracted directory."""
    pack_dir = os.path.join(dest, "pack")
    os.makedirs(pack_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(pack_dir)

    # Some packs have a subfolder inside the zip
    contents = os.listdir(pack_dir)
    if len(contents) == 1 and os.path.isdir(os.path.join(pack_dir, contents[0])):
        inner = os.path.join(pack_dir, contents[0])
        if os.path.exists(os.path.join(inner, "pack.mcmeta")):
            logger.info(f"Pack root detected inside subfolder: {contents[0]}")
            return inner

    return pack_dir


def package_output(output_dir: str, final_path: str):
    """Zip the output directory into a final .zip file."""
    with zipfile.ZipFile(final_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                full = os.path.join(root, file)
                arcname = os.path.relpath(full, output_dir)
                zf.write(full, arcname)
    logger.info(f"Output packaged: {final_path} ({os.path.getsize(final_path) // 1024} KB)")


def run(pack_url: str, staging_dir: str = "staging", output_name: str = "converted_pack.zip"):

    os.makedirs(staging_dir, exist_ok=True)
    pack_dir_zip  = os.path.join(staging_dir, "input_pack.zip")
    pack_dir      = os.path.join(staging_dir, "pack")
    output_dir    = os.path.join(staging_dir, "output")

    # 1. Download & extract 
    if not os.path.exists(pack_dir_zip):
        logger.info("=== STEP 1: Download ===")
        download_pack(pack_url, staging_dir)

    logger.info("=== STEP 2: Extract ===")
    if os.path.exists(pack_dir):
        shutil.rmtree(pack_dir)
    pack_dir = extract_pack(pack_dir_zip, staging_dir)

    # 2. Detect 
    logger.info("=== STEP 3: Detect ===")
    pack_type_info    = detect_pack_type(pack_dir)
    base_version_info = detect_base_version(pack_dir)

    pack_types  = pack_type_info["types"]
    base_format = base_version_info["format"]
    
    # Strip OptiFine CIT and shaders for compatibility
    cit_removed = strip_optifine_cit(pack_dir)
    shaders_removed = strip_shaders(pack_dir)
    
    if cit_removed > 0:
        logger.warning(f"⚠ Removed {cit_removed} OptiFine CIT files (incompatible with 1.21.4+)")
    if shaders_removed > 0:
        logger.warning(f"⚠ Removed {shaders_removed} shader files (incompatible with 1.21.4+)")
    
    # Custom description - green text for Mortaz Development
    description = "§aMortaz Development Converter"

    logger.info(f"Pack types: {pack_types} | Base format: {base_format} ({base_version_info['version']})")

    # 3. Build overlay structure 
    logger.info("=== STEP 4: Build overlays ===")
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    build_full_structure(pack_dir, output_dir, {
        "format":           base_format,
        "version":          base_version_info["version"],
        "has_overlays":     base_version_info["has_overlays"],
        "existing_overlays": base_version_info["existing_overlays"],
        "description":      description,
        "pack_type":        pack_types,
    })

    # 4. Convert item models for 1.21.2+ 
    logger.info("=== STEP 5: Convert item models (1.21.2+) ===")
    convert_pack_item_models(
        pack_dir    = pack_dir,
        output_dir  = output_dir,
        overlay_id_new = "overlay_v1_21_4",
        overlay_id_old = "overlay_v1_20_5",
    )

    # 5. ModelEngine extra processing 
    if "modelengine_v4" in pack_types:
        logger.info("=== STEP 6: ModelEngine v4 assets ===")
        process_me_v4(pack_dir, output_dir)
    if "modelengine_v3" in pack_types:
        logger.info("=== STEP 6: ModelEngine v3 assets ===")
        process_me_v3(pack_dir, output_dir)
    if not any(t in pack_types for t in ["modelengine_v4", "modelengine_v3"]):
        logger.info(f"=== STEP 6: Skipped (pack types: {pack_types}) ===")

    # 6. Package 
    logger.info("=== STEP 7: Package ===")
    final_path = os.path.join(staging_dir, output_name)
    package_output(output_dir, final_path)

    logger.info("=== DONE ===")
    logger.info(f"Output: {final_path}")
    return final_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resourcepack-Converter")
    parser.add_argument("--url",    required=True,  help="Pack download URL")
    parser.add_argument("--output", default="converted_pack.zip", help="Output filename")
    parser.add_argument("--staging", default="staging", help="Staging directory")
    args = parser.parse_args()

    run(
        pack_url    = args.url,
        staging_dir = args.staging,
        output_name = args.output,
    )
