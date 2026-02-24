> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.
> Snapshot copy for portability; source-of-truth remains under docs/ at commit 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

# Human Dictionary Export

Generated artifacts:
- `human_dictionary.html` (primary visual document)
- `human_dictionary.pdf` (primary print/share document)

Build command:
```bash
python tools/export_human_dictionary.py --html --pdf
```

If PDF is skipped:
- Install one PDF backend:
- WeasyPrint system dependencies (Windows native libs), or
- `wkhtmltopdf` binary available on PATH.

