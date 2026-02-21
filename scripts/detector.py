#!/usr/bin/env python3
"""
detector.py
===========
Detects:
  1. Pack type  (itemsadder / nexo / modelengine_v4 / modelengine_v3 / vanilla)
  2. Base pack_format from pack.mcmeta
  3. Existing overlay directories

Also provides strip helpers for OptiFine CIT and shaders.
"""

import json, os, glob, logging, shutil
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# pack_format → MC version mapping
# Keep this sorted ascending.
# ---------------------------------------------------------------------------
PACK_FORMATS = {
    15: "1.20.1",
    18: "1.20.2",
    22: "1.20.3",  # 1.20.3 and 1.20.4 share format 22
    32: "1.20.5",  # 1.20.5 and 1.20.6 share format 32
    34: "1.21.0",  # 1.21.0 and 1.21.1 share format 34
    42: "1.21.2",  # 1.21.2 and 1.21.3 share format 42
    46: "1.21.4",
    48: "1.21.5",
    50: "1.21.6",
    52: "1.21.7",
    54: "1.21.8",
    56: "1.21.9",
    57: "1.21.10",
}

# ---------------------------------------------------------------------------
# Overlay range definitions
# Each entry describes a contiguous range of pack_format values.
# item_json = True  → this range uses assets/minecraft/items/ (1.21.2+)
# item_json = False → this range uses old assets/*/models/item/*.json predicates
# ---------------------------------------------------------------------------
OVERLAY_RANGES = [
    {
        "id":          "overlay_v1_20_1",
        "label":       "1.20.1",
        "min_format":  15,
        "max_format":  17,
        "item_json":   False,
    },
    {
        "id":          "overlay_v1_20_2",
        "label":       "1.20.2–1.20.4",
        "min_format":  18,
        "max_format":  31,
        "item_json":   False,
    },
    {
        "id":          "overlay_v1_20_5",
        "label":       "1.20.5–1.21.1",
        "min_format":  32,
        "max_format":  41,
        "item_json":   False,
    },
    {
        "id":          "overlay_v1_21_2",
        "label":       "1.21.2–1.21.3",
        "min_format":  42,
        "max_format":  45,
        "item_json":   True,
    },
    {
        "id":          "overlay_v1_21_4",
        "label":       "1.21.4–1.21.10",
        "min_format":  46,
        "max_format":  999,
        "item_json":   True,
    },
]


# ---------------------------------------------------------------------------
# detect_pack_type
# ---------------------------------------------------------------------------

def detect_pack_type(pack_dir: str) -> dict:
    """
    Heuristic detection of which plugin generated this resourcepack.
    Returns {"types": [...], "scores": {...}}
    """
    scores = {
        "itemsadder":    0,
        "nexo":          0,
        "modelengine_v4": 0,
        "modelengine_v3": 0,
    }

    # ItemsAdder: dedicated namespace OR damage+damaged predicates together
    if os.path.exists(os.path.join(pack_dir, "assets", "itemsadder")):
        scores["itemsadder"] += 10
    if os.path.exists(os.path.join(pack_dir, "assets", "_iainternal")):
        scores["itemsadder"] += 10

    for f in glob.glob(f"{pack_dir}/assets/*/models/item/*.json"):
        try:
            data = json.load(open(f, encoding="utf-8"))
            for ov in data.get("overrides", []):
                p = ov.get("predicate", {})
                if "damage" in p and "damaged" in p:
                    scores["itemsadder"] += 1
                    break
        except Exception:
            continue

    # Nexo: custom_model_data only (no damage/damaged)
    if os.path.exists(os.path.join(pack_dir, "assets", "nexo")):
        scores["nexo"] += 10
    for f in glob.glob(f"{pack_dir}/assets/*/models/item/*.json"):
        try:
            data = json.load(open(f, encoding="utf-8"))
            for ov in data.get("overrides", []):
                p = ov.get("predicate", {})
                if "custom_model_data" in p and "damage" not in p and "damaged" not in p:
                    scores["nexo"] += 1
                    break
        except Exception:
            continue

    # ModelEngine v4: .geo.json + .animation.json
    me4 = (
        glob.glob(f"{pack_dir}/assets/*/geo/*.geo.json")
        + glob.glob(f"{pack_dir}/assets/*/animations/*.animation.json")
    )
    if me4:
        scores["modelengine_v4"] += len(me4) * 2
    if os.path.exists(os.path.join(pack_dir, "assets", "modelengine")):
        scores["modelengine_v4"] += 10

    # ModelEngine v3: legacy entity models
    me3 = glob.glob(f"{pack_dir}/assets/*/models/entity/**/*.json", recursive=True)
    if me3:
        scores["modelengine_v3"] += len(me3)

    THRESHOLD = 1
    detected = [t for t, s in scores.items() if s >= THRESHOLD]

    # ME v3 and v4 are mutually exclusive — keep higher score
    if "modelengine_v4" in detected and "modelengine_v3" in detected:
        if scores["modelengine_v4"] >= scores["modelengine_v3"]:
            detected.remove("modelengine_v3")
        else:
            detected.remove("modelengine_v4")

    if not detected:
        detected = ["vanilla"]

    logger.info(f"Detected pack types: {detected} | scores: {scores}")
    return {"types": detected, "scores": scores}


