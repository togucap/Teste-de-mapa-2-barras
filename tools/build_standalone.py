#!/usr/bin/env python3
"""Gera dist/duas-barras-3d.html: uma página única (sem Apps Script) para abrir no navegador.

Substitui os marcadores <?!= include('Nome'); ?> de apps-script/Index.html pelo conteúdo de apps-script/Nome.html.
Uso: python3 tools/build_standalone.py
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "apps-script"
OUT = ROOT / "dist" / "duas-barras-3d.html"


def main():
    index = (SRC / "Index.html").read_text(encoding="utf-8")
    html = re.sub(
        r"<\?!=\s*include\('([^']+)'\);?\s*\?>",
        lambda m: (SRC / f"{m.group(1)}.html").read_text(encoding="utf-8").strip(),
        index,
    )
    if "<?" in html:
        raise SystemExit("Marcador de template não resolvido em Index.html")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Gerado {OUT.relative_to(ROOT)} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
