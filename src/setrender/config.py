"""Template loading and parameter resolution.

Precedence (last wins): template file < --params file < --keywords < --set key=value.
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


def find_template(name_or_path: str) -> Path:
    p = Path(name_or_path).expanduser()
    if p.is_file():
        return p
    for cand in (TEMPLATE_DIR / name_or_path, TEMPLATE_DIR / f"{name_or_path}.tpl"):
        if cand.is_file():
            return cand
    raise SystemExit(f"setrender: template '{name_or_path}' not found (looked in {TEMPLATE_DIR})")


def list_templates() -> list[Path]:
    return sorted(TEMPLATE_DIR.glob("*.tpl"))


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def set_path(d: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


def get_path(d: dict, dotted: str, default=None):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def parse_set(expr: str) -> tuple[str, object]:
    if "=" not in expr:
        raise SystemExit(f"setrender: --set expects key=value, got '{expr}'")
    k, v = expr.split("=", 1)
    return k.strip(), yaml.safe_load(v)


def resolve(template: str, params_file: str | None, keywords: list[str], sets: list[str]) -> dict:
    path = find_template(template)
    cfg = yaml.safe_load(path.read_text()) or {}
    cfg["_template_path"] = str(path)
    if params_file:
        cfg = deep_merge(cfg, yaml.safe_load(Path(params_file).read_text()) or {})
    kwmap = cfg.get("keywords", {}) or {}
    for kw in keywords:
        for dotted, val in (kwmap.get(kw) or {}).items():
            if dotted == "palette_order":
                set_path(cfg, "variation.palette_order", val)
                set_path(cfg, "variation.shuffle_palettes", False)
            else:
                set_path(cfg, dotted, copy.deepcopy(val))
    for s in sets:
        k, v = parse_set(s)
        set_path(cfg, k, v)
    cfg["_keywords"] = list(keywords)
    return cfg
