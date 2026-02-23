import io

from app_ui import kernel_bridge


def test_log_kernel_fallback_once_emits_single_line(monkeypatch):
    stderr = io.StringIO()
    monkeypatch.setattr(kernel_bridge.sys, "stderr", stderr)
    kernel_bridge._KERNEL_FALLBACK_LOGGED = False
    try:
        kernel_bridge.log_kernel_fallback_once("Kernel DLL not found")
        kernel_bridge.log_kernel_fallback_once("Kernel DLL not found again")
    finally:
        kernel_bridge._KERNEL_FALLBACK_LOGGED = False
    lines = [line for line in stderr.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    assert "Simulation fallback active (python backend): Kernel DLL not found" == lines[0]
