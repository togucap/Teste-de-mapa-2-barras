#!/usr/bin/env python3
"""Empacota o modelo do Blender para o Apps Script e gera a página única.

1. Lê o GLB exportado pelo Blender (padrão: saida/casa.glb), compacta em gzip e grava em base64 em
   apps-script/Modelo.html (o visualizador descompacta no navegador).
2. Gera dist/casa-3d.html juntando Index.html, Modelo.html e Viewer.html (abre direto no navegador).

Uso:
    python3 blender/gerar_casa.py --glb saida/casa.glb
    python3 tools/build.py [--glb saida/casa.glb]
"""
import argparse
import base64
import gzip
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "apps-script"
OUT = ROOT / "dist" / "casa-3d.html"
CHUNK = 2000


def write_model(glb: pathlib.Path):
    data = glb.read_bytes()
    packed = gzip.compress(data, compresslevel=9, mtime=0)
    b64 = base64.b64encode(packed).decode("ascii")
    lines = ",\n".join(f'"{b64[i:i + CHUNK]}"' for i in range(0, len(b64), CHUNK))
    html = (
        "<script>\n"
        "/* Modelo 3D da casa: GLB exportado do Blender por blender/gerar_casa.py, compactado em gzip e\n"
        "   codificado em base64 por tools/build.py. Não edite à mão: gere de novo pelos scripts. */\n"
        f"window.CASA_GLB = [\n{lines}\n];\n"
        "</script>\n"
    )
    (SRC / "Modelo.html").write_text(html, encoding="utf-8")
    print(f"Modelo.html: GLB {len(data) // 1024} KB -> gzip {len(packed) // 1024} KB -> base64 {len(b64) // 1024} KB")


def write_standalone():
    index = (SRC / "Index.html").read_text(encoding="utf-8")
    html = re.sub(
        r"<\?!=\s*include\('([^']+)'\);?\s*\?>",
        lambda m: (SRC / f"{m.group(1)}.html").read_text(encoding="utf-8").strip(),
        index,
    )
    if "<?" in html:
        raise SystemExit("Marcador de template não resolvido em Index.html")
    html = "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n" + html + "\n</html>\n"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Gerado {OUT.relative_to(ROOT)} ({len(html) // 1024} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", default=str(ROOT / "saida" / "casa.glb"))
    args = ap.parse_args()
    glb = pathlib.Path(args.glb)
    if glb.exists():
        write_model(glb)
    elif not (SRC / "Modelo.html").exists():
        raise SystemExit(f"GLB não encontrado: {glb}. Gere com blender/gerar_casa.py --glb {glb}")
    write_standalone()


if __name__ == "__main__":
    main()
