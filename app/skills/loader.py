"""扫描 skills/ 目录，加载技能清单并动态注册工具。"""

import importlib.util
import json
from pathlib import Path
from typing import Any


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


def discover_skills() -> dict[str, dict]:
    """扫描 skills/ 目录，返回 {name: manifest}。"""
    found: dict[str, dict] = {}
    if not SKILLS_DIR.is_dir():
        return found
    for entry in sorted(SKILLS_DIR.iterdir()):
        manifest_path = entry / "skill.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(manifest, dict) and manifest.get("name"):
            manifest["_dir"] = str(entry)
            found[manifest["name"]] = manifest
    return found


def list_skills() -> list[dict]:
    """返回按名称排序的技能清单（不含内部字段）。"""
    return [
        {k: v for k, v in m.items() if not k.startswith("_")}
        for m in discover_skills().values()
    ]


def load_skill_module(manifest: dict) -> Any | None:
    """按清单 entry 导入技能模块。"""
    entry = manifest.get("entry") or "skill.py"
    module_path = Path(manifest["_dir"]) / entry
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(
        f"app.skills.dynamic.{manifest['name']}", module_path
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def get_skill_tools(config: dict) -> dict[str, dict]:
    """返回管理配置中的技能开关配置。"""
    return config.get("skills", {})


def get_skill_config(config: dict, name: str) -> dict | None:
    """按名称返回某技能的配置（未收录返回 None）。"""
    return get_skill_tools(config).get(name)


def skill_available(name: str) -> bool:
    """技能是否存在于 skills/ 目录。"""
    return name in discover_skills()


def skill_enabled(config: dict, name: str) -> bool:
    """技能是否已在管理配置中启用。"""
    skills = config.setdefault("skills", {})
    return bool(skills.get(name, {}).get("enabled", False))


def set_skill_enabled(config: dict, name: str, enabled: bool) -> bool:
    """在管理配置中启用/停用技能。返回是否成功。"""
    if not skill_available(name):
        return False
    skills = config.setdefault("skills", {})
    entry = skills.setdefault(name, {})
    entry["enabled"] = bool(enabled)
    return True


def skill_display(manifest: dict, lang: str) -> dict:
    """按界面语言返回技能展示信息。"""
    return {
        "name": manifest.get("name", ""),
        "title": manifest.get("title_zh" if lang == "zh" else "title", manifest.get("title", "")),
        "description": manifest.get("description_zh" if lang == "zh" else "description", ""),
    }
