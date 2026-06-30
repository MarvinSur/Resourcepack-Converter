#!/usr/bin/env python3

import json, os, glob, shutil, logging
logger = logging.getLogger(__name__)


# ModelEngine v4 

def process_me_v4(pack_dir: str, output_dir: str):

    count = 0
    namespaces = _get_namespaces(pack_dir)

    for ns in namespaces:
        # Geo files
        for geo_file in glob.glob(f"{pack_dir}/assets/{ns}/geo/*.geo.json"):
            model_name = os.path.basename(geo_file).replace(".geo.json", "")
            dst_dir = os.path.join(output_dir, "assets", ns, "geo")
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(geo_file, os.path.join(dst_dir, os.path.basename(geo_file)))

            # Paired animation file
            anim_src = f"{pack_dir}/assets/{ns}/animations/{model_name}.animation.json"
            if os.path.exists(anim_src):
                anim_dst = os.path.join(output_dir, "assets", ns, "animations")
                os.makedirs(anim_dst, exist_ok=True)
                shutil.copy2(anim_src, os.path.join(anim_dst, os.path.basename(anim_src)))

            # Textures
            tex_src = f"{pack_dir}/assets/{ns}/textures/entity/{model_name}"
            if os.path.exists(tex_src):
                tex_dst = os.path.join(output_dir, "assets", ns, "textures", "entity", model_name)
                if not os.path.exists(tex_dst):
                    shutil.copytree(tex_src, tex_dst)

            count += 1
            logger.debug(f"ME v4: copied {model_name}")

    logger.info(f"ME v4: processed {count} models")
    return count


def _fix_me_v4_geo_format(geo_data: dict) -> dict:

    if "format_version" not in geo_data:
        geo_data["format_version"] = "1.12.0"
    return geo_data


# ModelEngine v3 

def process_me_v3(pack_dir: str, output_dir: str):
    """
    ME v3: Legacy entity models.
    Structure: assets/<namespace>/models/entity/<model>.json
    Copies to output preserving structure.
    Also copies paired textures from textures/entity/.
    """
    count = 0
    namespaces = _get_namespaces(pack_dir)

    for ns in namespaces:
        for model_file in glob.glob(f"{pack_dir}/assets/{ns}/models/entity/**/*.json", recursive=True):
            rel = os.path.relpath(model_file, f"{pack_dir}/assets/{ns}/models/entity")
            model_name = rel.replace(".json", "").replace("\\", "/")

            # Copy model
            dst = os.path.join(output_dir, "assets", ns, "models", "entity", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(model_file, dst)

            # Copy textures
            for tex_src in glob.glob(f"{pack_dir}/assets/{ns}/textures/entity/{model_name}*"):
                tex_rel = os.path.relpath(tex_src, f"{pack_dir}/assets/{ns}/textures/entity")
                tex_dst = os.path.join(output_dir, "assets", ns, "textures", "entity", tex_rel)
                os.makedirs(os.path.dirname(tex_dst), exist_ok=True)
                shutil.copy2(tex_src, tex_dst)

            count += 1
            logger.debug(f"ME v3: copied {model_name}")

    logger.info(f"ME v3: processed {count} entity models")
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
