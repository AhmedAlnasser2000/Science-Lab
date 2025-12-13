# PhysicsLab Kernel (V1 Gravity Demo)

Minimal Rust `cdylib` that simulates a single ball under constant gravity and exposes a C ABI for Python (`ctypes`) or other callers.

## Build
- From repo root: `cargo build --release --manifest-path kernel/Cargo.toml`
- DLL output: `kernel/target/release/physicslab_kernel.dll`

## API (see `include/physicslab_kernel.h`)
- `pl_world_create(y0: f64, vy0: f64) -> u64`
- `pl_world_destroy(handle: u64)`
- `pl_world_step(handle: u64, dt: f64, steps: u32) -> i32`
- `pl_world_get_state(handle: u64, out_t: *mut f64, out_y: *mut f64, out_vy: *mut f64) -> i32`
- Error helpers: `pl_last_error_code()`, `pl_last_error_message(...)`

Status codes: `0 OK`, `1 INVALID_ARGUMENT`, `2 INVALID_HANDLE`, `3 POLICY_DENIED`, `4 INTERNAL_ERROR`.

Physics: `g = 9.81 m/s^2`, update loop `vy -= g*dt`, `y += vy*dt`, `t += dt`.

Limits: reject non-finite or non-positive `dt`, `steps == 0`, `steps > 10_000`.

## Tests
- Determinism: same inputs produce same outputs.
- Invalid dt: rejected with `INVALID_ARGUMENT`.
