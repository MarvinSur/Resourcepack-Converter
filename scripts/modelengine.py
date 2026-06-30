#!/usr/bin/env python3

import json, os, glob, shutil, logging
logger = logging.getLogger(__name__)


# ModelEngine v4 

def process_me_v4(pack_dir: str, output_dir: str):
    """
    Process ME v4 models.
    Textures and raw files are already copied to output_dir by overlay_builder.
    Here we only need to apply JSON fixes (like format_version) to geo files in the output dir.
    """
    count = 0
    namespaces = _get_namespaces(output_dir)

    for ns in namespaces:
        # Geo files in the output directory
        for geo_file in glob.glob(f"{output_dir}/assets/{ns}/geo/*.geo.json"):
            try:
                with open(geo_file, "r", encoding="utf-8") as f:
                    geo_data = json.load(f)
                
                fixed_data = _fix_me_v4_geo_format(geo_data)
                
                with open(geo_file, "w", encoding="utf-8") as f:
                    json.dump(fixed_data, f, indent=2)
                    
                count += 1
                logger.debug(f"ME v4: fixed geo format for {os.path.basename(geo_file)}")
            except Exception as e:
                logger.error(f"Failed to process ME v4 geo file {geo_file}: {e}")

    logger.info(f"ME v4: processed and fixed {count} models")
    return count

def _fix_me_v4_geo_format(geo_data: dict) -> dict:
    if "format_version" not in geo_data:
        geo_data["format_version"] = "1.12.0"
    return geo_data


# ModelEngine v3 

def process_me_v3(pack_dir: str, output_dir: str):
    """
    ME v3: Legacy entity models.
    Textures and raw files are already copied to output_dir by overlay_builder.
    There are no JSON format fixes needed for ME v3.
    """
    count = 0
    namespaces = _get_namespaces(output_dir)

    for ns in namespaces:
        for _ in glob.glob(f"{output_dir}/assets/{ns}/models/entity/**/*.json", recursive=True):
            count += 1

    logger.info(f"ME v3: processed {count} entity models (files natively copied)")
    return count


# Version compatibility for ME 

def build_me_overlay(pack_dir: str, output_dir: str, overlay_id: str, me_version: str):
    """
    Build ME-specific overlay.
    ME models themselves don't change between MC versions (they're entity-based),
    but we still need the overlay structure to be correct.
    """
    overlay_dir = os.path.join(output_dir, overlay_id)
    os.makedirs(overlay_dir, exist_ok=True)

    if me_version == "v4":
        process_me_v4(pack_dir, overlay_dir)
    elif me_version == "v3":
        process_me_v3(pack_dir, overlay_dir)

    logger.info(f"ME {me_version} overlay built: {overlay_id}")


# Helpers 

def _get_namespaces(pack_dir: str) -> list:
    assets_dir = os.path.join(pack_dir, "assets")
    if not os.path.exists(assets_dir):
        return []
    return [d for d in os.listdir(assets_dir) if os.path.isdir(os.path.join(assets_dir, d))]
