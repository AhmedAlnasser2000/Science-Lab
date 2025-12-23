"""Topic constants for the runtime bus."""

# UI
UI_PROFILE_CHANGED = "ui.profile.changed"
UI_PACK_CHANGED = "ui.pack.changed"

# Content install
CONTENT_INSTALL_REQUEST = "content.install.request"
CONTENT_INSTALL_PROGRESS = "content.install.progress"
CONTENT_INSTALL_COMPLETED = "content.install.completed"

# Labs
LAB_OPEN_REQUEST = "lab.open.request"
LAB_RUN_STARTED = "lab.run.started"
LAB_RUN_STOPPED = "lab.run.stopped"
LAB_TELEMETRY = "lab.telemetry"

# Job lifecycle
JOB_STARTED = "job.started"
JOB_PROGRESS = "job.progress"
JOB_COMPLETED = "job.completed"

# Core / storage
CORE_STORAGE_REPORT_REQUEST = "core.storage.report.request"
CORE_STORAGE_REPORT_READY = "core.storage.report.ready"
CORE_CLEANUP_REQUEST = "core.cleanup.request"
CORE_CLEANUP_STARTED = "core.cleanup.started"
CORE_CLEANUP_COMPLETED = "core.cleanup.completed"
CORE_STORAGE_ALLOCATE_RUN_DIR_REQUEST = "core.storage.allocate_run_dir.request"
CORE_POLICY_GET_REQUEST = "core.policy.get.request"
CORE_REGISTRY_GET_REQUEST = "core.registry.get.request"
CORE_INVENTORY_GET_REQUEST = "core.inventory.get.request"
CORE_CONTENT_MODULE_INSTALL_REQUEST = "core.content.module.install.request"
CORE_CONTENT_MODULE_UNINSTALL_REQUEST = "core.content.module.uninstall.request"
CORE_COMPONENT_PACK_INSTALL_REQUEST = "core.component_pack.install.request"
CORE_COMPONENT_PACK_UNINSTALL_REQUEST = "core.component_pack.uninstall.request"
CORE_JOBS_LIST_REQUEST = "core.jobs.list.request"
CORE_JOBS_GET_REQUEST = "core.jobs.get.request"

# Errors
ERROR_RAISED = "error.raised"

# Diagnostics
RUNTIME_BUS_REPORT_REQUEST = "runtime.bus.report.request"

__all__ = [
    "UI_PROFILE_CHANGED",
    "UI_PACK_CHANGED",
    "CONTENT_INSTALL_REQUEST",
    "CONTENT_INSTALL_PROGRESS",
    "CONTENT_INSTALL_COMPLETED",
    "LAB_OPEN_REQUEST",
    "LAB_RUN_STARTED",
    "LAB_RUN_STOPPED",
    "LAB_TELEMETRY",
    "JOB_STARTED",
    "JOB_PROGRESS",
    "JOB_COMPLETED",
    "CORE_STORAGE_REPORT_REQUEST",
    "CORE_STORAGE_REPORT_READY",
    "CORE_CLEANUP_REQUEST",
    "CORE_CLEANUP_STARTED",
    "CORE_CLEANUP_COMPLETED",
    "CORE_STORAGE_ALLOCATE_RUN_DIR_REQUEST",
    "CORE_POLICY_GET_REQUEST",
    "CORE_REGISTRY_GET_REQUEST",
    "CORE_INVENTORY_GET_REQUEST",
    "CORE_CONTENT_MODULE_INSTALL_REQUEST",
    "CORE_CONTENT_MODULE_UNINSTALL_REQUEST",
    "CORE_COMPONENT_PACK_INSTALL_REQUEST",
    "CORE_COMPONENT_PACK_UNINSTALL_REQUEST",
    "CORE_JOBS_LIST_REQUEST",
    "CORE_JOBS_GET_REQUEST",
    "ERROR_RAISED",
    "RUNTIME_BUS_REPORT_REQUEST",
]
