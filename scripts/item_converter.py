#!/usr/bin/env python3
"""
item_converter.py
=================
Converts old-style predicate model JSON (1.20.x format) into new-style
assets/minecraft/items/*.json (1.21.2+ format), mirroring what ItemsAdder v4
generates for pack-noe.

Target root format  : range_dispatch + custom_model_data + index:0
Old overlay format  : untouched models/item/*.json  (predicates)

Supported predicate types per item:
  - custom_model_data          → range_dispatch / threshold (integer CMD)
  - bow / pulling              → condition (using_item) + range_dispatch (use_duration)
  - crossbow / charge_type     → condition (using_item) → select (charge_type)
  - blocking (shield)          → condition (using_item) + special shield model
  - damage / damaged           → range_dispatch (damage)
  - leather armor (dye)        → select (trim_material) + dye tint
"""

import json, os, glob, logging, shutil, copy
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mp(raw: str) -> str:
    """Normalize model path: strip 'minecraft:' prefix."""
    if raw.startswith("minecraft:"):
        return raw[len("minecraft:"):]
    return raw


def _model(path: str) -> dict:
    return {"type": "minecraft:model", "model": path}


def _model_short(path: str) -> dict:
    """Without namespace prefix for short form used in items/ files."""
    return {"type": "model", "model": path}


# ---------------------------------------------------------------------------
# Default fallback builders — mirrors vanilla 1.21.4 item JSON structure
# ---------------------------------------------------------------------------

BOW_FALLBACK = {
    "type": "minecraft:condition",
    "property": "minecraft:using_item",
    "on_true": {
        "type": "minecraft:range_dispatch",
        "property": "minecraft:use_duration",
        "scale": 0.05,
        "fallback": _model("minecraft:item/bow_pulling_0"),
        "entries": [
            {"threshold": 0.65, "model": _model("minecraft:item/bow_pulling_1")},
            {"threshold": 0.9,  "model": _model("minecraft:item/bow_pulling_2")},
        ]
    },
    "on_false": _model("minecraft:item/bow")
}

CROSSBOW_FALLBACK = {
    "type": "minecraft:condition",
    "property": "minecraft:using_item",
    "on_true": {
        "type": "minecraft:range_dispatch",
        "property": "minecraft:crossbow/pull",
        "fallback": _model("minecraft:item/crossbow_pulling_0"),
        "entries": [
            {"threshold": 0.58, "model": _model("minecraft:item/crossbow_pulling_1")},
            {"threshold": 1.0,  "model": _model("minecraft:item/crossbow_pulling_2")},
        ]
    },
    "on_false": {
        "type": "minecraft:select",
        "property": "minecraft:charge_type",
        "fallback": _model("minecraft:item/crossbow"),
        "cases": [
            {"when": "arrow",  "model": _model("minecraft:item/crossbow_arrow")},
            {"when": "rocket", "model": _model("minecraft:item/crossbow_firework")},
        ]
    }
}

SHIELD_FALLBACK = {
    "type": "minecraft:condition",
    "property": "minecraft:using_item",
    "on_true": {
        "type": "minecraft:special",
        "base": "minecraft:item/shield_blocking",
        "model": {"type": "minecraft:shield"}
    },
    "on_false": {
        "type": "minecraft:special",
        "base": "minecraft:item/shield",
        "model": {"type": "minecraft:shield"}
    }
}

LEATHER_TRIM_MATERIALS = [
    "minecraft:quartz","minecraft:iron","minecraft:netherite","minecraft:redstone",
    "minecraft:copper","minecraft:gold","minecraft:emerald","minecraft:diamond",
    "minecraft:lapis","minecraft:amethyst","minecraft:resin"
]

def _leather_trim_cases(base_model_name: str) -> list:
    """Generate trim material cases for leather armor."""
    suffix_map = {
        "minecraft:quartz":    "quartz_trim",
        "minecraft:iron":      "iron_trim",
        "minecraft:netherite": "netherite_trim",
        "minecraft:redstone":  "redstone_trim",
        "minecraft:copper":    "copper_trim",
        "minecraft:gold":      "gold_trim",
        "minecraft:emerald":   "emerald_trim",
        "minecraft:diamond":   "diamond_trim",
        "minecraft:lapis":     "lapis_trim",
        "minecraft:amethyst":  "amethyst_trim",
        "minecraft:resin":     "resin_trim",
    }
    cases = []
    for mat, suffix in suffix_map.items():
        cases.append({
            "when": mat,
            "model": {
                "type": "minecraft:model",
                "model": f"minecraft:item/{base_model_name}_{suffix}",
                "tints": [{"type": "minecraft:dye", "default": -6265536}]
            }
        })
    return cases


