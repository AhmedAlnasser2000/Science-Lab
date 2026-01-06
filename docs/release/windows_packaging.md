# Windows packaging

## Prerequisites
- Python 3.12
- Build dependencies:
  - `pip install -r requirements-dev.txt`
  - `pip install -r requirements-packaging.txt`

## Build
From the repo root:

```
python tools/release/build_windows.py --out dist/PhysicsLab
```

Outputs:
- `dist/PhysicsLab/PhysicsLab.exe`
- Bundled assets copied alongside the exe
- `dist/PhysicsLab/BUILD_INFO.txt`

## Run
```
cd dist/PhysicsLab
./PhysicsLab.exe
```
