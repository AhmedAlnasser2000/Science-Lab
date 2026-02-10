from __future__ import annotations

import argparse
import html
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "docs" / "human_dictionary" / "_dev"
OUT_ROOT = ROOT / "docs" / "human_dictionary" / "public"
HTML_OUT = OUT_ROOT / "human_dictionary.html"
PDF_OUT = OUT_ROOT / "human_dictionary.pdf"


PAGES = [
    ("Glossary", SRC_ROOT / "glossary.md"),
    ("Workspaces, Runs, Templates", SRC_ROOT / "workspaces_runs_templates.md"),
    ("Packs, Repo, Store", SRC_ROOT / "packs_repo_store.md"),
    ("CodeSee: Peek, Inspector, Lens", SRC_ROOT / "codesee" / "peek_inspector_lens.md"),
    ("Runtime Bus: Trace, Trail, Messages", SRC_ROOT / "runtime_bus" / "trace_trail_messages.md"),
]


def _markdown_to_html(md_text: str) -> str:
    try:
        import markdown  # type: ignore

        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except Exception:
        lines = md_text.splitlines()
        out: list[str] = []
        for line in lines:
            s = line.rstrip()
            if s.startswith("### "):
                out.append(f"<h3>{html.escape(s[4:])}</h3>")
            elif s.startswith("## "):
                out.append(f"<h2>{html.escape(s[3:])}</h2>")
            elif s.startswith("# "):
                out.append(f"<h1>{html.escape(s[2:])}</h1>")
            elif s.startswith("- "):
                if not out or not out[-1].endswith("</ul>"):
                    out.append("<ul>")
                out.append(f"<li>{html.escape(s[2:])}</li>")
            elif s.strip() == "":
                if out and out[-1] == "</ul>":
                    continue
                out.append("<p></p>")
            else:
                if out and out[-1].startswith("<ul>") and not s.startswith("- "):
                    out.append("</ul>")
                out.append(f"<p>{html.escape(s)}</p>")
        if out and out[-1] == "<ul>":
            out[-1] = "<ul></ul>"
        if out and "<ul>" in out and "</ul>" not in out:
            out.append("</ul>")
        return "\n".join(out)