def _leather_armor_fallback(item_name: str) -> dict:
    return {
        "type": "model",
        "property": "minecraft:trim_material",
        "model": f"item/{item_name}",
        "tints": [{"type": "dye", "default": -6265536}],
        "cases": _leather_trim_cases(item_name),
        "fallback": {
            "type": "minecraft:model",
            "model": f"minecraft:item/{item_name}",
            "tints": [{"type": "minecraft:dye", "default": -6265536}]
        }
    }


def _leather_armor_entry(item_name: str, custom_model: str) -> dict:
    """Entry for a custom leather armor piece under a CMD threshold."""
    return {
        "type": "model",
        "property": "minecraft:trim_material",
        "model": custom_model,
        "tints": [{"type": "dye", "default": -6265536}],
        "cases": _leather_trim_cases(item_name),
        "fallback": {
            "type": "minecraft:model",
            "model": f"minecraft:item/{item_name}",
            "tints": [{"type": "minecraft:dye", "default": -6265536}]
        }
    }


# ---------------------------------------------------------------------------
# Detect item category from item name
# ---------------------------------------------------------------------------

BOW_ITEMS       = {"bow"}
CROSSBOW_ITEMS  = {"crossbow"}
SHIELD_ITEMS    = {"shield"}
FISHING_ITEMS   = {"fishing_rod"}
LEATHER_ARMOR   = {
    "leather_helmet", "leather_chestplate", "leather_leggings",
    "leather_boots", "leather_horse_armor"
}

def _item_category(item_name: str) -> str:
    if item_name in BOW_ITEMS:       return "bow"
    if item_name in CROSSBOW_ITEMS:  return "crossbow"
    if item_name in SHIELD_ITEMS:    return "shield"
    if item_name in FISHING_ITEMS:   return "fishing_rod"
    if item_name in LEATHER_ARMOR:   return "leather_armor"
    return "generic"


# ---------------------------------------------------------------------------
# Parse predicates into CMD buckets
# ---------------------------------------------------------------------------

def _parse_predicates(overrides: list, item_name: str, base_model: str) -> dict:
    """
    Parse old-style overrides list into a dict keyed by CMD value.
    Returns: {cmd_int: model_path_str}
    Also handles special pulling/blocking predicates (grouped under CMD if present).
    """
    buckets = {}   # cmd -> model
    for ov in overrides:
        pred  = ov.get("predicate", {})
        model = _mp(ov.get("model", base_model))
        cmd   = pred.get("custom_model_data")
        if cmd is not None:
            buckets[int(cmd)] = model
    return buckets


def _parse_bow_predicates(overrides: list, base_model: str):
    """
    Returns list of (cmd, base_model, pull0, pull65, pull90) tuples.
    Groups pulling variants together with their CMD.
    """
    cmd_models   = {}   # cmd -> default model
    pulling_sets = {}   # cmd -> {0: m, 0.65: m, 0.9: m}

    for ov in overrides:
        pred  = ov.get("predicate", {})
        model = _mp(ov.get("model", base_model))
        cmd   = pred.get("custom_model_data")
        pull  = pred.get("pulling")

        if pull is not None:
            # This is a pulling variant
            pull_val = pred.get("pull", 0.0)
            if cmd is not None:
                if cmd not in pulling_sets:
                    pulling_sets[cmd] = {}
                if pull == 1:
                    if pull_val >= 0.9:
                        pulling_sets[cmd][0.9] = model
                    elif pull_val >= 0.65:
                        pulling_sets[cmd][0.65] = model
                    else:
                        pulling_sets[cmd][0.0] = model
            continue

        if cmd is not None:
            cmd_models[int(cmd)] = model

    results = []
    for cmd in sorted(cmd_models.keys()):
        m    = cmd_models[cmd]
        pset = pulling_sets.get(cmd, {})
        results.append({
            "cmd":     cmd,
            "model":   m,
            "pull_0":  pset.get(0.0,  m),
            "pull_65": pset.get(0.65, m),
            "pull_90": pset.get(0.9,  m),
        })
    return results


