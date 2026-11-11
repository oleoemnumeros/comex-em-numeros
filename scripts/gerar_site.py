"""Gera docs/index.html (o site) a partir de site/template.html e data/dados.json.

Os dados vão embutidos na própria página, para ela abrir rápido e funcionar
em qualquer hospedagem estática (GitHub Pages, Cloudflare Pages...).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEMPLATE = RAIZ / "site" / "template.html"
DADOS = RAIZ / "data" / "dados.json"
SAIDA = RAIZ / "docs"


def main() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    dados = DADOS.read_text(encoding="utf-8") if DADOS.exists() else "null"
    json.loads(dados)  # garante que é JSON válido
    seguro = dados.replace("</", "<\\/")  # não deixa o JSON fechar a tag <script>
    html = html.replace("/*__DADOS__*/", seguro, 1)
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / "index.html").write_text(html, encoding="utf-8")
    if DADOS.exists():
        shutil.copy(DADOS, SAIDA / "dados.json")
    (SAIDA / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site gerado em {SAIDA / 'index.html'} ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