# ---------------------------------------------------------------------------
# detect_base_version
# ---------------------------------------------------------------------------

def detect_base_version(pack_dir: str) -> dict:
    """
    Read pack.mcmeta and return:
      format            int
      version           str  (closest known MC version)
      has_overlays      bool
      existing_overlays list[str]
    """
    mcmeta_path = os.path.join(pack_dir, "pack.mcmeta")
    if not os.path.exists(mcmeta_path):
        logger.warning("pack.mcmeta not found — defaulting to format 15 (1.20.1)")
        return {
            "format": 15,
            "version": "1.20.1",
            "has_overlays": False,
            "existing_overlays": []
        }

    try:
        data = json.load(open(mcmeta_path, encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse pack.mcmeta: {e}")
        return {
            "format": 15,
            "version": "1.20.1",
            "has_overlays": False,
            "existing_overlays": []
        }

    fmt          = data.get("pack", {}).get("pack_format", 15)
    has_overlays = "overlays" in data
    existing     = [
        e.get("directory", "")
        for e in data.get("overlays", {}).get("entries", [])
    ]

    # Map to known version: find closest format key
    known_formats = sorted(PACK_FORMATS.keys())
    closest = min(known_formats, key=lambda x: abs(x - fmt))
    version = PACK_FORMATS[closest]

    logger.info(
        f"Base format: {fmt} → {version} "
        f"| has_overlays: {has_overlays} "
        f"| existing: {existing}"
    )
    return {
        "format": fmt,
        "version": version,
        "has_overlays": has_overlays,
        "existing_overlays": existing
    }


# ---------------------------------------------------------------------------
# Strip helpers
# ---------------------------------------------------------------------------

def strip_optifine_cit(pack_dir: str) -> int:
    """Remove OptiFine CIT folders (incompatible with 1.21.4+)."""
    cit_paths = [
        os.path.join(pack_dir, "assets", "minecraft", "optifine", "cit"),
        os.path.join(pack_dir, "optifine", "cit"),
        os.path.join(pack_dir, "assets", "optifine", "cit"),
    ]
    removed = 0
    for path in cit_paths:
        if os.path.exists(path):
            try:
                props   = glob.glob(f"{path}/**/*.properties", recursive=True)
                removed += len(props)
                shutil.rmtree(path)
                logger.info(f"Removed OptiFine CIT: {path} ({len(props)} files)")
            except Exception as e:
                logger.error(f"Failed to remove CIT {path}: {e}")
    if removed:
        logger.info(f"✓ Stripped {removed} OptiFine CIT file(s)")
    return removed


def strip_shaders(pack_dir: str) -> int:
    """Remove assets/minecraft/shaders/ (incompatible with 1.21.4+)."""
    shader_paths = [
        os.path.join(pack_dir, "assets", "minecraft", "shaders"),
    ]
    removed = 0
    for path in shader_paths:
        if os.path.exists(path):
            try:
                files   = glob.glob(f"{path}/**/*", recursive=True)
                removed += len([f for f in files if os.path.isfile(f)])
                shutil.rmtree(path)
                logger.info(f"Removed shaders: {path} ({removed} files)")
            except Exception as e:
                logger.error(f"Failed to remove shaders {path}: {e}")
    if removed:
        logger.info(f"✓ Stripped {removed} shader file(s)")
    return removed
