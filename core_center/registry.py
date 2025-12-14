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


def _record_key(rec: RegistryRecord) -> Tuple[str, str, str]:
    return (
        str(rec.get("id", "")),
        str(rec.get("type", "")),
        str(rec.get("source", "")),
    )


def upsert_records(existing: List[RegistryRecord], new: List[RegistryRecord]) -> List[RegistryRecord]:
    merged: Dict[Tuple[str, str, str], RegistryRecord] = {}
    for rec in existing:
        merged[_record_key(rec)] = rec
    for rec in new:
        merged[_record_key(rec)] = rec
    return list(merged.values())