# ---------------------------------------------------------------------------
# Build item.json per category
# ---------------------------------------------------------------------------

def _build_generic(item_name: str, base_model: str, overrides: list) -> dict:
    """Standard CMD range_dispatch."""
    buckets = _parse_predicates(overrides, item_name, base_model)
    default = _mp(base_model)
    entries = []
    for cmd in sorted(buckets.keys()):
        entries.append({
            "threshold": cmd,
            "model": {"type": "model", "model": buckets[cmd]}
        })
    if not entries:
        return {"model": _model(default)}

    return {
        "model": {
            "type": "range_dispatch",
            "property": "custom_model_data",
            "index": 0,
            "fallback": _model(f"minecraft:item/{item_name}"),
            "entries": entries
        },
        "oversized_in_gui": True
    }


def _build_bow(item_name: str, base_model: str, overrides: list) -> dict:
    bow_entries = _parse_bow_predicates(overrides, base_model)
    default = _mp(base_model)
    entries = []
    for b in bow_entries:
        entry_model = {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_false": {"type": "model", "model": b["model"]},
            "on_true": {
                "type": "minecraft:range_dispatch",
                "property": "minecraft:use_duration",
                "scale": 0.05,
                "fallback": {"type": "model", "model": b["pull_0"]},
                "entries": [
                    {"threshold": 0.65, "model": {"type": "model", "model": b["pull_65"]}},
                    {"threshold": 0.9,  "model": {"type": "model", "model": b["pull_90"]}},
                ]
            }
        }
        entries.append({"threshold": b["cmd"], "model": entry_model})

    if not entries:
        return {"model": copy.deepcopy(BOW_FALLBACK)}

    # Last entry: vanilla fallback at end (mirrors pack-noe pattern)
    return {
        "model": {
            "type": "range_dispatch",
            "property": "custom_model_data",
            "index": 0,
            "fallback": copy.deepcopy(BOW_FALLBACK),
            "entries": entries
        },
        "oversized_in_gui": True
    }


def _build_crossbow(item_name: str, base_model: str, overrides: list) -> dict:
    buckets = _parse_predicates(overrides, item_name, base_model)
    entries = []
    for cmd in sorted(buckets.keys()):
        m = buckets[cmd]
        # Each CMD entry: condition using_item → charged select / pulling
        entry_model = {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_false": {
                "type": "minecraft:select",
                "property": "minecraft:charge_type",
                "model": m,
                "fallback": {"type": "model", "model": m},
                "cases": [
                    {"when": "arrow",  "model": {"type": "model", "model": f"{m}_charged"}},
                    {"when": "rocket", "model": {"type": "model", "model": f"{m}_firework"}},
                ]
            },
            "on_true": {
                "type": "minecraft:range_dispatch",
                "property": "minecraft:crossbow/pull",
                "fallback": {"type": "model", "model": m},
                "entries": [
                    {"threshold": 0.58, "model": {"type": "model", "model": f"{m}_1"}},
                    {"threshold": 1.0,  "model": {"type": "model", "model": f"{m}_2"}},
                ]
            }
        }
        entries.append({"threshold": cmd, "model": entry_model})

    if not entries:
        return {"model": copy.deepcopy(CROSSBOW_FALLBACK)}

    return {
        "model": {
            "type": "range_dispatch",
            "property": "custom_model_data",
            "index": 0,
            "fallback": copy.deepcopy(CROSSBOW_FALLBACK),
            "entries": entries
        },
        "oversized_in_gui": True
    }


def _build_shield(item_name: str, base_model: str, overrides: list) -> dict:
    buckets = _parse_predicates(overrides, item_name, base_model)
    entries = []
    for cmd in sorted(buckets.keys()):
        m = buckets[cmd]
        entry_model = {
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_false": {
                "type": "model",
                "base": "minecraft:item/shield",
                "model": m
            },
            "on_true": {
                "type": "model",
                "base": "minecraft:item/shield_blocking",
                "model": f"{m}_blocking" if not m.endswith("_blocking") else m
            }
        }
        entries.append({"threshold": cmd, "model": entry_model})

    if not entries:
        return {"model": copy.deepcopy(SHIELD_FALLBACK)}

    return {
        "model": {
            "type": "range_dispatch",
            "property": "custom_model_data",
            "index": 0,
            "fallback": copy.deepcopy(SHIELD_FALLBACK),
            "entries": entries
        },
        "oversized_in_gui": True
    }


