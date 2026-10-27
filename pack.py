#!/usr/bin/env python3
"""打包 / 同步脚本。

    python pack.py --exe           # PyInstaller 单文件 -> dist/sgcc(.exe)
    python pack.py --sync-skill    # 把包同步进 ~/.claude/skills/sgcc/scripts
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = Path.home() / ".claude" / "skills" / "sgcc"


def build_exe():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--clean", "--noconfirm",
        "--name", "sgcc",
        "--collect-submodules", "gmssl",
        str(HERE / "entry.py"),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)
    exe = HERE / "dist" / ("sgcc.exe" if sys.platform == "win32" else "sgcc")
    print(f"built: {exe}")


def sync_skill():
    SKILL.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "skill" / "SKILL.md", SKILL / "SKILL.md")

    dst = SKILL / "scripts"
    pkg = dst / "sgcc"
    if pkg.exists():
        shutil.rmtree(pkg)
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        HERE / "sgcc", pkg,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("pyproject.toml", "README.md", "LICENSE", "pack.py", "entry.py"):
        shutil.copy2(HERE / name, dst / name)
    exe = HERE / "dist" / ("sgcc.exe" if sys.platform == "win32" else "sgcc")
    if exe.exists():
        shutil.copy2(exe, dst / exe.name)
        print(f"copied {exe.name}")
    print(f"synced -> {SKILL}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", action="store_true", help="用 PyInstaller 打单文件可执行")
    ap.add_argument("--sync-skill", action="store_true", help="同步到 Claude Skill 目录")
    args = ap.parse_args()
    if not (args.exe or args.sync_skill):
        ap.print_help()
        return 2
    if args.sync_skill:
        sync_skill()
    if args.exe:
        build_exe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
