from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

from app_ui.versioning import get_build_info


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path)


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _write_build_info(target_dir: Path) -> None:
    info = get_build_info()
    target = target_dir / "BUILD_INFO.txt"
    target.write_text(json.dumps(info, indent=2), encoding="utf-8")


def _prepare_spec(spec: Path, root: Path) -> Path:
    spec_text = spec.read_text(encoding="utf-8")
    root_posix = root.as_posix()
    entry_path = f"{root_posix}/app_ui/main.py"
    spec_text = spec_text.replace("['app_ui/main.py']", f"[r'{entry_path}']")
    spec_text = spec_text.replace("pathex=['.']", f"pathex=[r'{root_posix}']")
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".spec", mode="w", encoding="utf-8")
    temp.write(spec_text)
    temp.close()
    return Path(temp.name)


def build_release(out_dir: str, spec_path: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    out_path = _resolve_path(root, out_dir)
    spec = _resolve_path(root, spec_path)
    if not spec.exists():
        raise FileNotFoundError(f"Spec not found: {spec}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    work_dir = root / "build" / "pyinstaller" / "work"
    resolved_spec = _prepare_spec(spec, root)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(resolved_spec),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(out_path.parent),
        "--workpath",
        str(work_dir),
        "--log-level=INFO",
    ]
    print(f"PyInstaller command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        resolved_spec.unlink(missing_ok=True)
        raise RuntimeError(
            "PyInstaller build failed\n"
            f"stdout:\n{result.stdout}\n\n"
            f"stderr:\n{result.stderr}\n"
        )
    resolved_spec.unlink(missing_ok=True)

    built_root = out_path.parent / out_path.name
    if not built_root.exists():
        raise RuntimeError(f"Expected build output not found: {built_root}")

    asset_roots = [
        "content_repo",
        "content_store",
        "ui_repo",
        "ui_store",
        "component_repo",
        "component_store",
        "schemas",
    ]
    for rel in asset_roots:
        src = root / rel
        dst = built_root / rel
        _copy_tree(src, dst)

    _write_build_info(built_root)
    return built_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PhysicsLab Windows release bundle")
    parser.add_argument("--out", default="dist/PhysicsLab", help="Output folder for release bundle")
    parser.add_argument(
        "--spec",
        default="build/pyinstaller/physicslab.spec",
        help="PyInstaller spec file",
    )
    args = parser.parse_args()
    build_release(args.out, args.spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
