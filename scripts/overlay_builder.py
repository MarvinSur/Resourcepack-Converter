#!/usr/bin/env python3
"""
overlay_builder.py
==================
Builds the full overlay directory structure so the converted pack
supports Minecraft 1.20.1 – 1.21.10.

Strategy
--------
Root dir  → highest pack_format assets (what the pack actually ships)
Overlays  → copies of assets for every version range BELOW the root format

Additionally:
  - Removes assets/minecraft/items/ from all old overlays
    (items/ is only valid from 1.21.2+, format 42+).
  - Copies atlases to every overlay so textures load correctly.
"""

import json, os, shutil, glob, logging
from detector import OVERLAY_RANGES

logger = logging.getLogger(__name__)

TARGET_MAX_FORMAT = 75   # 1.21.11


# ---------------------------------------------------------------------------
# pack.mcmeta builder
# ---------------------------------------------------------------------------

def build_pack_mcmeta(base_format: int, description: str, output_dir: str):
    """
    Generate pack.mcmeta with:
      pack_format   = TARGET_MAX_FORMAT (57)
      supported_formats = 15 – 57
      overlays      = one entry per range below base_format
    """
    entries = []
    for ovr in OVERLAY_RANGES:
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
    logger.info(f"pack.mcmeta written → {len(entries)} overlay entries")
    return mcmeta


# ---------------------------------------------------------------------------
# Asset copiers
# ---------------------------------------------------------------------------

def copy_assets_to_root(pack_dir: str, output_dir: str):
    """Copy everything from pack_dir/assets → output_dir/assets."""
    assets_src = os.path.join(pack_dir, "assets")
    assets_dst = os.path.join(output_dir, "assets")

    if os.path.exists(assets_src):
        if os.path.exists(assets_dst):
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
        logger.info("Assets copied to root")

    icon_src = os.path.join(pack_dir, "pack.png")
    if os.path.exists(icon_src):
        shutil.copy2(icon_src, os.path.join(output_dir, "pack.png"))


def copy_assets_to_overlay(pack_dir: str, output_dir: str, overlay_id: str):
    """
    Copy assets to overlay/<overlay_id>/assets/.
    Then strip assets/minecraft/items/ from the overlay if it exists
    (items/ format is 1.21.2+ only).
    Also ensures atlases are present.
    """
    overlay_dir = os.path.join(output_dir, overlay_id)
    assets_src  = os.path.join(pack_dir, "assets")
    assets_dst  = os.path.join(overlay_dir, "assets")

    if not os.path.exists(assets_src):
        return

    if os.path.exists(assets_dst):
        shutil.rmtree(assets_dst)
    shutil.copytree(assets_src, assets_dst)

    # Strip items/ — not valid before format 42 (1.21.2)
    items_dir = os.path.join(assets_dst, "minecraft", "items")
    if os.path.exists(items_dir):
        shutil.rmtree(items_dir)
        logger.debug(f"Stripped items/ from overlay {overlay_id}")

    logger.info(f"Assets copied → overlay: {overlay_id}")


# ---------------------------------------------------------------------------
# Handle packs that already have overlays
# ---------------------------------------------------------------------------

def strip_overlays_from_existing(pack_dir: str, output_dir: str) -> bool:
    """
    If the source pack already has overlays defined in pack.mcmeta,
    copy those overlay directories verbatim into the output.
    Returns True if existing overlays were found.
    """
    mcmeta_path = os.path.join(pack_dir, "pack.mcmeta")
    if not os.path.exists(mcmeta_path):
        return False

    mcmeta = json.load(open(mcmeta_path, encoding="utf-8"))
    if "overlays" not in mcmeta:
        return False

    existing_entries = mcmeta.get("overlays", {}).get("entries", [])
    logger.info(f"Pack has {len(existing_entries)} existing overlay(s), merging…")

    for entry in existing_entries:
        overlay_dir = entry.get("directory", "")
        src = os.path.join(pack_dir, overlay_dir)
        if os.path.exists(src):
            dst = os.path.join(output_dir, overlay_dir)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            logger.info(f"  Copied existing overlay: {overlay_dir}")

    return True


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def build_full_structure(pack_dir: str, output_dir: str, pack_info: dict):
    """
    Construct the complete overlay structure.

    pack_info keys:
      format           int   — pack_format of the source pack
      version          str   — human-readable MC version
      has_overlays     bool
      existing_overlays list
      description      str
      pack_type        list
    """
    os.makedirs(output_dir, exist_ok=True)

    base_format = pack_info["format"]
    description = pack_info.get("description", "Converted by Resourcepack-Converter")

    # 1. Copy root assets
    copy_assets_to_root(pack_dir, output_dir)

    # 2. Merge any pre-existing overlays from the source pack
    strip_overlays_from_existing(pack_dir, output_dir)

    # 3. For every overlay range BELOW the base format, copy assets
    #    Skip ranges whose directory was already provided by the source pack.
    existing_ids = set(pack_info.get("existing_overlays", []))

    for ovr in OVERLAY_RANGES:
        if ovr["max_format"] >= base_format:
            # This range is covered by the root (or is the root itself)
            continue

        overlay_id = ovr["id"]

        if overlay_id in existing_ids:
            logger.info(f"Overlay {overlay_id} already merged from source, skipping copy")
            continue

        copy_assets_to_overlay(pack_dir, output_dir, overlay_id)

    # 4. Write pack.mcmeta last (after all dirs are set up)
    build_pack_mcmeta(base_format, description, output_dir)

    logger.info(f"Full overlay structure built → {output_dir}")
