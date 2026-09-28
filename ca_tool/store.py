"""Project persistence: one JSON file per project under projects/ (git-ignored)."""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .models import Intake, Project, now


def _dir(pid: str) -> Path:
    return config.PROJECTS_DIR / pid


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "project"


def create(intake: Intake) -> Project:
    base = slug(intake.client_name)
    pid, n = base, 2
    while _dir(pid).exists():
        pid, n = f"{base}-{n}", n + 1
    p = Project(id=pid, intake=intake)
    p.add_log("project created")
    save(p)
    return p


def save(p: Project) -> None:
    d = _dir(p.id)
    d.mkdir(parents=True, exist_ok=True)
    p.updated_at = now()
    tmp = d / "project.json.tmp"
    tmp.write_text(p.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(d / "project.json")


def load(pid: str) -> Project:
    return Project.model_validate_json((_dir(pid) / "project.json").read_text(encoding="utf-8"))


def list_ids() -> list[str]:
    if not config.PROJECTS_DIR.exists():
        return []
    return sorted(p.parent.name for p in config.PROJECTS_DIR.glob("*/project.json"))


def output_dir(pid: str) -> Path:
    d = _dir(pid) / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d
