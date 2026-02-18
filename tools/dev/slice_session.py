from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ACTIVE_FILE = ".active_session"
_SCRATCH_ENV = "PHYSICSLAB_SLICE_TMP_DIR"
_SLICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _scratch_root() -> Path:
    override = os.environ.get(_SCRATCH_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / ".slice_tmp"


def _state_path(session_dir: Path) -> Path:
    return session_dir / "state.json"


def _notes_path(session_dir: Path) -> Path:
    return session_dir / "notes.md"


def _gates_dir(session_dir: Path) -> Path:
    return session_dir / "gates"


def _active_path(root: Path) -> Path:
    return root / _ACTIVE_FILE


def _normalize_slice_id(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("slice_id is required")
    path_value = Path(cleaned)
    if path_value.is_absolute():
        raise ValueError(f"invalid slice_id (absolute path not allowed): {cleaned}")
    if cleaned in {".", ".."}:
        raise ValueError(f"invalid slice_id: {cleaned}")
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"invalid slice_id (path separators not allowed): {cleaned}")
    if ":" in cleaned:
        raise ValueError(f"invalid slice_id (drive/path marker not allowed): {cleaned}")
    if not _SLICE_ID_RE.fullmatch(cleaned):
        raise ValueError(
            "invalid slice_id; allowed pattern is [A-Za-z0-9][A-Za-z0-9._-]*"
        )
    return cleaned


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return text or "gate"


def _read_state(session_dir: Path) -> dict[str, Any]:
    state_file = _state_path(session_dir)
    if not state_file.exists():
        return {"slice_id": session_dir.name, "created_at": _utc_now(), "updated_at": _utc_now(), "gates": []}
    return json.loads(state_file.read_text(encoding="utf-8"))


def _write_state(session_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now()
    _state_path(session_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _require_active_slice(root: Path) -> str:
    active_file = _active_path(root)
    if not active_file.exists():
        raise RuntimeError("No active slice session. Run: start <slice_id>")
    slice_id = active_file.read_text(encoding="utf-8").strip()
    if not slice_id:
        raise RuntimeError("Active session file is empty. Run: start <slice_id>")
    return _normalize_slice_id(slice_id)


def _contains_path(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _session_dir(root: Path, slice_id: str) -> tuple[Path, str]:
    safe_id = _normalize_slice_id(slice_id)
    base = root.resolve()
    target = (base / safe_id).resolve()
    if not _contains_path(base, target):
        raise RuntimeError(f"refusing unsafe path outside scratch root: {target}")
    return target, safe_id


def cmd_start(slice_id: str) -> int:
    root = _scratch_root().resolve()
    session_dir, session_id = _session_dir(root, slice_id)

    _gates_dir(session_dir).mkdir(parents=True, exist_ok=True)

    notes_file = _notes_path(session_dir)
    if not notes_file.exists():
        notes_file.write_text(f"# Slice Session Notes: {session_id}\n\n", encoding="utf-8")

    state = _read_state(session_dir)
    state["slice_id"] = session_id
    state.setdefault("created_at", _utc_now())
    state.setdefault("gates", [])
    _write_state(session_dir, state)

    root.mkdir(parents=True, exist_ok=True)
    _active_path(root).write_text(session_id, encoding="utf-8")

    print(f"Started slice session: {session_id}")
    print(f"Session dir: {session_dir}")
    return 0


def cmd_note(text: str) -> int:
    root = _scratch_root().resolve()
    session_id = _require_active_slice(root)
    session_dir, _ = _session_dir(root, session_id)
    if not session_dir.exists():
        raise RuntimeError(f"Active slice directory does not exist: {session_dir}")
    notes_file = _notes_path(session_dir)
    if not notes_file.exists():
        notes_file.write_text(f"# Slice Session Notes: {session_id}\n\n", encoding="utf-8")
    with notes_file.open("a", encoding="utf-8") as handle:
        handle.write(f"- [{_utc_now()}] {text}\n")
    print(f"Note appended for {session_id}")
    return 0


def cmd_gate(name: str, kind: str) -> int:
    root = _scratch_root().resolve()
    session_id = _require_active_slice(root)
    session_dir, _ = _session_dir(root, session_id)
    state = _read_state(session_dir)
    gates = list(state.get("gates", []))
    gate_slug = _slug(name)

    for gate in gates:
        if gate.get("slug") == gate_slug and gate.get("status") == "open":
            raise RuntimeError(f"Gate '{name}' is already open")

    next_index = max((int(gate.get("index", 0)) for gate in gates), default=0) + 1
    gate_file = _gates_dir(session_dir) / f"{next_index:02d}_{gate_slug}.md"
    opened_at = _utc_now()
    gate_file.write_text(
        "\n".join(
            [
                f"# Gate {next_index}: {name}",
                f"- Kind: {kind}",
                "- Status: open",
                f"- Opened: {opened_at}",
                "- Result: pending",
                "",
                "## Evidence",
                "- TODO",
                "",
            ]
        ),
        encoding="utf-8",
    )

    gate_record = {
        "index": next_index,
        "name": name,
        "slug": gate_slug,
        "kind": kind,
        "status": "open",
        "result": None,
        "opened_at": opened_at,
        "closed_at": None,
        "file": str(gate_file.relative_to(session_dir)).replace("\\", "/"),
    }
    gates.append(gate_record)
    state["gates"] = gates
    _write_state(session_dir, state)
    print(f"Opened gate: {name} ({kind})")
    print(f"Gate file: {gate_file}")
    return 0


def cmd_gate_done(name: str, result: str) -> int:
    root = _scratch_root().resolve()
    session_id = _require_active_slice(root)
    session_dir, _ = _session_dir(root, session_id)
    state = _read_state(session_dir)
    gates = list(state.get("gates", []))
    gate_slug = _slug(name)

    target: dict[str, Any] | None = None
    for gate in reversed(gates):
        if gate.get("slug") == gate_slug and gate.get("status") == "open":
            target = gate
            break
    if target is None:
        raise RuntimeError(f"No open gate found for: {name}")

    closed_at = _utc_now()
    target["status"] = "closed"
    target["result"] = result
    target["closed_at"] = closed_at
    _write_state(session_dir, state)

    gate_file = session_dir / str(target.get("file", ""))
    with gate_file.open("a", encoding="utf-8") as handle:
        handle.write("## Close\n")
        handle.write(f"- Closed: {closed_at}\n")
        handle.write(f"- Result: {result}\n\n")

    print(f"Closed gate: {target.get('name')} ({result})")
    return 0


def _print_finalize_preview(path: Path) -> None:
    print(f"Would delete: {path}")
    if not path.exists():
        print(" - (session folder does not exist)")
        return
    key_files = ("state.json", "notes.md")
    for key in key_files:
        candidate = path / key
        if candidate.exists():
            print(f" - {key}")
    gates = path / "gates"
    if gates.exists() and gates.is_dir():
        count = sum(1 for _ in gates.glob("*.md"))
        print(f" - gates/ ({count} files)")


def cmd_finalize(slice_id: str, *, delete: bool) -> int:
    root = _scratch_root().resolve()
    session_dir, session_id = _session_dir(root, slice_id)
    _print_finalize_preview(session_dir)

    if not delete:
        print("DRY RUN (no deletion performed)")
        return 0

    if session_dir.exists():
        shutil.rmtree(session_dir)
    active_file = _active_path(root)
    if active_file.exists():
        active_id = active_file.read_text(encoding="utf-8").strip()
        if active_id == session_id:
            active_file.unlink(missing_ok=True)
    print(f"DELETED: {session_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage per-slice scratch notes and gates.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Create a slice scratch session.")
    start.add_argument("slice_id")

    note = sub.add_parser("note", help="Append a timestamped note to active slice.")
    note.add_argument("text", nargs="+")

    gate = sub.add_parser("gate", help="Open a gate record for the active slice.")
    gate.add_argument("name")
    gate.add_argument("--kind", choices=("ui", "backend"), required=True)

    gate_done = sub.add_parser("gate-done", help="Close a gate record for the active slice.")
    gate_done.add_argument("name")
    gate_done.add_argument("--result", choices=("pass", "fail", "blocked"), required=True)

    finalize = sub.add_parser(
        "finalize",
        help="Preview deletion by default. Pass --delete to remove one slice scratch session.",
    )
    finalize.add_argument("slice_id")
    finalize.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete the session folder.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "start":
            return cmd_start(args.slice_id)
        if args.cmd == "note":
            return cmd_note(" ".join(args.text).strip())
        if args.cmd == "gate":
            return cmd_gate(args.name, args.kind)
        if args.cmd == "gate-done":
            return cmd_gate_done(args.name, args.result)
        if args.cmd == "finalize":
            return cmd_finalize(args.slice_id, delete=bool(args.delete))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