def build_html() -> Path:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []
    toc: list[str] = []

    for idx, (title, path) in enumerate(PAGES, start=1):
        if not path.exists():
            continue
        slug = f"sec-{idx}"
        toc.append(f'<li><a href="#{slug}">{html.escape(title)}</a></li>')
        content = _markdown_to_html(path.read_text(encoding="utf-8"))
        sections.append(f'<section id="{slug}"><h2>{html.escape(title)}</h2>{content}</section>')

    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PhysicsLab Human Dictionary</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111c34;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #60a5fa;
      --header: #f59e0b;
      --border: #26334d;
    }}
    body {{
      margin: 0;
      font-family: Segoe UI, Arial, sans-serif;
      background: radial-gradient(circle at top, #1a2747 0%, var(--bg) 45%);
      color: var(--text);
      line-height: 1.5;
    }}
    .wrap {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 28px 20px 60px;
    }}
    .panel {{
      background: linear-gradient(180deg, rgba(17, 28, 52, 0.96), rgba(12, 23, 45, 0.96));
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px 20px;
      margin-bottom: 16px;
    }}
    h1 {{
      margin: 0 0 6px;
      color: var(--accent);
      font-size: 32px;
    }}
    h2 {{
      margin: 16px 0 10px;
      color: var(--header);
      border-bottom: 1px solid var(--border);
      padding-bottom: 6px;
    }}
    h3 {{
      color: var(--accent);
      margin-top: 18px;
    }}
    p, li {{
      color: var(--text);
    }}
    .muted {{
      color: var(--muted);
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    ul {{
      margin-top: 6px;
    }}
    code {{
      background: #0b1224;
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 1px 5px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>PhysicsLab Human Dictionary</h1>
      <div class="muted">V5.5d1 note: human dictionary source + visual export.</div>
    </div>
    <div class="panel">
      <h2>Contents</h2>
      <ul>
        {"".join(toc)}
      </ul>
    </div>
    {"".join(sections)}
  </div>
</body>
</html>
"""
    HTML_OUT.write_text(doc, encoding="utf-8")
    return HTML_OUT


def build_pdf(html_path: Path) -> tuple[bool, str]:
    try:
        from weasyprint import HTML  # type: ignore

        HTML(filename=str(html_path)).write_pdf(str(PDF_OUT))
        return True, "PDF built with weasyprint"
    except Exception:
        pass

    try:
        subprocess.run(
            ["wkhtmltopdf", str(html_path), str(PDF_OUT)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "PDF built with wkhtmltopdf"
    except Exception as exc:
        wkhtml_err = str(exc)

    # Last-resort pure-Python fallback so teams can still get a readable PDF
    # on machines without native weasyprint/wkhtmltopdf backends.
    try:
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer  # type: ignore

        def _inline(md_line: str) -> str:
            text = html.escape(md_line)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
            return text

        styles = getSampleStyleSheet()
        style_title = ParagraphStyle(
            "HDTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1f4e8c"),
            spaceAfter=12,
        )
        style_section = ParagraphStyle(
            "HDSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#b35c00"),
            spaceBefore=8,
            spaceAfter=6,
        )
        style_term = ParagraphStyle(
            "HDTerm",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#1f4e8c"),
            spaceBefore=6,
            spaceAfter=3,
        )
        style_body = ParagraphStyle(
            "HDBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#202020"),
            spaceAfter=3,
        )
        style_meta = ParagraphStyle(
            "HDMeta",
            parent=style_body,
            textColor=colors.HexColor("#5a5a5a"),
            fontSize=9.5,
            spaceAfter=8,
        )

        story: list[object] = []
        story.append(Paragraph("PhysicsLab Human Dictionary", style_title))
        story.append(Paragraph("Public dictionary with user-friendly language.", style_meta))

        for title, path in PAGES:
            if not path.exists():
                continue
            story.append(Paragraph(_inline(title), style_section))
            bullets: list[ListItem] = []
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line:
                    if bullets:
                        story.append(
                            ListFlowable(
                                bullets,
                                bulletType="bullet",
                                start="circle",
                                leftIndent=14,
                                bulletFontName="Helvetica",
                                bulletFontSize=8,
                            )
                        )
                        bullets = []
                    story.append(Spacer(1, 4))
                    continue
                if line.startswith("# "):
                    continue
                if line.startswith("## "):
                    if bullets:
                        story.append(
                            ListFlowable(
                                bullets,
                                bulletType="bullet",
                                start="circle",
                                leftIndent=14,
                                bulletFontName="Helvetica",
                                bulletFontSize=8,
                            )
                        )
                        bullets = []
                    story.append(Paragraph(_inline(line[3:]), style_section))
                    continue
                if line.startswith("### "):
                    if bullets:
                        story.append(
                            ListFlowable(
                                bullets,
                                bulletType="bullet",
                                start="circle",
                                leftIndent=14,
                                bulletFontName="Helvetica",
                                bulletFontSize=8,
                            )
                        )
                        bullets = []
                    story.append(Paragraph(_inline(line[4:]), style_term))
                    continue
                if line.startswith("- "):
                    bullets.append(ListItem(Paragraph(_inline(line[2:]), style_body)))
                    continue
                if bullets:
                    story.append(
                        ListFlowable(
                            bullets,
                            bulletType="bullet",
                            start="circle",
                            leftIndent=14,
                            bulletFontName="Helvetica",
                            bulletFontSize=8,
                        )
                    )
                    bullets = []
                story.append(Paragraph(_inline(line), style_body))
            if bullets:
                story.append(
                    ListFlowable(
                        bullets,
                        bulletType="bullet",
                        start="circle",
                        leftIndent=14,
                        bulletFontName="Helvetica",
                        bulletFontSize=8,
                    )
                )
            story.append(Spacer(1, 8))

        doc = SimpleDocTemplate(
            str(PDF_OUT),
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
            title="PhysicsLab Human Dictionary",
            author="PhysicsLab",
        )
        doc.build(story)
        return True, "PDF built with reportlab fallback"
    except Exception as reportlab_exc:
        return (
            False,
            "PDF skipped (install weasyprint/wkhtmltopdf/reportlab): "
            f"wkhtmltopdf={wkhtml_err}; reportlab={reportlab_exc}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export human dictionary to HTML/PDF.")
    parser.add_argument("--html", action="store_true", help="Build HTML export")
    parser.add_argument("--pdf", action="store_true", help="Build PDF export")
    args = parser.parse_args()

    do_html = args.html or not args.pdf
    do_pdf = args.pdf

    html_path = HTML_OUT
    if do_html:
        html_path = build_html()
        print(f"[ok] HTML: {html_path}")

    if do_pdf:
        ok, msg = build_pdf(html_path)
        status = "ok" if ok else "warn"
        print(f"[{status}] {msg}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
