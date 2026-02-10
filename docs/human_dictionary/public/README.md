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
