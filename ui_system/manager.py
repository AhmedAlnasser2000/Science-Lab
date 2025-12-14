import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


CONFIG_PATH = Path("data/roaming/ui_config.json")
DEFAULT_PACK_ID = "default"


@dataclass
class Pack:
    id: str
    name: str
    version: str
    description: str
    author: str
    license: str
    targets: List[str]
    min_app_version: str
    qss_files: List[str]
    assets: List[str]
    supports_reduced_motion: bool
    base_path: Path
    source: str  # repo or store


def _load_manifest(manifest_path: Path) -> Optional[Pack]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    required = ["id", "name", "version", "description", "author", "license", "targets", "min_app_version", "qss_files", "assets", "supports_reduced_motion"]
    if not all(k in data for k in required):
        return None
    return Pack(
        id=str(data.get("id")),
        name=str(data.get("name")),
        version=str(data.get("version")),
        description=str(data.get("description")),
        author=str(data.get("author")),
        license=str(data.get("license")),
        targets=list(data.get("targets") or []),
        min_app_version=str(data.get("min_app_version")),
        qss_files=list(data.get("qss_files") or []),
        assets=list(data.get("assets") or []),
        supports_reduced_motion=bool(data.get("supports_reduced_motion")),
        base_path=manifest_path.parent,
        source="store" if "store" in str(manifest_path.parts) else "repo",
    )


def list_packs(repo_root: Path, store_root: Path) -> List[Pack]:
    packs: List[Pack] = []
    for root in [store_root, repo_root]:
        if not root.exists():
            continue
        for manifest in root.rglob("ui_pack_manifest.json"):
            pack = _load_manifest(manifest)
            if pack:
                packs.append(pack)
    return packs


def get_active_pack(config_path: Path = CONFIG_PATH) -> str:
    cfg = _load_config(config_path)
    return cfg.get("active_pack_id", DEFAULT_PACK_ID)


def set_active_pack(config_path: Path, pack_id: str) -> None:
    cfg = _load_config(config_path)
    cfg["active_pack_id"] = pack_id
    _save_config(config_path, cfg)


def load_qss(pack: Pack) -> str:
    contents: List[str] = []
    for rel in pack.qss_files:
        path = pack.base_path / rel
        try:
            contents.append(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return "\n".join(contents)


def apply_qss(app, qss_text: str) -> None:
    try:
        app.setStyleSheet(qss_text)
    except Exception:
        # swallow errors to avoid crashing UI
        return


def resolve_pack(pack_id: str, repo_root: Path, store_root: Path, prefer_store: bool = True) -> Optional[Pack]:
    packs = list_packs(repo_root, store_root)
    if prefer_store:
        for pack in packs:
            if pack.id == pack_id and pack.source == "store":
                return pack
    for pack in packs:
        if pack.id == pack_id:
            return pack
    return None


def ensure_config(config_path: Path = CONFIG_PATH) -> None:
    if config_path.exists():
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _save_config(
        config_path,
        {
            "active_pack_id": DEFAULT_PACK_ID,
            "reduced_motion": False,
        },
    )


def _load_config(config_path: Path) -> dict:
    ensure_config(config_path)
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {"active_pack_id": DEFAULT_PACK_ID, "reduced_motion": False}


def _save_config(config_path: Path, cfg: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
