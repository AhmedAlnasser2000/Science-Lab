from __future__ import annotations

import importlib
import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app_ui.versioning import get_build_info

REPORT_VERSION = 1

PILLAR_TITLES: List[Tuple[int, str]] = [
    (1, "Versioning & build identity"),
    (2, "Schema versions + migrations"),
    (3, "CI baseline (Windows-first)"),
    (4, "Release & packaging pipeline"),
    (5, "Crash capture + Safe Viewer"),
    (6, "Logging & structured events"),
    (7, "Telemetry / metrics (opt-in)"),
    (8, "Activity spans + runtime tracing contract"),
    (9, "Config layering & reproducibility"),
    (10, "Runtime data hygiene (data layout + .gitignore)"),
    (11, "Plugin/pack dependency metadata"),
    (12, "Security & capability boundaries"),
]


@dataclass
class PillarEntry:
    id: int
    title: str
    status: str
    reason: str
    evidence: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = (self.status or "").upper()
        data["pillar_id"] = self.id
        data["name"] = self.title
        return data


def _check_build_identity() -> PillarEntry:
    try:
        build = get_build_info()
    except Exception as exc:
        return PillarEntry(
            id=1,
            title=PILLAR_TITLES[0][1],
            status="FAIL",
            reason=f"Build identity failed: {exc}",
            evidence=["app_ui.versioning.get_build_info"],
        )
    app_version = (build or {}).get("app_version") or ""
    build_id = (build or {}).get("build_id") or ""
    if not app_version:
        return PillarEntry(
            id=1,
            title=PILLAR_TITLES[0][1],
            status="FAIL",
            reason="Build identity missing app_version",
            evidence=["app_ui.versioning.get_build_info"],
        )
    return PillarEntry(
        id=1,
        title=PILLAR_TITLES[0][1],
        status="PASS",
        reason="Build identity available",
        evidence=[
            "app_ui.versioning.get_build_info",
            f"app_version={app_version}",
            f"build_id={build_id or 'unknown'}",
        ],
        details=build,
    )


def _check_ci_baseline() -> PillarEntry:
    path = Path(".github/workflows/ci.yml")
    if not path.exists():
        return PillarEntry(
            id=3,
            title=PILLAR_TITLES[2][1],
            status="FAIL",
            reason="CI workflow missing",
            evidence=[str(path)],
        )
    content = path.read_text(encoding="utf-8", errors="ignore")
    required = {
        "actions/setup-python@v5": "setup-python",
        'python-version: "3.12"': "python-version",
        "pytest -q tests/pillars": "pillars pytest",
    }
    missing = []
    for token, label in required.items():
        if token not in content:
            missing.append(label)
    if "compileall" not in content:
        missing.append("compile step")
    if missing:
        return PillarEntry(
            id=3,
            title=PILLAR_TITLES[2][1],
            status="FAIL",
            reason="CI workflow missing required steps",
            evidence=missing,
        )
    return PillarEntry(
        id=3,
        title=PILLAR_TITLES[2][1],
        status="PASS",
        reason="CI workflow enforces compile + pillars tests",
    )


