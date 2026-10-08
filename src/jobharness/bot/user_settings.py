"""User settings overlay (plan step 4.4).

Bot mode never edits tracked files. The Principal's choices live in
``<data_dir>/user_settings.yaml`` (deep-merged over ``config/config.yaml``) and
``<data_dir>/positioning.yaml`` (merged over the shipped positioning), and are
always validated through :class:`~jobharness.settings.Settings` /
:class:`~jobharness.schemas.positioning.Positioning` before being written.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from jobharness.schemas.archetype import Archetype, load_archetypes
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile, load_profile
from jobharness.settings import Settings

USER_SETTINGS = "user_settings.yaml"
POSITIONING_OVERLAY = "positioning.yaml"
PROFILE_FILE = "profile.yaml"


class MissingProfileError(RuntimeError):
    """No profile has been created yet."""


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _first_error(e: ValidationError) -> str:
    err = e.errors()[0]
    loc = ".".join(str(x) for x in err["loc"])
    return f"{loc}: {err['msg']}"


def _merged_settings_dict(config_path: Path, data_dir: Path, patch: dict[str, Any] | None) -> dict[str, Any]:
    raw = _read_yaml(config_path)
    raw.setdefault("ingest", {})["rss_feeds"] = []  # bot mode: user adds feeds explicitly
    raw.setdefault("paths", {})["data_dir"] = str(data_dir)
    raw["paths"]["output_dir"] = str(data_dir / "out")
    merged = deep_merge(raw, _read_yaml(data_dir / USER_SETTINGS))
    return deep_merge(merged, patch) if patch else merged


def load_settings(config_path: Path, data_dir: Path) -> Settings:
    return Settings.model_validate(_merged_settings_dict(config_path, data_dir, None))


def save_user_settings(config_path: Path, data_dir: Path, patch: dict[str, Any]) -> Settings:
    """Validate ``patch`` merged over current settings; write the overlay on success.

    Raises ``ValueError`` with a readable message when invalid (nothing is written).
    """
    try:
        settings = Settings.model_validate(_merged_settings_dict(config_path, data_dir, patch))
    except ValidationError as e:
        raise ValueError(_first_error(e)) from None
    overlay = deep_merge(_read_yaml(data_dir / USER_SETTINGS), patch)
    write_yaml_atomic(data_dir / USER_SETTINGS, overlay)
    return settings


def load_positioning(config_dir: Path, data_dir: Path) -> Positioning:
    base_path = config_dir / "positioning.yaml"
    if not base_path.exists():
        base_path = config_dir / "positioning.example.yaml"
    merged = deep_merge(_read_yaml(base_path), _read_yaml(data_dir / POSITIONING_OVERLAY))
    return Positioning.model_validate(merged)


def save_positioning(config_dir: Path, data_dir: Path, patch: dict[str, Any]) -> Positioning:
    base_path = config_dir / "positioning.yaml"
    if not base_path.exists():
        base_path = config_dir / "positioning.example.yaml"
    overlay = deep_merge(_read_yaml(data_dir / POSITIONING_OVERLAY), patch)
    try:
        pos = Positioning.model_validate(deep_merge(_read_yaml(base_path), overlay))
    except ValidationError as e:
        raise ValueError(_first_error(e)) from None
    write_yaml_atomic(data_dir / POSITIONING_OVERLAY, overlay)
    return pos


@dataclass
class Runtime:
    settings: Settings
    profile: Profile
    positioning: Positioning
    archetypes: dict[str, Archetype]
    data_dir: Path
    config_dir: Path


def profile_path(data_dir: Path) -> Path:
    return data_dir / PROFILE_FILE


def load_runtime(config_path: Path, data_dir: Path) -> Runtime:
    config_dir = config_path.parent
    pp = profile_path(data_dir)
    if not pp.exists():
        raise MissingProfileError("profile not created yet; send /profile_start")
    return Runtime(
        settings=load_settings(config_path, data_dir),
        profile=load_profile(str(pp)),
        positioning=load_positioning(config_dir, data_dir),
        archetypes=load_archetypes(config_dir / "archetypes"),
        data_dir=data_dir,
        config_dir=config_dir,
    )


__all__ = [
    "MissingProfileError",
    "Runtime",
    "deep_merge",
    "load_positioning",
    "load_runtime",
    "load_settings",
    "profile_path",
    "save_positioning",
    "save_user_settings",
    "write_yaml_atomic",
]
