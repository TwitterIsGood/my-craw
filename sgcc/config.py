"""路径与配置。

优先级：命令行/环境变量 > `~/.sgcc/config.json`（或 `$SGCC_HOME`）。
"""

import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("SGCC_HOME") or (Path.home() / ".sgcc")).expanduser()
SESSION_NAME = "session.json"
CONFIG_NAME = "config.json"


def app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def session_path(override=None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("SGCC_SESSION")
    if env:
        return Path(env).expanduser()
    p = APP_DIR / SESSION_NAME
    if p.exists():
        return p
    legacy = Path.cwd() / SESSION_NAME
    return legacy if legacy.exists() else p


def credentials() -> tuple[str, str]:
    cfg = load_json(APP_DIR / CONFIG_NAME, {}) or {}
    phone = os.environ.get("SGCC_PHONE") or cfg.get("phone", "")
    password = os.environ.get("SGCC_PASSWORD") or cfg.get("password", "")
    return phone, password