def _check_config_layering() -> PillarEntry:
    try:
        import app_ui.config as config  # local import to keep scope small
    except Exception as exc:
        return PillarEntry(
            id=9,
            title=PILLAR_TITLES[8][1],
            status="FAIL",
            reason=f"Config module import failed: {exc}",
        )
    defaults = getattr(config, "_DEFAULT_UI_CONFIG", {})
    config_path = getattr(config, "CONFIG_PATH", Path("data/roaming/ui_config.json"))
    files_read: List[str] = []
    sources = ["defaults"]
    effective: Dict[str, Any] = {}
    if isinstance(defaults, dict):
        effective.update(defaults)
    else:
        defaults = {}
    if Path(config_path).exists():
        try:
            data = json.loads(Path(config_path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                effective.update(data)
                files_read.append(str(config_path))
                sources.append("roaming")
        except Exception:
            pass
    if not defaults or not effective:
        return PillarEntry(
            id=9,
            title=PILLAR_TITLES[8][1],
            status="FAIL",
            reason="Effective config snapshot is empty",
            evidence=[f"config_path={config_path}"],
        )
    return PillarEntry(
        id=9,
        title=PILLAR_TITLES[8][1],
        status="PASS",
        reason="Config snapshot available",
        evidence=[f"config_path={config_path}", f"sources={sources}"],
        details={
            "sources": sources,
            "files_read": files_read,
            "env_keys": [],
        },
    )


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except Exception:
        return str(path.resolve()).startswith(str(root.resolve()))


def _check_crash_capture(
    *, base_dir: Path | None = None, viewer_symbol: str = "app_ui.screens.system_health.CrashViewerPanel"
) -> PillarEntry:
    try:
        from diagnostics.crash_capture import get_crash_dir
    except Exception as exc:
        return PillarEntry(
            id=5,
            title=PILLAR_TITLES[4][1],
            status="FAIL",
            reason=f"Crash capture module import failed: {exc}",
        )
    crash_dir = get_crash_dir(base_dir)
    root = base_dir or Path("data/roaming")
    if not _is_under_root(crash_dir, root):
        return PillarEntry(
            id=5,
            title=PILLAR_TITLES[4][1],
            status="FAIL",
            reason="Crash dir outside allowed data roots",
            evidence=[str(crash_dir)],
        )
    try:
        module_name, attr = viewer_symbol.rsplit(".", 1)
        module = importlib.import_module(module_name)
        viewer = getattr(module, attr, None)
    except Exception as exc:
        return PillarEntry(
            id=5,
            title=PILLAR_TITLES[4][1],
            status="FAIL",
            reason=f"Crash viewer import failed: {exc}",
            evidence=[viewer_symbol],
        )
    if viewer is None:
        return PillarEntry(
            id=5,
            title=PILLAR_TITLES[4][1],
            status="FAIL",
            reason="Crash viewer symbol missing",
            evidence=[viewer_symbol],
        )
    return PillarEntry(
        id=5,
        title=PILLAR_TITLES[4][1],
        status="PASS",
        reason="Crash capture directory and viewer present",
        evidence=[str(crash_dir), viewer_symbol],
    )


def _check_logging_baseline(*, base_dir: Path | None = None) -> PillarEntry:
    try:
        from diagnostics.logging_setup import configure_logging
    except Exception as exc:
        return PillarEntry(
            id=6,
            title=PILLAR_TITLES[5][1],
            status="FAIL",
            reason=f"Logging setup module import failed: {exc}",
        )
    info = configure_logging(base_dir)
    log_path_value = info.get("log_path") if isinstance(info, dict) else None
    if not log_path_value:
        return PillarEntry(
            id=6,
            title=PILLAR_TITLES[5][1],
            status="FAIL",
            reason="Logging setup did not return log_path",
        )
    log_path = Path(log_path_value)
    root = base_dir or Path("data/roaming")
    if not _is_under_root(log_path, root):
        return PillarEntry(
            id=6,
            title=PILLAR_TITLES[5][1],
            status="FAIL",
            reason="Log path outside allowed data roots",
            evidence=[str(log_path)],
        )
    logger_name = info.get("logger_name", "physicslab")
    logger = logging.getLogger(logger_name)
    logger.info("pillars logging baseline check")
    if not log_path.exists() or log_path.stat().st_size == 0:
        return PillarEntry(
            id=6,
            title=PILLAR_TITLES[5][1],
            status="FAIL",
            reason="Log file not written",
            evidence=[str(log_path)],
        )
    return PillarEntry(
        id=6,
        title=PILLAR_TITLES[5][1],
        status="PASS",
        reason="Logging baseline configured and writable",
        evidence=[str(log_path), info.get("format", "kv")],
        details={"handlers": info.get("handlers", "")},
    )


def _check_telemetry_opt_in() -> PillarEntry:
    try:
        from diagnostics import telemetry
    except Exception as exc:
        return PillarEntry(
            id=7,
            title=PILLAR_TITLES[6][1],
            status="FAIL",
            reason=f"Telemetry module import failed: {exc}",
        )
    base_dir = Path("data/roaming/telemetry_probe")
    base_dir.mkdir(parents=True, exist_ok=True)
    policy_path = base_dir / "policy.json"
    policy_path.write_text(json.dumps({"telemetry_enabled": False}, indent=2))
    telemetry.clear_metrics()
    if telemetry.is_telemetry_enabled(base_dir):
        return PillarEntry(
            id=7,
            title=PILLAR_TITLES[6][1],
            status="FAIL",
            reason="Telemetry enabled by default",
            evidence=[str(policy_path)],
        )
    telemetry.emit_metric("pillars.disabled", base_dir=base_dir)
    if telemetry.get_recent_metrics():
        return PillarEntry(
            id=7,
            title=PILLAR_TITLES[6][1],
            status="FAIL",
            reason="Metrics recorded while telemetry disabled",
            evidence=[str(policy_path)],
        )
    policy_path.write_text(json.dumps({"telemetry_enabled": True}, indent=2))
    if not telemetry.is_telemetry_enabled(base_dir):
        return PillarEntry(
            id=7,
            title=PILLAR_TITLES[6][1],
            status="FAIL",
            reason="Telemetry did not enable with opt-in",
            evidence=[str(policy_path)],
        )
    telemetry.clear_metrics()
    telemetry.emit_metric("pillars.enabled", base_dir=base_dir)
    if not telemetry.get_recent_metrics():
        return PillarEntry(
            id=7,
            title=PILLAR_TITLES[6][1],
            status="FAIL",
            reason="Metrics not recorded when telemetry enabled",
            evidence=[str(policy_path)],
        )
    return PillarEntry(
        id=7,
        title=PILLAR_TITLES[6][1],
        status="PASS",
        reason="Telemetry is opt-in and gated",
        evidence=[str(policy_path), "pillars.enabled"],
    )


def _check_tracing_contract() -> PillarEntry:
    try:
        from diagnostics import tracing
    except Exception as exc:
        return PillarEntry(
            id=8,
            title=PILLAR_TITLES[7][1],
            status="FAIL",
            reason=f"Tracing module import failed: {exc}",
        )
    tracing.clear_spans()
    with tracing.span("pillars.contract"):
        pass
    spans = tracing.get_recent_spans()
    names = [s.get("name") for s in spans if isinstance(s, dict)]
    if not names or "pillars.contract" not in names:
        return PillarEntry(
            id=8,
            title=PILLAR_TITLES[7][1],
            status="FAIL",
            reason="No spans recorded by tracing contract",
        )
    return PillarEntry(
        id=8,
        title=PILLAR_TITLES[7][1],
        status="PASS",
        reason="Tracing contract recorded spans",
        evidence=names[:5],
    )


def _load_pack_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_pack_manifest(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    pack_id = manifest.get("pack_id")
    pack_type = manifest.get("pack_type")
    version = manifest.get("version")
    if not isinstance(pack_id, str) or not pack_id.strip():
        errors.append("pack_id")
    if not isinstance(pack_type, str) or not pack_type.strip():
        errors.append("pack_type")
    if not isinstance(version, str) or not version.strip():
        errors.append("version")
    deps = manifest.get("dependencies") or manifest.get("requires") or []
    if deps and not isinstance(deps, list):
        errors.append("dependencies")
    capabilities = manifest.get("capabilities") or []
    if capabilities and not isinstance(capabilities, list):
        errors.append("capabilities")
    return errors


def _collect_pack_manifests(roots: List[Path]) -> List[Path]:
    manifests: List[Path] = []
    for root in roots:
        if root.exists():
            manifests.extend(root.rglob("pack_manifest.json"))
    return manifests


def _detect_dependency_cycle(graph: Dict[str, List[str]]) -> List[str]:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, stack: List[str]) -> List[str]:
        if node in visiting:
            return stack + [node]
        if node in visited:
            return []
        visiting.add(node)
        for dep in graph.get(node, []):
            cycle = visit(dep, stack + [node])
            if cycle:
                return cycle
        visiting.remove(node)
        visited.add(node)
        return []

    for node in graph:
        cycle = visit(node, [])
        if cycle:
            return cycle
    return []


def _check_pack_metadata(roots: List[Path] | None = None) -> PillarEntry:
    from diagnostics.security_guard import validate_capabilities

    if roots is None:
        roots = [Path("component_store"), Path("content_store"), Path("ui_store")]
    existing_roots = [root for root in roots if root.exists()]
    if not existing_roots:
        return PillarEntry(
            id=11,
            title=PILLAR_TITLES[10][1],
            status="PASS",
            reason="No pack stores found",
        )
    manifests = _collect_pack_manifests(existing_roots)
    if not manifests:
        has_entries = any(any(root.iterdir()) for root in existing_roots)
        if has_entries:
            return PillarEntry(
                id=11,
                title=PILLAR_TITLES[10][1],
                status="FAIL",
                reason="Pack store contains entries but no pack_manifest.json found",
                evidence=[str(root) for root in existing_roots],
            )
        return PillarEntry(
            id=11,
            title=PILLAR_TITLES[10][1],
            status="PASS",
            reason="Pack stores are empty",
        )
    errors: List[str] = []
    manifests_by_id: Dict[str, Dict[str, Any]] = {}
    dependencies: Dict[str, List[str]] = {}
    for path in manifests:
        try:
            data = _load_pack_manifest(path)
        except Exception as exc:
            errors.append(f"{path}: invalid json ({exc})")
            continue
        issues = _validate_pack_manifest(data)
        if issues:
            errors.append(f"{path}: missing {','.join(issues)}")
            continue
        pack_id = data["pack_id"]
        manifests_by_id[pack_id] = data
        deps = data.get("dependencies") or data.get("requires") or []
        dep_ids = []
        for dep in deps:
            if isinstance(dep, dict) and isinstance(dep.get("id"), str):
                dep_ids.append(dep["id"])
            elif isinstance(dep, str):
                dep_ids.append(dep)
        dependencies[pack_id] = dep_ids
        caps = data.get("capabilities") or []
        if isinstance(caps, list):
            unknown = validate_capabilities(caps)
            if unknown:
                errors.append(f"{pack_id}: unknown capabilities {unknown}")
        if pack_id in dep_ids:
            errors.append(f"{pack_id}: self-dependency")
    missing_deps = []
    for pack_id, deps in dependencies.items():
        for dep in deps:
            if dep not in manifests_by_id:
                missing_deps.append(f"{pack_id} -> {dep}")
    if missing_deps:
        errors.append(f"missing deps: {missing_deps[:5]}")
    cycle = _detect_dependency_cycle(dependencies)
    if cycle:
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")
    if errors:
        return PillarEntry(
            id=11,
            title=PILLAR_TITLES[10][1],
            status="FAIL",
            reason="Pack manifest validation failed",
            evidence=errors[:8],
        )
    return PillarEntry(
        id=11,
        title=PILLAR_TITLES[10][1],
        status="PASS",
        reason="All pack manifests valid",
        evidence=list(manifests_by_id.keys())[:8],
    )


def _check_security_boundaries() -> PillarEntry:
    from diagnostics.security_guard import KNOWN_CAPABILITIES, resolve_under_root, validate_capabilities

    root = Path("data/roaming/security_probe")
    root.mkdir(parents=True, exist_ok=True)
    try:
        ok_path = resolve_under_root(root, "safe/asset.json")
    except Exception as exc:
        return PillarEntry(
            id=12,
            title=PILLAR_TITLES[11][1],
            status="FAIL",
            reason=f"Path guard rejected safe path: {exc}",
        )
    rejected = []
    for vector in ["../secret", "..\\secret", "C:\\Windows\\system32", "\\\\server\\share\\x"]:
        try:
            resolve_under_root(root, vector)
        except Exception:
            rejected.append(vector)
    if len(rejected) < 4:
        return PillarEntry(
            id=12,
            title=PILLAR_TITLES[11][1],
            status="FAIL",
            reason="Path guard did not reject all traversal vectors",
            evidence=[v for v in ["../secret", "..\\secret", "C:\\Windows\\system32", "\\\\server\\share\\x"] if v not in rejected],
        )
    if not KNOWN_CAPABILITIES:
        return PillarEntry(
            id=12,
            title=PILLAR_TITLES[11][1],
            status="FAIL",
            reason="Capability allowlist missing",
        )
    if not validate_capabilities(["unknown.capability"]):
        return PillarEntry(
            id=12,
            title=PILLAR_TITLES[11][1],
            status="FAIL",
            reason="Unknown capabilities not rejected",
        )
    return PillarEntry(
        id=12,
        title=PILLAR_TITLES[11][1],
        status="PASS",
        reason="Security guard and capability allowlist present",
        evidence=[str(ok_path), f"capabilities={len(KNOWN_CAPABILITIES)}"],
    )


def _check_schema_manifest(base_dir: Path | None = None) -> PillarEntry:
    root = base_dir or Path(".")
    manifest_path = root / "schemas" / "schema_manifest.json"
    migrations_path = root / "docs" / "migrations" / "README.md"
    if not manifest_path.exists():
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="schema_manifest.json missing",
            evidence=[str(manifest_path)],
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason=f"schema_manifest.json invalid: {exc}",
        )
    if not isinstance(manifest, dict):
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="schema_manifest.json root is not an object",
        )
    if not isinstance(manifest.get("manifest_version"), int):
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="manifest_version missing or not int",
        )
    entries = manifest.get("schemas")
    if not isinstance(entries, list) or not entries:
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="schemas list missing or empty",
        )
    missing = []
    for entry in entries:
        if not isinstance(entry, dict):
            missing.append("entry-not-object")
            continue
        path = entry.get("path")
        schema_id = entry.get("schema_id")
        schema_version = entry.get("schema_version")
        if not path or not schema_id or not isinstance(schema_version, int):
            missing.append(str(path or "missing-path"))
            continue
        if not (root / "schemas" / path).exists():
            missing.append(str(path))
    if missing:
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="Schema manifest entries invalid or missing files",
            evidence=missing,
        )
    if not migrations_path.exists():
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="Migrations README missing",
            evidence=[str(migrations_path)],
        )
    return PillarEntry(
        id=2,
        title=PILLAR_TITLES[1][1],
        status="PASS",
        reason="Schema manifest and migrations note present",
        evidence=[str(manifest_path), str(migrations_path)],
    )


