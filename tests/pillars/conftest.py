from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def temp_output_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="pillars_test_") as tmp:
        yield Path(tmp)
