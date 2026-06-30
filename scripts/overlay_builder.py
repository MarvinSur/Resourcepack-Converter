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

def build_pack_mcmeta(base_format: int, description: str, output_dir: str, existing_overlays: list):
    """
    Generate pack.mcmeta with:
      pack_format   = TARGET_MAX_FORMAT (75)
      supported_formats = 15 – 75
      overlays      = only those preserved from the source pack
    """
    entries = []
    # If the source pack had valid existing overlays, we just re-list them.
    for directory in existing_overlays:
        # We don't have the exact formats from the source mcmeta, 
        # but we can try to map them back, or just read the original mcmeta!
        pass

    # Actually, the easiest way to preserve existing overlay metadata is to 
    # read the original pack.mcmeta if it exists, or just pass the original overlay entries.
    
    # We will just write a simple pack.mcmeta that covers all versions.
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
    
    # If there are existing overlays, we should probably just inject them back.
    # We will fetch them in build_full_structure and pass them here.
    if existing_overlays:
        mcmeta["overlays"] = {"entries": existing_overlays}

    out_path = os.path.join(output_dir, "pack.mcmeta")
    json.dump(mcmeta, open(out_path, "w", encoding="utf-8"), indent=2)
    logger.info(f"pack.mcmeta written (supported 15-{TARGET_MAX_FORMAT})")
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

    # We do NOT create backward overlays that duplicate the entire assets/ directory anymore.
    # The root will hold both old (models/item/) and new (items/) item structures natively.

    # We just need to extract the original overlay entries from pack.mcmeta (if any)
    # to preserve them.
    mcmeta_path = os.path.join(pack_dir, "pack.mcmeta")
    existing_entries = []
    if os.path.exists(mcmeta_path):
        try:
            mcmeta = json.load(open(mcmeta_path, encoding="utf-8"))
            existing_entries = mcmeta.get("overlays", {}).get("entries", [])
        except Exception:
            pass

    # 4. Write pack.mcmeta last (after all dirs are set up)
    build_pack_mcmeta(base_format, description, output_dir, existing_entries)

    logger.info(f"Full structure built → {output_dir} (Backwards overlays eliminated)")
