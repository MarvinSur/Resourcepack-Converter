#!/usr/bin/env python3

import json, os, shutil, glob, logging
from detector import OVERLAY_RANGES

logger = logging.getLogger(__name__)

TARGET_MAX_FORMAT = 57  # 1.21.10


def build_pack_mcmeta(base_format: int, description: str, output_dir: str):
    """
    Generate pack.mcmeta with:
    - pack_format = max supported (57 = 1.21.10)
    - supported_formats range covering all versions
    - overlays entries for each range below base_format
    """
    entries = []
    for ovr in OVERLAY_RANGES:
        # Only add overlay if its range is BELOW the base format
        # (the base format's range goes directly in root)
        if ovr["max_format"] < base_format:
            entries.append({
                "formats": {
                    "min_inclusive": ovr["min_format"],
                    "max_inclusive": ovr["max_format"]
                },
                "directory": ovr["id"]
            })

    mcmeta = {
        "pack": {
            "pack_format": TARGET_MAX_FORMAT,
            "supported_formats": {
                "min_inclusive": 15,
                "max_inclusive": TARGET_MAX_FORMAT
            },
            "description": description
        }
    }

    if entries:
        mcmeta["overlays"] = {"entries": entries}

    out_path = os.path.join(output_dir, "pack.mcmeta")
    json.dump(mcmeta, open(out_path, "w", encoding="utf-8"), indent=2)
    logger.info(f"pack.mcmeta written with {len(entries)} overlay entries")
    return mcmeta


def copy_assets_to_root(pack_dir: str, output_dir: str):
    """
    Copy all assets from pack_dir to output_dir root.
    Skips pack.mcmeta (we generate our own).
    """
    assets_src = os.path.join(pack_dir, "assets")
    assets_dst = os.path.join(output_dir, "assets")

    if os.path.exists(assets_src):
        if os.path.exists(assets_dst):
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
        logger.info("Assets copied to root")

    # Copy pack.png if exists
    icon_src = os.path.join(pack_dir, "pack.png")
    if os.path.exists(icon_src):
        shutil.copy2(icon_src, os.path.join(output_dir, "pack.png"))


def copy_assets_to_overlay(pack_dir: str, output_dir: str, overlay_id: str, overrides: dict = None):
    """
    Copy assets to a specific overlay directory.
    overrides: dict of {relative_path: content} to override specific files in overlay.
    """
    overlay_dir = os.path.join(output_dir, overlay_id)
    assets_src = os.path.join(pack_dir, "assets")
    assets_dst = os.path.join(overlay_dir, "assets")

    if os.path.exists(assets_src):
        if os.path.exists(assets_dst):
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)

    # Apply overrides (e.g., different pack.mcmeta or model files)
    if overrides:
        for rel_path, content in overrides.items():
            full_path = os.path.join(overlay_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            if isinstance(content, dict):
                json.dump(content, open(full_path, "w", encoding="utf-8"), indent=2)
            else:
                open(full_path, "w", encoding="utf-8").write(content)

    logger.info(f"Assets copied to overlay: {overlay_id}")


def strip_overlays_from_existing(pack_dir: str, output_dir: str):
    """
    If pack already has overlays, flatten the highest-format one to root
    and keep others as overlay dirs.
    """
    mcmeta_path = os.path.join(pack_dir, "pack.mcmeta")
    if not os.path.exists(mcmeta_path):
        return False

    mcmeta = json.load(open(mcmeta_path, encoding="utf-8"))
    if "overlays" not in mcmeta:
        return False

    existing_entries = mcmeta.get("overlays", {}).get("entries", [])
    logger.info(f"Pack has {len(existing_entries)} existing overlays, merging...")

    # Copy existing overlay dirs to output
    for entry in existing_entries:
        overlay_dir = entry.get("directory", "")
        src = os.path.join(pack_dir, overlay_dir)
        if os.path.exists(src):
            dst = os.path.join(output_dir, overlay_dir)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    return True


def build_full_structure(pack_dir: str, output_dir: str, pack_info: dict):
    """
    Main builder. Constructs complete overlay structure.

    pack_info: {
        'format': int,
        'version': str,
        'has_overlays': bool,
        'existing_overlays': list,
        'description': str,
        'pack_type': str,
    }
    """
    os.makedirs(output_dir, exist_ok=True)

    base_format = pack_info["format"]
    description = pack_info.get("description", "Converted by Resourcepack-Converter")

    # 1. Copy main assets to root
    copy_assets_to_root(pack_dir, output_dir)

    # 2. Handle existing overlays if any
    has_existing = strip_overlays_from_existing(pack_dir, output_dir)

    # 3. Build overlay entries for versions BELOW base_format
    #    These need the OLD format (predicates, no item.json)
    for ovr in OVERLAY_RANGES:
        if ovr["max_format"] >= base_format:
            continue  # This range is covered by root or already handled

        overlay_id = ovr["id"]
        overlay_out = os.path.join(output_dir, overlay_id)

        # Skip if already built from existing overlays
        if ovr["id"] in pack_info.get("existing_overlays", []):
            logger.info(f"Overlay {overlay_id} already exists, skipping copy")
            continue

        # Copy assets to overlay
        copy_assets_to_overlay(pack_dir, output_dir, overlay_id)

        logger.info(f"Built overlay: {overlay_id} (formats {ovr['min_format']}–{ovr['max_format']})")

    # 4. Write pack.mcmeta
    build_pack_mcmeta(base_format, description, output_dir)

    logger.info(f"Full overlay structure built in: {output_dir}")