def _check_runtime_data_hygiene() -> PillarEntry:
    git_path = Path(".gitignore")
    if not git_path.exists():
        return PillarEntry(
            id=10,
            title=PILLAR_TITLES[9][1],
            status="FAIL",
            reason=".gitignore missing",
        )
    ignore_text = git_path.read_text(encoding="utf-8", errors="ignore")
    if "data/" not in ignore_text and "/data/" not in ignore_text:
        if "/data/roaming/" not in ignore_text and "/data/workspaces/" not in ignore_text:
            return PillarEntry(
                id=10,
                title=PILLAR_TITLES[9][1],
                status="FAIL",
                reason="data/ ignores not found in .gitignore",
            )
    if not _git_available():
        return PillarEntry(
            id=10,
            title=PILLAR_TITLES[9][1],
            status="SKIP",
            reason="git not available",
        )
    probe_dir = Path("data/roaming/pillars_reports")
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_path = probe_dir / "_gitignore_probe.tmp"
    try:
        probe_path.write_text("probe")
        output = _run_git_status()
        if output is None:
            return PillarEntry(
                id=10,
                title=PILLAR_TITLES[9][1],
                status="SKIP",
                reason="git status failed",
            )
        if str(probe_path.as_posix()) in output or str(probe_path) in output:
            return PillarEntry(
                id=10,
                title=PILLAR_TITLES[9][1],
                status="FAIL",
                reason="data/ probe file appears in git status",
                evidence=[str(probe_path)],
            )
        return PillarEntry(
            id=10,
            title=PILLAR_TITLES[9][1],
            status="PASS",
            reason="data/ outputs ignored by git",
        )
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except Exception:
            pass


