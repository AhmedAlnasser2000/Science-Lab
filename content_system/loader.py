import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATUS_READY = "READY"
STATUS_NOT_INSTALLED = "NOT_INSTALLED"
STATUS_UNAVAILABLE = "UNAVAILABLE"

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_BASE = REPO_ROOT / "content_repo" / "physics_v1"
STORE_BASE = REPO_ROOT / "content_store" / "physics_v1"


def _load_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "missing file"
    except OSError as exc:
        return None, f"io error: {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc.msg}"


def _collect_asset_paths(manifest: Dict[str, Any]) -> List[str]:
    assets: List[str] = []
    seen = set()

    def _add(path: Optional[str]) -> None:
        if isinstance(path, str):
            normalized = path.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                assets.append(normalized)

    content = manifest.get("content")
    if isinstance(content, dict):
        _add(content.get("asset_path"))

    x_ext = manifest.get("x_extensions")
    if isinstance(x_ext, dict):
        guides = x_ext.get("guides")
        if isinstance(guides, dict):
            for value in guides.values():
                _add(value)

    return assets


def _extract_lab_metadata(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    x_ext = manifest.get("x_extensions")
    if not isinstance(x_ext, dict):
        return None
    lab_ext = x_ext.get("lab")
    if not isinstance(lab_ext, dict):
        return None
    lab_id = lab_ext.get("lab_id")
    if not isinstance(lab_id, str) or not lab_id.strip():
        return None
    info: Dict[str, Any] = {"lab_id": lab_id.strip()}
    entry = lab_ext.get("entry")
    if isinstance(entry, str) and entry.strip():
        info["entry"] = entry.strip()
    recommended = lab_ext.get("recommended_profile")
    if isinstance(recommended, str):
        info["recommended_profile"] = recommended
    return info


def _safe_relative(path: Path, base: Path) -> Optional[Path]:
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def _compute_part_status(repo_manifest_path: Path, repo_manifest: Dict[str, Any]) -> Tuple[str, str]:
    assets = _collect_asset_paths(repo_manifest)
    rel_manifest = _safe_relative(repo_manifest_path, REPO_BASE)
    if rel_manifest is None:
        return STATUS_UNAVAILABLE, "part manifest is outside the repo root"

    store_manifest_path = STORE_BASE / rel_manifest
    if not store_manifest_path.exists():
        return STATUS_NOT_INSTALLED, "part manifest not present in content_store"

    store_manifest, store_err = _load_json(store_manifest_path)
    if store_manifest is None:
        return STATUS_UNAVAILABLE, f"installed manifest unreadable: {store_err}"

    for asset in assets:
        store_asset = STORE_BASE / asset
        if not store_asset.exists():
            return STATUS_NOT_INSTALLED, f"missing asset in store: {asset}"

    return STATUS_READY, ""


def _find_part_in_repo(part_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    module_manifest_path = REPO_BASE / "module_manifest.json"
    module_manifest, module_err = _load_json(module_manifest_path)
    if module_manifest is None:
        return None, f"module manifest unavailable: {module_err}"

    issues: List[str] = []
    for section_stub in module_manifest.get("sections", []):
        section_rel = section_stub.get("manifest_path")
        section_path = module_manifest_path.parent / section_rel if isinstance(section_rel, str) else None
        if section_path is None:
            issues.append(f"section entry missing manifest_path for id {section_stub.get('section_id', '?')}")
            continue

        section_manifest, section_err = _load_json(section_path)
        if section_manifest is None:
            issues.append(f"section {section_stub.get('section_id', '?')}: {section_err}")
            continue

        for package_stub in section_manifest.get("packages", []):
            package_rel = package_stub.get("manifest_path")
            package_path = section_path.parent / package_rel if isinstance(package_rel, str) else None
            if package_path is None:
                issues.append(f"package entry missing manifest_path for id {package_stub.get('package_id', '?')}")
                continue

            package_manifest, package_err = _load_json(package_path)
            if package_manifest is None:
                issues.append(f"package {package_stub.get('package_id', '?')}: {package_err}")
                continue

            for part_stub in package_manifest.get("parts", []):
                if part_stub.get("part_id") != part_id:
                    continue

                part_rel = part_stub.get("manifest_path")
                part_path = package_path.parent / part_rel if isinstance(part_rel, str) else None
                if part_path is None:
                    return None, f"part manifest_path missing for id {part_id}"

                return {
                    "module_id": module_manifest.get("module_id"),
                    "section_id": section_manifest.get("section_id"),
                    "package_id": package_manifest.get("package_id"),
                    "part_manifest_path": part_path,
                    "module_manifest_path": module_manifest_path,
                    "section_manifest_path": section_path,
                    "package_manifest_path": package_path,
                }, None

    if issues:
        return None, f"part not found; issues encountered: {'; '.join(issues)}"
    return None, "part not declared in module"


def list_tree() -> Dict[str, Any]:
    module_manifest_path = REPO_BASE / "module_manifest.json"
    module_manifest, module_err = _load_json(module_manifest_path)
    if module_manifest is None:
        return {
            "module": None,
            "status": STATUS_UNAVAILABLE,
            "reason": f"module manifest unavailable: {module_err}",
        }

    module_entry: Dict[str, Any] = {
        "module_id": module_manifest.get("module_id"),
        "title": module_manifest.get("title"),
        "sections": [],
    }

    for section_stub in module_manifest.get("sections", []):
        section_rel = section_stub.get("manifest_path")
        section_path = module_manifest_path.parent / section_rel if isinstance(section_rel, str) else None
        if section_path is None:
            module_entry["sections"].append(
                {
                    "section_id": section_stub.get("section_id"),
                    "title": section_stub.get("title"),
                    "status": STATUS_UNAVAILABLE,
                    "reason": "missing section manifest path",
                    "packages": [],
                }
            )
            continue

        section_manifest, section_err = _load_json(section_path)
        if section_manifest is None:
            module_entry["sections"].append(
                {
                    "section_id": section_stub.get("section_id"),
                    "title": section_stub.get("title"),
                    "status": STATUS_UNAVAILABLE,
                    "reason": f"section manifest unavailable: {section_err}",
                    "packages": [],
                }
            )
            continue

        section_entry: Dict[str, Any] = {
            "section_id": section_manifest.get("section_id"),
            "title": section_manifest.get("title"),
            "packages": [],
        }

        for package_stub in section_manifest.get("packages", []):
            package_rel = package_stub.get("manifest_path")
            package_path = section_path.parent / package_rel if isinstance(package_rel, str) else None
            if package_path is None:
                section_entry["packages"].append(
                    {
                        "package_id": package_stub.get("package_id"),
                        "title": package_stub.get("title"),
                        "status": STATUS_UNAVAILABLE,
                        "reason": "missing package manifest path",
                        "parts": [],
                    }
                )
                continue

            package_manifest, package_err = _load_json(package_path)
            if package_manifest is None:
                section_entry["packages"].append(
                    {
                        "package_id": package_stub.get("package_id"),
                        "title": package_stub.get("title"),
                        "status": STATUS_UNAVAILABLE,
                        "reason": f"package manifest unavailable: {package_err}",
                        "parts": [],
                    }
                )
                continue

            package_entry: Dict[str, Any] = {
                "package_id": package_manifest.get("package_id"),
                "title": package_manifest.get("title"),
                "parts": [],
            }

            for part_stub in package_manifest.get("parts", []):
                part_rel = part_stub.get("manifest_path")
                part_manifest_path = package_path.parent / part_rel if isinstance(part_rel, str) else None
                if part_manifest_path is None:
                    package_entry["parts"].append(
                        {
                            "part_id": part_stub.get("part_id"),
                            "title": part_stub.get("title"),
                            "status": STATUS_UNAVAILABLE,
                            "reason": "missing part manifest path",
                        }
                    )
                    continue

                repo_manifest, repo_err = _load_json(part_manifest_path)
                if repo_manifest is None:
                    package_entry["parts"].append(
                        {
                            "part_id": part_stub.get("part_id"),
                            "title": part_stub.get("title"),
                            "status": STATUS_UNAVAILABLE,
                            "reason": f"repo part manifest unavailable: {repo_err}",
                        }
                    )
                    continue

                status, reason = _compute_part_status(part_manifest_path, repo_manifest)
                part_entry = {
                    "part_id": repo_manifest.get("part_id"),
                    "title": repo_manifest.get("title"),
                    "status": status,
                    "reason": reason,
                }
                lab_info = _extract_lab_metadata(repo_manifest)
                if lab_info:
                    part_entry["lab"] = lab_info
                package_entry["parts"].append(part_entry)

            section_entry["packages"].append(package_entry)

        module_entry["sections"].append(section_entry)

    return {"module": module_entry, "status": STATUS_READY, "reason": ""}


def get_part_status(part_id: str) -> Tuple[str, str]:
    part_info, err = _find_part_in_repo(part_id)
    if part_info is None:
        return STATUS_UNAVAILABLE, err

    repo_manifest_path = part_info["part_manifest_path"]
    repo_manifest, repo_err = _load_json(repo_manifest_path)
    if repo_manifest is None:
        return STATUS_UNAVAILABLE, f"repo part manifest unavailable: {repo_err}"

    return _compute_part_status(repo_manifest_path, repo_manifest)


def get_part(part_id: str) -> Dict[str, Any]:
    part_info, err = _find_part_in_repo(part_id)
    if part_info is None:
        return {"status": STATUS_UNAVAILABLE, "reason": err}

    repo_manifest_path = part_info["part_manifest_path"]
    repo_manifest, repo_err = _load_json(repo_manifest_path)
    if repo_manifest is None:
        return {"status": STATUS_UNAVAILABLE, "reason": f"repo part manifest unavailable: {repo_err}"}

    status, reason = _compute_part_status(repo_manifest_path, repo_manifest)

    assets = _collect_asset_paths(repo_manifest)
    rel_manifest = _safe_relative(repo_manifest_path, REPO_BASE)
    store_manifest_path = STORE_BASE / rel_manifest if rel_manifest else None

    asset_paths: Dict[str, Dict[str, str]] = {}
    for asset in assets:
        asset_paths[asset] = {
            "repo": str(REPO_BASE / asset),
            "store": str(STORE_BASE / asset),
        }

    lab_info = _extract_lab_metadata(repo_manifest)

    result = {
        "status": status,
        "reason": reason,
        "manifest": repo_manifest,
        "paths": {
            "repo_manifest": str(repo_manifest_path),
            "store_manifest": str(store_manifest_path) if store_manifest_path else None,
            "assets": asset_paths,
        },
    }
    if lab_info:
        result["lab"] = lab_info
    return result


def download_part(part_id: str) -> Dict[str, Any]:
    part_info, err = _find_part_in_repo(part_id)
    if part_info is None:
        return {"status": STATUS_UNAVAILABLE, "reason": err}

    repo_manifest_path = part_info["part_manifest_path"]
    repo_manifest, repo_err = _load_json(repo_manifest_path)
    if repo_manifest is None:
        return {"status": STATUS_UNAVAILABLE, "reason": f"repo part manifest unavailable: {repo_err}"}

    rel_manifest = _safe_relative(repo_manifest_path, REPO_BASE)
    if rel_manifest is None:
        return {"status": STATUS_UNAVAILABLE, "reason": "part manifest is outside the repo root"}

    STORE_BASE.mkdir(parents=True, exist_ok=True)

    repo_part_dir = repo_manifest_path.parent
    store_part_dir = STORE_BASE / rel_manifest.parent
    try:
        shutil.copytree(repo_part_dir, store_part_dir, dirs_exist_ok=True)
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": STATUS_UNAVAILABLE, "reason": f"failed to copy part directory: {exc}"}

    assets = _collect_asset_paths(repo_manifest)
    missing_assets: List[str] = []
    for asset in assets:
        src = REPO_BASE / asset
        dst = STORE_BASE / asset
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)
        else:
            missing_assets.append(asset)

    status, reason = _compute_part_status(repo_manifest_path, repo_manifest)
    if missing_assets and status == STATUS_READY:
        reason = f"missing assets during copy: {', '.join(missing_assets)}"
        status = STATUS_NOT_INSTALLED

    return {
        "status": status,
        "reason": reason,
        "copied_assets": assets,
        "missing_assets": missing_assets,
    }
