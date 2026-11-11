"""Gera docs/index.html (o site) a partir de site/template.html e data/dados.json.

Os dados vão embutidos na própria página, para ela abrir rápido e funcionar
em qualquer hospedagem estática (GitHub Pages, Cloudflare Pages...).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEMPLATE = RAIZ / "site" / "template.html"
NOMES = RAIZ / "site" / "nomes_populares.json"
DADOS = RAIZ / "data" / "dados.json"
SAIDA = RAIZ / "docs"


def encurta(nome: str) -> str:
    """Nome curto a partir do texto oficial da posição SH4."""
    n = nome.split(";")[0]
    n = re.sub(r"\s*\((exceto|excet|incluíd|incluindo|por exemplo)[^)]*\)", "", n, flags=re.I)
    n = re.sub(r"\s+", " ", n).strip()
    if len(n) > 70:
        corte = n.rfind(",", 25, 70)
        n = n[:corte] if corte > 0 else n[:68].rsplit(" ", 1)[0] + "…"
    return n


def amigavel(nome: str) -> str:
    """'BENS DE CAPITAL (BK)' -> 'Bens de capital'."""
    n = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", nome.strip())
    if n.isupper():
        n = n.capitalize()
    if n.lower().startswith("bens não especificados"):
        n = "Outros"
    return n


def prepara(d: dict) -> dict:
    populares = json.loads(NOMES.read_text(encoding="utf-8")) if NOMES.exists() else {}
    for chave in ("produtos", "paises", "estados", "setores", "categorias"):
        for fluxo, itens in (d.get(chave) or {}).items():
            for it in itens:
                it["nome"] = it["nome"].replace("\xa0", " ").strip()
                if chave == "produtos":
                    it["curto"] = populares.get(it["codigo"]) or encurta(it["nome"])
                elif chave == "categorias":
                    it["nome"] = amigavel(it["nome"])
                elif chave == "estados" and it["nome"].lower().startswith("não declarad"):
                    it["nome"] = "UF não declarada"
    return d


def main() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    if DADOS.exists():
        dados = json.dumps(prepara(json.loads(DADOS.read_text(encoding="utf-8"))), ensure_ascii=False, separators=(",", ":"))
    else:
        dados = "null"
    seguro = dados.replace("</", "<\\/")  # não deixa o JSON fechar a tag <script>
    html = html.replace("/*__DADOS__*/", seguro, 1)
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / "index.html").write_text(html, encoding="utf-8")
    if DADOS.exists():
        (SAIDA / "dados.json").write_text(dados, encoding="utf-8")
    (SAIDA / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site gerado em {SAIDA / 'index.html'} ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