def _git_available() -> bool:
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return False
    return result.returncode == 0


def _run_git_status() -> str | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout or ""


def run_pillar_checks() -> List[PillarEntry]:
    results: Dict[int, PillarEntry] = {}

    results[1] = _check_build_identity()
    results[2] = _check_schema_manifest()
    results[3] = _check_ci_baseline()
    results[4] = PillarEntry(
        id=4,
        title=PILLAR_TITLES[3][1],
        status="SKIP",
        reason="Release pipeline checks not implemented yet",
    )
    results[5] = _check_crash_capture()
    results[6] = _check_logging_baseline()
    results[7] = _check_telemetry_opt_in()
    results[8] = _check_tracing_contract()
    results[9] = _check_config_layering()
    results[10] = _check_runtime_data_hygiene()
    results[11] = _check_pack_metadata()
    results[12] = _check_security_boundaries()

    return [results[i] for i, _ in PILLAR_TITLES]


def build_report(results: Iterable[PillarEntry]) -> Dict[str, Any]:
    build = get_build_info()
    return {
        "report_version": REPORT_VERSION,
        "generated_at": time.time(),
        "app_version": build.get("app_version", "unknown"),
        "build_id": build.get("build_id", "unknown"),
        "results": [r.to_dict() for r in results],
    }


def write_report(report: Dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "pillars_report.json"
    target.write_text(json.dumps(report, indent=2))
    return target


def load_report(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def find_latest_report(report_dir: Path) -> Path | None:
    candidates: List[Path] = []
    latest = Path("data/roaming/pillars_report_latest.json")
    if latest.exists():
        candidates.append(latest)
    if report_dir.exists():
        candidates.extend(
            sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        )
    return candidates[0] if candidates else None
