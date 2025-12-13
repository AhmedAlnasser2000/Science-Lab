#ifndef PHYSICSLAB_KERNEL_H
#define PHYSICSLAB_KERNEL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Status codes
#define PL_STATUS_OK 0
#define PL_STATUS_INVALID_ARGUMENT 1
#define PL_STATUS_INVALID_HANDLE 2
#define PL_STATUS_POLICY_DENIED 3
#define PL_STATUS_INTERNAL_ERROR 4

// Lifecycle
uint64_t pl_world_create(double y0, double vy0);
void pl_world_destroy(uint64_t handle);

// Simulation
int32_t pl_world_step(uint64_t handle, double dt, uint32_t steps);
int32_t pl_world_get_state(uint64_t handle, double* out_t, double* out_y, double* out_vy);

// Error inspection
int32_t pl_last_error_code(void);
uint32_t pl_last_error_message(uint8_t* out_buf, uint32_t buf_len);

#ifdef __cplusplus
}
#endif

#endif // PHYSICSLAB_KERNEL_H
