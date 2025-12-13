import ctypes
from pathlib import Path
from typing import List, Tuple

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


def ensure_kernel_available() -> None:
    _get_lib()


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


def run_gravity_demo(
    y0: float = 10.0, vy0: float = 0.0, dt: float = 0.01, steps: int = 300
) -> List[Tuple[float, float, float]]:
    lib = _get_lib()
    handle = lib.pl_world_create(ctypes.c_double(y0), ctypes.c_double(vy0))
    if handle == 0:
        raise RuntimeError(_fetch_error(lib))

    results: List[Tuple[float, float, float]] = []

    try:
        for _ in range(steps):
            status = lib.pl_world_step(handle, ctypes.c_double(dt), ctypes.c_uint32(1))
            if status != 0:
                raise RuntimeError(_fetch_error(lib))
            t = ctypes.c_double()
            y = ctypes.c_double()
            vy = ctypes.c_double()
            status_state = lib.pl_world_get_state(handle, ctypes.byref(t), ctypes.byref(y), ctypes.byref(vy))
            if status_state != 0:
                raise RuntimeError(_fetch_error(lib))
            results.append((t.value, y.value, vy.value))
    finally:
        lib.pl_world_destroy(handle)

    return results