def _build_leather_armor(item_name: str, base_model: str, overrides: list) -> dict:
    buckets = _parse_predicates(overrides, item_name, base_model)
    entries = []
    for cmd in sorted(buckets.keys()):
        m = buckets[cmd]
        entries.append({
            "threshold": cmd,
            "model": _leather_armor_entry(item_name, m)
        })

    if not entries:
        return {"model": _leather_armor_fallback(item_name)}

    return {
        "model": {
            "type": "range_dispatch",
            "property": "custom_model_data",
            "index": 0,
            "fallback": _leather_armor_fallback(item_name),
            "entries": entries
        },
        "oversized_in_gui": True
    }


def _build_fishing_rod(item_name: str, base_model: str, overrides: list) -> dict:
    # fishing_rod uses cast predicate (not pulling), treat as generic CMD
    return _build_generic(item_name, base_model, overrides)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def overrides_to_item_json(item_name: str, base_model: str, overrides: list) -> dict:
    cat = _item_category(item_name)
    if cat == "bow":
        return _build_bow(item_name, base_model, overrides)
    elif cat == "crossbow":
        return _build_crossbow(item_name, base_model, overrides)
    elif cat == "shield":
        return _build_shield(item_name, base_model, overrides)
    elif cat == "leather_armor":
        return _build_leather_armor(item_name, base_model, overrides)
    else:
        return _build_generic(item_name, base_model, overrides)


# ---------------------------------------------------------------------------
# Pack-level conversion
# ---------------------------------------------------------------------------

def convert_pack_item_models(pack_dir: str, output_dir: str,
                              overlay_id_new: str = "overlay_v1_21_4",
                              overlay_id_old: str = "overlay_v1_20_5"):
    """
    1. Scan all assets/*/models/item/*.json that have 'overrides'
    2. Generate assets/minecraft/items/<item>.json in output root  (1.21.2+ format)
    3. Copy original predicate model files into EVERY old overlay dir
       so that versions < 1.21.2 still get the correct predicates.

    Old overlays that need the original predicate models:
        overlay_v1_20_1   (format 15–17)
        overlay_v1_20_2   (format 18–31)
        overlay_v1_20_5   (format 32–41)
    """
    from detector import OVERLAY_RANGES

    item_dir_out = os.path.join(output_dir, "assets", "minecraft", "items")
    os.makedirs(item_dir_out, exist_ok=True)

    # Collect all old overlays that should NOT have item.json
    old_overlays = [o["id"] for o in OVERLAY_RANGES if not o["item_json"]]

    converted = 0
    for model_file in glob.glob(f"{pack_dir}/assets/*/models/item/*.json"):
        try:
            data      = json.load(open(model_file, encoding="utf-8"))
            overrides = data.get("overrides", [])
            if not overrides:
                continue

            item_name  = os.path.basename(model_file).replace(".json", "")
            base_model = data.get("parent", f"minecraft:item/{item_name}")
            namespace  = model_file.replace("\\", "/").split("/assets/")[1].split("/")[0]

            # --- Write item.json (1.21.2+ format) ---
            item_json = overrides_to_item_json(item_name, base_model, overrides)
            out_path  = os.path.join(item_dir_out, f"{item_name}.json")
            json.dump(item_json, open(out_path, "w", encoding="utf-8"), indent=2)

            # --- Copy original model.json to ALL old overlays ---
            for ov_id in old_overlays:
                ov_model_dir = os.path.join(
                    output_dir, ov_id, "assets", namespace, "models", "item"
                )
                os.makedirs(ov_model_dir, exist_ok=True)
                shutil.copy2(model_file, os.path.join(ov_model_dir, os.path.basename(model_file)))

            converted += 1

        except Exception as e:
            logger.error(f"Failed to convert {model_file}: {e}", exc_info=True)
            continue

    logger.info(f"Converted {converted} item models → items/*.json")
    return converted
