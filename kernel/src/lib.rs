use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{LazyLock, Mutex};

const OK: i32 = 0;
const INVALID_ARGUMENT: i32 = 1;
const INVALID_HANDLE: i32 = 2;
const POLICY_DENIED: i32 = 3;
const INTERNAL_ERROR: i32 = 4;

const MAX_STEPS: u32 = 10_000;
const G: f64 = 9.81;

struct World {
    t: f64,
    y: f64,
    vy: f64,
}

struct LastError {
    code: i32,
    message: String,
}

static HANDLE_COUNTER: AtomicU64 = AtomicU64::new(1);
static WORLDS: LazyLock<Mutex<HashMap<u64, World>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));
static LAST_ERROR: LazyLock<Mutex<LastError>> = LazyLock::new(|| {
    Mutex::new(LastError {
        code: OK,
        message: String::new(),
    })
});

fn set_error(code: i32, message: impl Into<String>) -> i32 {
    if let Ok(mut err) = LAST_ERROR.lock() {
        err.code = code;
        err.message = message.into();
    }
    code
}

fn clear_error() {
    let _ = set_error(OK, "");
}

fn validate_dt(dt: f64) -> Result<(), i32> {
    if !dt.is_finite() {
        return Err(set_error(INVALID_ARGUMENT, "dt must be finite"));
    }
    if dt <= 0.0 {
        return Err(set_error(INVALID_ARGUMENT, "dt must be positive"));
    }
    Ok(())
}

fn validate_steps(steps: u32) -> Result<(), i32> {
    if steps == 0 {
        return Err(set_error(INVALID_ARGUMENT, "steps must be > 0"));
    }
    if steps > MAX_STEPS {
        return Err(set_error(POLICY_DENIED, "steps exceeds limit"));
    }
    Ok(())
}

fn world_map() -> Result<std::sync::MutexGuard<'static, HashMap<u64, World>>, i32> {
    WORLDS
        .lock()
        .map_err(|_| set_error(INTERNAL_ERROR, "failed to lock worlds"))
}

#[no_mangle]
pub extern "C" fn pl_last_error_code() -> i32 {
    LAST_ERROR
        .lock()
        .map(|err| err.code)
        .unwrap_or(INTERNAL_ERROR)
}

#[no_mangle]
pub extern "C" fn pl_last_error_message(out_buf: *mut u8, buf_len: u32) -> u32 {
    let msg = LAST_ERROR
        .lock()
        .map(|err| err.message.clone())
        .unwrap_or_else(|_| "failed to lock error".to_string());
    let bytes = msg.as_bytes();
    let needed = bytes.len() as u32;
    if out_buf.is_null() || buf_len == 0 {
        return needed;
    }
    let copy_len = std::cmp::min(bytes.len(), (buf_len - 1) as usize);
    unsafe {
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), out_buf, copy_len);
        *out_buf.add(copy_len) = 0;
    }
    needed
}

#[no_mangle]
pub extern "C" fn pl_world_create(y0: f64, vy0: f64) -> u64 {
    if !y0.is_finite() || !vy0.is_finite() {
        set_error(INVALID_ARGUMENT, "y0 and vy0 must be finite");
        return 0;
    }
    clear_error();
    let handle = HANDLE_COUNTER.fetch_add(1, Ordering::SeqCst);
    let world = World { t: 0.0, y: y0, vy: vy0 };
    match WORLDS.lock() {
        Ok(mut map) => {
            map.insert(handle, world);
            handle
        }
        Err(_) => {
            set_error(INTERNAL_ERROR, "failed to lock worlds");
            0
        }
    }
}

#[no_mangle]
pub extern "C" fn pl_world_destroy(handle: u64) {
    if handle == 0 {
        set_error(INVALID_HANDLE, "invalid handle");
        return;
    }
    match WORLDS.lock() {
        Ok(mut map) => {
            if map.remove(&handle).is_some() {
                clear_error();
            } else {
                set_error(INVALID_HANDLE, "unknown handle");
            }
        }
        Err(_) => {
            set_error(INTERNAL_ERROR, "failed to lock worlds");
        }
    }
}

#[no_mangle]
pub extern "C" fn pl_world_step(handle: u64, dt: f64, steps: u32) -> i32 {
    if handle == 0 {
        return set_error(INVALID_HANDLE, "invalid handle");
    }
    if let Err(code) = validate_dt(dt) {
        return code;
    }
    if let Err(code) = validate_steps(steps) {
        return code;
    }
    let mut worlds = match world_map() {
        Ok(m) => m,
        Err(code) => return code,
    };
    let world = match worlds.get_mut(&handle) {
        Some(w) => w,
        None => return set_error(INVALID_HANDLE, "unknown handle"),
    };
    for _ in 0..steps {
        world.vy -= G * dt;
        world.y += world.vy * dt;
        world.t += dt;
    }
    clear_error();
    OK
}

#[no_mangle]
pub extern "C" fn pl_world_get_state(handle: u64, out_t: *mut f64, out_y: *mut f64, out_vy: *mut f64) -> i32 {
    if handle == 0 {
        return set_error(INVALID_HANDLE, "invalid handle");
    }
    if out_t.is_null() || out_y.is_null() || out_vy.is_null() {
        return set_error(INVALID_ARGUMENT, "output pointers must be non-null");
    }
    let mut worlds = match world_map() {
        Ok(m) => m,
        Err(code) => return code,
    };
    let world = match worlds.get(&handle) {
        Some(w) => w,
        None => return set_error(INVALID_HANDLE, "unknown handle"),
    };
    unsafe {
        *out_t = world.t;
        *out_y = world.y;
        *out_vy = world.vy;
    }
    clear_error();
    OK
}
