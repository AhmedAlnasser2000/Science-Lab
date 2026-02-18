from __future__ import annotations

import importlib.util
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "dev" / "slice_session.py"

_SPEC = importlib.util.spec_from_file_location("slice_session", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _run(tmp_path: Path, *args: str) -> tuple[int, str, str]:
    key = "PHYSICSLAB_SLICE_TMP_DIR"
    previous = os.environ.get(key)
    os.environ[key] = str(tmp_path / ".slice_tmp")
    try:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = int(_MODULE.main(list(args)))
        return code, stdout.getvalue(), stderr.getvalue()
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def test_slice_session_start_and_note(tmp_path: Path) -> None:
    code, _out, _err = _run(tmp_path, "start", "V5.5d6")
    assert code == 0

    session_dir = tmp_path / ".slice_tmp" / "V5.5d6"
    assert session_dir.exists()
    assert (session_dir / "state.json").exists()
    assert (session_dir / "notes.md").exists()
    assert (session_dir / "gates").exists()

    state = json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
    assert state["slice_id"] == "V5.5d6"
    assert state["gates"] == []

    code, _out, _err = _run(tmp_path, "note", "Gate", "1", "started")
    assert code == 0
    notes = (session_dir / "notes.md").read_text(encoding="utf-8")
    assert "Gate 1 started" in notes


def test_slice_session_gate_and_finalize_dry_run_then_delete(tmp_path: Path) -> None:
    code, _out, _err = _run(tmp_path, "start", "V5.5d6")
    assert code == 0
    code, _out, _err = _run(tmp_path, "gate", "inspector-routing", "--kind", "ui")
    assert code == 0

    session_dir = tmp_path / ".slice_tmp" / "V5.5d6"
    gate_files = sorted((session_dir / "gates").glob("*.md"))
    assert len(gate_files) == 1
    gate_text = gate_files[0].read_text(encoding="utf-8")
    assert "- Kind: ui" in gate_text
    assert "- Status: open" in gate_text

    code, _out, _err = _run(tmp_path, "gate-done", "inspector-routing", "--result", "pass")
    assert code == 0
    gate_text = gate_files[0].read_text(encoding="utf-8")
    assert "- Result: pass" in gate_text

    code, out, _err = _run(tmp_path, "finalize", "V5.5d6")
    assert code == 0
    assert "Would delete:" in out
    assert "DRY RUN (no deletion performed)" in out
    assert session_dir.exists()

    code, out, _err = _run(tmp_path, "finalize", "V5.5d6", "--delete")
    assert code == 0
    assert "DELETED:" in out
    assert not session_dir.exists()


def test_slice_session_finalize_rejects_path_traversal_and_absolute_ids(tmp_path: Path) -> None:
    code, _out, _err = _run(tmp_path, "start", "safe_slice")
    assert code == 0

    outside = tmp_path / "outside_keep.txt"
    outside.write_text("keep", encoding="utf-8")
    safe_dir = tmp_path / ".slice_tmp" / "safe_slice"
    assert safe_dir.exists()

    malicious_ids = ("..", "../..", "..\\..", "C:\\Windows")
    for bad_id in malicious_ids:
        code, _out, err = _run(tmp_path, "finalize", bad_id, "--delete")
        assert code == 1
        assert "invalid slice_id" in err or "unsafe path" in err
        assert outside.exists()
        assert safe_dir.exists()
