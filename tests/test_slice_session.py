from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "dev" / "slice_session.py"

_SPEC = importlib.util.spec_from_file_location("slice_session", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _run(tmp_path: Path, *args: str) -> int:
    key = "PHYSICSLAB_SLICE_TMP_DIR"
    previous = os.environ.get(key)
    os.environ[key] = str(tmp_path / ".slice_tmp")
    try:
        return int(_MODULE.main(list(args)))
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def test_slice_session_start_and_note(tmp_path: Path) -> None:
    assert _run(tmp_path, "start", "V5.5d6") == 0

    session_dir = tmp_path / ".slice_tmp" / "V5.5d6"
    assert session_dir.exists()
    assert (session_dir / "state.json").exists()
    assert (session_dir / "notes.md").exists()
    assert (session_dir / "gates").exists()

    state = json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
    assert state["slice_id"] == "V5.5d6"
    assert state["gates"] == []

    assert _run(tmp_path, "note", "Gate", "1", "started") == 0
    notes = (session_dir / "notes.md").read_text(encoding="utf-8")
    assert "Gate 1 started" in notes


def test_slice_session_gate_and_finalize(tmp_path: Path) -> None:
    assert _run(tmp_path, "start", "V5.5d6") == 0
    assert _run(tmp_path, "gate", "inspector-routing", "--kind", "ui") == 0

    session_dir = tmp_path / ".slice_tmp" / "V5.5d6"
    gate_files = sorted((session_dir / "gates").glob("*.md"))
    assert len(gate_files) == 1
    gate_text = gate_files[0].read_text(encoding="utf-8")
    assert "- Kind: ui" in gate_text
    assert "- Status: open" in gate_text

    assert _run(tmp_path, "gate-done", "inspector-routing", "--result", "pass") == 0
    gate_text = gate_files[0].read_text(encoding="utf-8")
    assert "- Result: pass" in gate_text

    assert _run(tmp_path, "finalize", "V5.5d6") == 0
    assert not session_dir.exists()
