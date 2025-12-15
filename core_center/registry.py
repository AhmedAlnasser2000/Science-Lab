import json
from pathlib import Path
from typing import Dict, List, Tuple

RegistryRecord = Dict[str, object]


def load_registry(path: Path) -> List[RegistryRecord]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def save_registry(path: Path, records: List[RegistryRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _normalize_source(source: str) -> str:
    mapping = {
        "content_repo": "repo",
        "ui_repo": "repo",
        "content_store": "store",
        "ui_store": "store",
    }
    return mapping.get(source, source or "")


def _normalize_record(rec: RegistryRecord) -> RegistryRecord:
    source = _normalize_source(str(rec.get("source", "")))
    rec["source"] = source
    return rec


def _record_key(rec: RegistryRecord) -> Tuple[str, str, str]:
    return (
        str(rec.get("id", "")),
        str(rec.get("type", "")),
        _normalize_source(str(rec.get("source", ""))),
    )


def upsert_records(existing: List[RegistryRecord], new: List[RegistryRecord]) -> List[RegistryRecord]:
    merged: Dict[Tuple[str, str, str], RegistryRecord] = {}
    for rec in existing:
        normalized = _normalize_record(rec)
        merged[_record_key(normalized)] = normalized
    for rec in new:
        normalized = _normalize_record(rec)
        merged[_record_key(normalized)] = normalized
    return list(merged.values())


def summarize_registry(records: List[RegistryRecord]) -> Dict[str, object]:
    summary: Dict[str, object] = {
        "total": len(records),
        "by_type": {},
        "by_source": {},
    }
    for rec in records:
        rec_type = str(rec.get("type", "unknown"))
        summary["by_type"][rec_type] = summary["by_type"].get(rec_type, 0) + 1
        source = str(rec.get("source", "unknown"))
        summary["by_source"][source] = summary["by_source"].get(source, 0) + 1
    return summary
