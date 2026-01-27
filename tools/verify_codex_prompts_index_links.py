#!/usr/bin/env python
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


INDEX_PATH = Path("docs/codex_prompts/INDEX.md")
LINK_RE = re.compile(r"\(([^)]+\.md)\)")


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"missing index: {INDEX_PATH}", file=sys.stderr)
        return 2
    base_dir = INDEX_PATH.parent
    text = INDEX_PATH.read_text(encoding="utf-8")
    links = set(LINK_RE.findall(text))
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().split("|")]
        if len(parts) < 3:
            continue
        candidate = parts[1]
        if candidate.endswith(".md"):
            links.add(candidate)
    missing: list[str] = []
    for rel in sorted(links):
        rel = rel.strip()
        if rel.startswith("http://") or rel.startswith("https://"):
            continue
        target = (base_dir / rel).resolve()
        if not target.exists():
            missing.append(rel)
    if missing:
        print("missing codex prompt index targets:", file=sys.stderr)
        for rel in missing:
            print(f" - {rel}", file=sys.stderr)
        return 1
    print(f"ok: {len(links)} links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
