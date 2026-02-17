#!/usr/bin/env python3

import json, os, glob, logging
logger = logging.getLogger(__name__)

PACK_FORMATS = {
    15: "1.20.1",
    18: "1.20.2",
    22: "1.20.3",
    32: "1.20.5",
    34: "1.21.0",
    42: "1.21.2",
    46: "1.21.4",
    48: "1.21.5",
    50: "1.21.6",
    52: "1.21.7",
    54: "1.21.8",
    56: "1.21.9",
    57: "1.21.10",
}

# Overlay ranges: each entry covers a range of pack_format values
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
        "max_format":  99,
        "item_json":   True,
    },
]


def detect_pack_type(pack_dir: str) -> dict:
    """
    Returns ALL detected types (pack bisa gabungan ItemsAdder + ModelEngine, dll).
    'types' adalah list, bisa lebih dari 1.
    """
    scores = {"itemsadder": 0, "nexo": 0, "modelengine_v4": 0, "modelengine_v3": 0}

    # ItemsAdder: damage + damaged predicates together
    if os.path.exists(f"{pack_dir}/assets/itemsadder"):
        scores["itemsadder"] += 10
    for f in glob.glob(f"{pack_dir}/assets/*/models/item/*.json"):
        try:
            data = json.load(open(f))
            for ov in data.get("overrides", []):
                p = ov.get("predicate", {})
                if "damage" in p and "damaged" in p:
                    scores["itemsadder"] += 1
                    break
        except Exception:
            continue

    # Nexo: custom_model_data only (no damage)
    if os.path.exists(f"{pack_dir}/assets/nexo"):
        scores["nexo"] += 10
    for f in glob.glob(f"{pack_dir}/assets/*/models/item/*.json"):
        try:
            data = json.load(open(f))
            for ov in data.get("overrides", []):
                p = ov.get("predicate", {})
                if "custom_model_data" in p and "damage" not in p:
                    scores["nexo"] += 1
                    break
        except Exception:
            continue

    # ModelEngine v4: .geo.json + .animation.json (Blockbench format)
    me4 = (glob.glob(f"{pack_dir}/assets/*/geo/*.geo.json")
         + glob.glob(f"{pack_dir}/assets/*/animations/*.animation.json"))
    if me4:
        scores["modelengine_v4"] += len(me4) * 2
    if os.path.exists(f"{pack_dir}/assets/modelengine"):
        scores["modelengine_v4"] += 10

    # ModelEngine v3: models/entity legacy
    me3 = glob.glob(f"{pack_dir}/assets/*/models/entity/**/*.json", recursive=True)
    if me3:
        scores["modelengine_v3"] += len(me3)

    # Threshold: jika score > 0, dianggap detected
    THRESHOLD = 1
    detected = [t for t, s in scores.items() if s >= THRESHOLD]

    # ME v3 dan v4 tidak mungkin bersamaan — ambil yang lebih tinggi
    if "modelengine_v4" in detected and "modelengine_v3" in detected:
        if scores["modelengine_v4"] >= scores["modelengine_v3"]:
            detected.remove("modelengine_v3")
        else:
            detected.remove("modelengine_v4")

    if not detected:
        detected = ["vanilla"]

    logger.info(f"Detected types: {detected} | scores: {scores}")
    return {"types": detected, "scores": scores}


def detect_base_version(pack_dir: str) -> dict:
    mcmeta = os.path.join(pack_dir, "pack.mcmeta")
    if not os.path.exists(mcmeta):
        logger.warning("pack.mcmeta not found, defaulting to format 15 (1.20.1)")
        return {"format": 15, "version": "1.20.1", "has_overlays": False, "existing_overlays": []}

    data = json.load(open(mcmeta, encoding="utf-8"))
    fmt = data.get("pack", {}).get("pack_format", 15)
    has_overlays = "overlays" in data
    existing = [e.get("directory", "") for e in data.get("overlays", {}).get("entries", [])]

    # Find closest known version
    closest = min(PACK_FORMATS.keys(), key=lambda x: abs(x - fmt))
    version = PACK_FORMATS[closest]

    logger.info(f"Base format: {fmt} → {version} | existing overlays: {existing}")
    return {"format": fmt, "version": version, "has_overlays": has_overlays, "existing_overlays": existing}
