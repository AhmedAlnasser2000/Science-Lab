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
    "ERROR_RAISED",
    "RUNTIME_BUS_REPORT_REQUEST",
]
