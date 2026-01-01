# Development Setup (Windows-friendly)

This repo uses a plain venv + pip workflow for development.

## Create and activate a venv
```bash
python -m venv .venv
```

Activation:
```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat
```

## Install dev dependencies
```bash
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
```

## Run the app (imports only)
```bash
python -m app_ui.main
```

## Run pillars tests
```bash
python -m pytest -q tests/pillars
```
