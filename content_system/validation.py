from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schemas"

MANIFEST_SCHEMAS = {
    "module": "module_manifest.schema.json",
    "section": "section_manifest.schema.json",
    "package": "package_manifest.schema.json",
    "part": "part_manifest.schema.json",
}


@dataclass
class ValidationIssue:
    path: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    manifest_type: str
    schema_id: Optional[str]
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    error_summary: Optional[str]
    mtime_ns: Optional[int]
    size: Optional[int]


_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}
_RESULT_CACHE: Dict[str, ValidationResult] = {}


def clear_validation_cache() -> None:
    _RESULT_CACHE.clear()


def _load_schema_file(name: str) -> Dict[str, Any]:
    cached = _SCHEMA_CACHE.get(name)
    if cached is not None:
        return cached
    path = SCHEMA_ROOT / name
    data = json.loads(path.read_text(encoding="utf-8"))
    _SCHEMA_CACHE[name] = data
    return data


def _resolve_pointer(schema: Dict[str, Any], pointer: str) -> Any:
    if not pointer or pointer == "/":
        return schema
    current: Any = schema
    for raw in pointer.strip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        else:
            return {}
    return current


def _resolve_ref(ref: str, current_file: str) -> Tuple[Dict[str, Any], str]:
    if ref.startswith("#"):
        return _resolve_pointer(_load_schema_file(current_file), ref[1:]), current_file
    if "#" in ref:
        file_part, pointer = ref.split("#", 1)
    else:
        file_part, pointer = ref, ""
    file_name = file_part or current_file
    schema = _load_schema_file(file_name)
    return _resolve_pointer(schema, pointer), file_name


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate(
    value: Any,
    schema: Dict[str, Any],
    *,
    current_file: str,
    json_path: str,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if "$ref" in schema:
        ref_schema, ref_file = _resolve_ref(str(schema["$ref"]), current_file)
        return _validate(value, ref_schema, current_file=ref_file, json_path=json_path)

    if "allOf" in schema:
        for sub in schema.get("allOf", []):
            if isinstance(sub, dict):
                issues.extend(
                    _validate(value, sub, current_file=current_file, json_path=json_path)
                )

    if "if" in schema and "then" in schema:
        if_schema = schema.get("if") or {}
        then_schema = schema.get("then") or {}
        if isinstance(if_schema, dict) and isinstance(then_schema, dict):
            match = not _validate(value, if_schema, current_file=current_file, json_path=json_path)
            if match:
                issues.extend(
                    _validate(value, then_schema, current_file=current_file, json_path=json_path)
                )

    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not _schema_type_matches(value, expected_type):
            issues.append(
                ValidationIssue(json_path, f"expected {expected_type}")
            )
            return issues

    if "const" in schema:
        if value != schema["const"]:
            issues.append(ValidationIssue(json_path, f"expected const {schema['const']}"))
            return issues

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        issues.append(ValidationIssue(json_path, "value not in enum"))

    if isinstance(value, str):
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and len(value) < min_len:
            issues.append(ValidationIssue(json_path, f"minLength {min_len}"))
        max_len = schema.get("maxLength")
        if isinstance(max_len, int) and len(value) > max_len:
            issues.append(ValidationIssue(json_path, f"maxLength {max_len}"))
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            if re.match(pattern, value) is None:
                issues.append(ValidationIssue(json_path, "pattern mismatch"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            issues.append(ValidationIssue(json_path, f"minimum {minimum}"))
        exclusive = schema.get("exclusiveMinimum")
        if isinstance(exclusive, (int, float)) and value <= exclusive:
            issues.append(ValidationIssue(json_path, f"exclusiveMinimum {exclusive}"))

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(ValidationIssue(json_path, f"minItems {min_items}"))
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            issues.append(ValidationIssue(json_path, f"maxItems {max_items}"))
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for idx, item in enumerate(value):
                issues.extend(
                    _validate(
                        item,
                        items_schema,
                        current_file=current_file,
                        json_path=f"{json_path}[{idx}]",
                    )
                )

    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                issues.append(ValidationIssue(json_path, f"missing required '{key}'"))
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, val in value.items():
                prop_schema = properties.get(key)
                if isinstance(prop_schema, dict):
                    issues.extend(
                        _validate(
                            val,
                            prop_schema,
                            current_file=current_file,
                            json_path=f"{json_path}.{key}",
                        )
                    )
        additional = schema.get("additionalProperties")
        if additional is False and isinstance(properties, dict):
            allowed = set(properties.keys())
            for key in value.keys():
                if key not in allowed:
                    issues.append(ValidationIssue(json_path, f"unexpected property '{key}'"))
        if isinstance(additional, dict):
            for key, val in value.items():
                if key in properties:
                    continue
                issues.extend(
                    _validate(
                        val,
                        additional,
                        current_file=current_file,
                        json_path=f"{json_path}.{key}",
                    )
                )

    return issues


def _file_stats(path: Path) -> Tuple[Optional[int], Optional[int]]:
    try:
        stat = path.stat()
    except OSError:
        return None, None
    return stat.st_mtime_ns, stat.st_size


def record_manifest_error(path: Path, manifest_type: str, error_summary: str) -> None:
    mtime_ns, size = _file_stats(path)
    result = ValidationResult(
        ok=False,
        manifest_type=manifest_type,
        schema_id=None,
        errors=[ValidationIssue("$", error_summary)],
        warnings=[],
        error_summary=error_summary,
        mtime_ns=mtime_ns,
        size=size,
    )
    _RESULT_CACHE[str(path)] = result


def validate_manifest(
    path: Path, manifest_type: str, data: Dict[str, Any]
) -> ValidationResult:
    cache_key = str(path)
    mtime_ns, size = _file_stats(path)
    cached = _RESULT_CACHE.get(cache_key)
    if cached and cached.mtime_ns == mtime_ns and cached.size == size:
        return cached

    schema_name = MANIFEST_SCHEMAS.get(manifest_type)
    warnings: List[ValidationIssue] = []
    if not schema_name or not (SCHEMA_ROOT / schema_name).exists():
        result = ValidationResult(
            ok=True,
            manifest_type=manifest_type,
            schema_id=None,
            errors=[],
            warnings=[ValidationIssue("$", "schema not found")],
            error_summary=None,
            mtime_ns=mtime_ns,
            size=size,
        )
        _RESULT_CACHE[cache_key] = result
        return result

    try:
        schema = _load_schema_file(schema_name)
        schema_id = schema.get("$id") if isinstance(schema, dict) else None
        issues = _validate(data, schema, current_file=schema_name, json_path="$")
        error_summary = issues[0].message if issues else None
        result = ValidationResult(
            ok=not issues,
            manifest_type=manifest_type,
            schema_id=schema_id,
            errors=issues,
            warnings=warnings,
            error_summary=error_summary,
            mtime_ns=mtime_ns,
            size=size,
        )
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(ValidationIssue("$", f"validator error: {exc}"))
        result = ValidationResult(
            ok=True,
            manifest_type=manifest_type,
            schema_id=None,
            errors=[],
            warnings=warnings,
            error_summary=None,
            mtime_ns=mtime_ns,
            size=size,
        )
    _RESULT_CACHE[cache_key] = result
    return result


def get_validation_report(limit: int = 50) -> Dict[str, Any]:
    ok_count = 0
    warn_count = 0
    fail_count = 0
    failures: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for path, result in _RESULT_CACHE.items():
        if result.ok:
            ok_count += 1
        else:
            fail_count += 1
        if result.warnings:
            warn_count += len(result.warnings)
            for issue in result.warnings:
                warnings.append(
                    {
                        "path": path,
                        "manifest_type": result.manifest_type,
                        "error_summary": issue.message,
                        "schema_id": result.schema_id,
                        "json_path": issue.path,
                    }
                )
        if not result.ok:
            for issue in result.errors:
                failures.append(
                    {
                        "path": path,
                        "manifest_type": result.manifest_type,
                        "error_summary": issue.message,
                        "schema_id": result.schema_id,
                        "json_path": issue.path,
                    }
                )

    failures = failures[:limit]
    warnings = warnings[:limit]
    return {
        "ok_count": ok_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "failures": failures,
        "warnings": warnings,
    }
