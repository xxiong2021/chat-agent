"""Skill 插件框架：发现、加载和注册技能工具。"""

from app.skills.loader import (
    discover_skills,
    get_skill_config,
    get_skill_tools,
    load_skill_module,
    list_skills,
    set_skill_enabled,
    skill_available,
    skill_display,
    skill_enabled,
)

__all__ = [
    "discover_skills",
    "get_skill_config",
    "get_skill_tools",
    "load_skill_module",
    "list_skills",
    "set_skill_enabled",
    "skill_available",
    "skill_display",
    "skill_enabled",
]
