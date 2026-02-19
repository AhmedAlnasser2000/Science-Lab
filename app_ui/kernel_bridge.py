# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] DLL candidates + load strategy
# [NAV-20] ABI symbol binding
# [NAV-30] Public bridge API
# [NAV-99] End
# =============================================================================

# === [NAV-00] Imports / constants ============================================
import ctypes
import sys
from pathlib import Path
from typing import List, Tuple

# === [NAV-10] DLL candidates + load strategy =================================
DLL_CANDIDATES = [
    Path("kernel/target/release/physicslab_kernel.dll"),
    Path("app_ui/native/physicslab_kernel.dll"),
]


class KernelNotAvailable(Exception):
    pass


def _load_library() -> ctypes.CDLL:
    for candidate in DLL_CANDIDATES:
        if candidate.exists():
            return ctypes.CDLL(str(candidate))
    raise KernelNotAvailable(
        "Kernel DLL not found. Build the Rust kernel then try again."
    )


def _resolve_symbols():
    # === [NAV-20] ABI symbol binding =========================================
    lib = _load_library()
    lib.pl_world_create.argtypes = [ctypes.c_double, ctypes.c_double]
    lib.pl_world_create.restype = ctypes.c_uint64

    lib.pl_world_destroy.argtypes = [ctypes.c_uint64]
    lib.pl_world_destroy.restype = None

    lib.pl_world_step.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_uint32]
    lib.pl_world_step.restype = ctypes.c_int32

    lib.pl_world_get_state.argtypes = [
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    lib.pl_world_get_state.restype = ctypes.c_int32

    lib.pl_last_error_code.argtypes = []
    lib.pl_last_error_code.restype = ctypes.c_int32

    lib.pl_last_error_message.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
    lib.pl_last_error_message.restype = ctypes.c_uint32

    return lib


_LIB = None
_KERNEL_FALLBACK_LOGGED = False


# === [NAV-30] Public bridge API ===============================================
def ensure_kernel_available() -> None:
    _get_lib()


def kernel_available() -> bool:
    try:
        ensure_kernel_available()
        return True
    except KernelNotAvailable:
        return False


def _get_lib() -> ctypes.CDLL:
    global _LIB
    if _LIB is None:
        _LIB = _resolve_symbols()
    return _LIB


def _fetch_error(lib: ctypes.CDLL) -> str:
    buf = ctypes.create_string_buffer(256)
    required = lib.pl_last_error_message(buf, ctypes.sizeof(buf))
    if required >= ctypes.sizeof(buf):
        buf = ctypes.create_string_buffer(required + 1)
        lib.pl_last_error_message(buf, ctypes.sizeof(buf))
    return buf.value.decode("utf-8", errors="replace")


def log_kernel_fallback_once(reason: Exception | str) -> None:
    global _KERNEL_FALLBACK_LOGGED
    if _KERNEL_FALLBACK_LOGGED:
        return
    _KERNEL_FALLBACK_LOGGED = True
    message = str(reason).strip() or "Kernel backend unavailable."
    try:
        sys.stderr.write(f"Simulation fallback active (python backend): {message}\n")
    except Exception:
        pass


class GravityKernelSession:
    def __init__(self, y0: float, vy0: float):
        self.lib = _get_lib()
        self.handle = self.lib.pl_world_create(ctypes.c_double(y0), ctypes.c_double(vy0))
        if self.handle == 0:
            raise RuntimeError(_fetch_error(self.lib))

    def reset(self, y0: float, vy0: float) -> None:
        self.close()
        self.handle = self.lib.pl_world_create(ctypes.c_double(y0), ctypes.c_double(vy0))
        if self.handle == 0:
            raise RuntimeError(_fetch_error(self.lib))

    def step(self, dt: float, steps: int = 1) -> None:
        status = self.lib.pl_world_step(
            self.handle,
            ctypes.c_double(dt),
            ctypes.c_uint32(max(1, steps)),
        )
        if status != 0:
            raise RuntimeError(_fetch_error(self.lib))

    def get_state(self) -> Tuple[float, float, float]:
        t = ctypes.c_double()
        y = ctypes.c_double()
        vy = ctypes.c_double()
        status = self.lib.pl_world_get_state(
            self.handle,
            ctypes.byref(t),
            ctypes.byref(y),
            ctypes.byref(vy),
        )
        if status != 0:
            raise RuntimeError(_fetch_error(self.lib))
        return t.value, y.value, vy.value

    def close(self) -> None:
        if getattr(self, "handle", 0):
            self.lib.pl_world_destroy(ctypes.c_uint64(self.handle))
            self.handle = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def create_gravity_session(y0: float, vy0: float) -> GravityKernelSession:
    return GravityKernelSession(y0, vy0)


def run_gravity_demo(
    y0: float = 10.0, vy0: float = 0.0, dt: float = 0.01, steps: int = 300
) -> List[Tuple[float, float, float]]:
    session = create_gravity_session(y0, vy0)
    results: List[Tuple[float, float, float]] = []
    try:
        for _ in range(steps):
            session.step(dt)
            results.append(session.get_state())
    finally:
        session.close()
    return results


# === [NAV-99] End =============================================================
