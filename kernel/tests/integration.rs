const OK: i32 = 0;
const INVALID_ARGUMENT: i32 = 1;

#[link(name = "physicslab_kernel", kind = "dylib")]
extern "C" {
    fn pl_world_create(y0: f64, vy0: f64) -> u64;
    fn pl_world_destroy(handle: u64);
    fn pl_world_step(handle: u64, dt: f64, steps: u32) -> i32;
    fn pl_world_get_state(handle: u64, out_t: *mut f64, out_y: *mut f64, out_vy: *mut f64) -> i32;
    fn pl_last_error_code() -> i32;
}

fn run_sim(y0: f64, vy0: f64, dt: f64, steps: u32) -> (f64, f64, f64) {
    unsafe {
        let handle = pl_world_create(y0, vy0);
        assert_ne!(handle, 0);
        let status = pl_world_step(handle, dt, steps);
        assert_eq!(status, OK);
        let mut t = 0.0;
        let mut y = 0.0;
        let mut vy = 0.0;
        let status_state = pl_world_get_state(handle, &mut t, &mut y, &mut vy);
        assert_eq!(status_state, OK);
        pl_world_destroy(handle);
        (t, y, vy)
    }
}

#[test]
fn determinism_same_inputs_same_outputs() {
    let a = run_sim(10.0, 0.0, 0.1, 50);
    let b = run_sim(10.0, 0.0, 0.1, 50);
    assert!((a.0 - b.0).abs() < 1e-12);
    assert!((a.1 - b.1).abs() < 1e-9);
    assert!((a.2 - b.2).abs() < 1e-9);
}

#[test]
fn invalid_dt_rejected() {
    unsafe {
        let handle = pl_world_create(0.0, 0.0);
        assert_ne!(handle, 0);
        let status = pl_world_step(handle, 0.0, 1);
        assert_eq!(status, INVALID_ARGUMENT);
        assert_eq!(pl_last_error_code(), INVALID_ARGUMENT);
        pl_world_destroy(handle);
    }
}
