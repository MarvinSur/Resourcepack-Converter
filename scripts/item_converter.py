#!/usr/bin/env python3
"""
item_converter.py
Converts old predicate-based overrides (pre-1.21.2) → new item.json format (1.21.2+)
Also generates overlay copies (old format) for backwards compat.
"""

import json, os, glob, logging, shutil
logger = logging.getLogger(__name__)


def _model_path(raw: str) -> str:
    """Normalize model path, strip namespace if minecraft:"""
    if raw.startswith("minecraft:"):
        return raw[len("minecraft:"):]
    return raw


def overrides_to_item_json(item_name: str, base_model: str, overrides: list) -> dict:
    """
    Convert overrides list → new item.json model definition.

    Handles:
    - custom_model_data  (Nexo, vanilla)
    - damage + damaged   (ItemsAdder)
    - pulling/pull       (bows)
    - blocking           (shields)
    """
    cases_cmd = []      # custom_model_data cases
    cases_damage = []   # damage/durability cases
    pulling_models = {} # bow pulling states {0: model, 1: model, ...}
    blocking_model = None
    default_model = _model_path(base_model)

    for ov in overrides:
        pred = ov.get("predicate", {})
        model = _model_path(ov.get("model", base_model))

        # Skip exact vanilla model references
        if model in [item_name, f"item/{item_name}"]:
            continue

        cmd = pred.get("custom_model_data")
        damage = pred.get("damage")
        pulling = pred.get("pulling")
        blocking = pred.get("blocking")

        if cmd is not None:
            cases_cmd.append({"when": int(cmd), "model": {"type": "minecraft:model", "model": model}})

        elif damage is not None and pulling is None:
            cases_damage.append({
                "when": float(round(damage, 4)),
                "model": {"type": "minecraft:model", "model": model}
            })

        elif pulling is not None:
            pull_val = pred.get("pull", 0.0)
            if pulling == 1:
                if pull_val >= 0.9:
                    pulling_models[2] = model
                elif pull_val >= 0.65:
                    pulling_models[1] = model
                else:
                    pulling_models[0] = model
            else:
                pulling_models[-1] = model  # standby

        elif blocking:
            blocking_model = model

    # Build model definition
    # Priority: custom_model_data > damage > pulling > blocking > default
    if cases_cmd:
        model_def = {
            "type": "minecraft:select",
            "property": "minecraft:custom_model_data",
            "cases": sorted(cases_cmd, key=lambda x: x["when"]),
            "fallback": {"type": "minecraft:model", "model": default_model}
        }
    elif pulling_models:
        model_def = {
            "type": "minecraft:select",
            "property": "minecraft:using_item",
            "cases": [
                {
                    "when": True,
                    "model": {
                        "type": "minecraft:select",
                        "property": "minecraft:charge_type",
                        "cases": [
                            {
                                "when": "bow",
                                "model": {
                                    "type": "minecraft:range_dispatch",
                                    "property": "minecraft:use_duration",
                                    "scale": 0.05,
                                    "entries": [
                                        {"threshold": t, "model": {"type": "minecraft:model", "model": m}}
                                        for t, m in sorted(
                                            {0: pulling_models.get(0, default_model),
                                             0.65: pulling_models.get(1, default_model),
                                             0.9: pulling_models.get(2, default_model)}.items()
                                        )
                                    ],
                                    "fallback": {"type": "minecraft:model", "model": default_model}
                                }
                            }
                        ],
                        "fallback": {"type": "minecraft:model", "model": default_model}
                    }
                }
            ],
            "fallback": {"type": "minecraft:model", "model": pulling_models.get(-1, default_model)}
        }
    elif blocking_model:
        model_def = {
            "type": "minecraft:select",
            "property": "minecraft:using_item",
            "cases": [
                {"when": True, "model": {"type": "minecraft:model", "model": blocking_model}}
            ],
            "fallback": {"type": "minecraft:model", "model": default_model}
        }
    elif cases_damage:
        model_def = {
            "type": "minecraft:range_dispatch",
            "property": "minecraft:damage",
            "entries": sorted(cases_damage, key=lambda x: x["when"]),
            "fallback": {"type": "minecraft:model", "model": default_model}
        }
    else:
        model_def = {"type": "minecraft:model", "model": default_model}

    return {"model": model_def}


def convert_pack_item_models(pack_dir: str, output_dir: str, overlay_id_new: str, overlay_id_old: str):
    """
    For each item model with overrides:
    1. Write item.json (new format) to output_dir/assets/minecraft/items/
    2. Write original model.json (old format) to output_dir/<overlay_id_old>/assets/*/models/item/
    """
    item_dir_out = os.path.join(output_dir, "assets", "minecraft", "items")
    os.makedirs(item_dir_out, exist_ok=True)

    converted = 0
    for model_file in glob.glob(f"{pack_dir}/assets/*/models/item/*.json"):
        try:
            data = json.load(open(model_file, encoding="utf-8"))
            overrides = data.get("overrides", [])
            if not overrides:
                continue

            item_name = os.path.basename(model_file).replace(".json", "")
            base_model = data.get("parent", f"minecraft:item/{item_name}")
            namespace = model_file.replace("\\", "/").split("/assets/")[1].split("/")[0]

            # Write item.json (1.21.2+ format)
            item_json = overrides_to_item_json(item_name, base_model, overrides)
            out_path = os.path.join(item_dir_out, f"{item_name}.json")
            json.dump(item_json, open(out_path, "w", encoding="utf-8"), indent=2)

            # Keep original model.json for old overlay
            overlay_model_dir = os.path.join(
                output_dir, overlay_id_old, "assets", namespace, "models", "item"
            )
            os.makedirs(overlay_model_dir, exist_ok=True)
            shutil.copy2(model_file, os.path.join(overlay_model_dir, os.path.basename(model_file)))

            converted += 1
        except Exception as e:
            logger.error(f"Failed to convert {model_file}: {e}")
            continue

    logger.info(f"Converted {converted} item models to item.json")
    return converted
