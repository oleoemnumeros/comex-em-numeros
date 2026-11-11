"""Gera o site estático do Comex em Números em docs/.

Uma página HTML de verdade para cada produto (SH4), país e estado, com
título, descrição e conteúdo já prontos no HTML, para o Google indexar.
Também gera sitemap.xml, robots.txt, 404.html, busca e a página de embed.

Entrada: data/dados.json (gerado por scripts/atualizar.py)
         site/estilo.css, site/app.js, site/nomes_populares.json
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
import unicodedata
from email.utils import format_datetime
from pathlib import Path

try:  # a imagem do mês precisa do Pillow; sem ele o site sai igual, só sem a imagem
    from card import gera_card
except ImportError:  # pragma: no cover
    gera_card = None

RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "site"
DADOS = RAIZ / "data" / "dados.json"
RESUMOS = RAIZ / "data" / "resumos"
SAIDA = RAIZ / "docs"
DOMINIO = "comexemnumeros.com.br"
BASE = f"https://{DOMINIO}"
# Contador de visitas (GoatCounter: sem cookies, não precisa de aviso de LGPD)
GOAT = '<script data-goatcounter="https://comexemnumeros.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

# Família em Números: para incluir um novo portal, acrescente uma linha nesta lista
FAMILIA = [
    ("Óleo em Números", "Petróleo e gás", "https://oleoemnumeros.com.br/", "#B45309"),
    ("Comex em Números", "Exportações e importações", "https://comexemnumeros.com.br/", "var(--exp)"),
]


def familia_html(atual: str = "Comex em Números") -> str:
    itens = []
    for nome, tema, url, cor in FAMILIA:
        miolo = f'<span class="ponto" style="background:{cor}"></span><span><b>{nome}</b> {tema}</span>'
        if nome == atual:
            itens.append(f'<li>{miolo} <em>você está aqui</em></li>')
        else:
            itens.append(f'<li><a href="{url}">{miolo}</a></li>')
    return ('<div class="familia"><p><b>Família em Números</b> · portais independentes que organizam dados públicos do Brasil</p>'
            f'<ul>{"".join(itens)}</ul></div>')


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Artigo por estado: "a Bahia", "o Pará", "São Paulo"
ARTIGO_UF = {
    "Acre": "o", "Alagoas": "", "Amapá": "o", "Amazonas": "o", "Bahia": "a", "Ceará": "o",
    "Distrito Federal": "o", "Espírito Santo": "o", "Goiás": "", "Maranhão": "o",
    "Mato Grosso": "", "Mato Grosso do Sul": "", "Minas Gerais": "", "Pará": "o",
    "Paraíba": "a", "Paraná": "o", "Pernambuco": "", "Piauí": "o", "Rio de Janeiro": "o",
    "Rio Grande do Norte": "o", "Rio Grande do Sul": "o", "Rondônia": "", "Roraima": "",
    "Santa Catarina": "", "São Paulo": "", "Sergipe": "", "Tocantins": "o",
}


# Artigo dos países mais comuns: "a China", "os Estados Unidos", "Singapura"
ARTIGO_PAIS = {
    "China": "a", "Estados Unidos": "os", "Países Baixos (Holanda)": "os", "Argentina": "a", "Índia": "a",
    "Espanha": "a", "Chile": "o", "Indonésia": "a", "Japão": "o", "Canadá": "o", "México": "o", "Itália": "a",
    "Tailândia": "a", "França": "a", "Turquia": "a", "Alemanha": "a", "Peru": "o", "Uruguai": "o",
    "Emirados Árabes Unidos": "os", "Bélgica": "a", "Reino Unido": "o", "Paraguai": "o", "Coreia do Sul": "a",
    "Irã": "o", "Arábia Saudita": "a", "Egito": "o", "Vietnã": "o", "Malásia": "a", "Colômbia": "a",
    "Filipinas": "as", "Suíça": "a", "Polônia": "a", "Paquistão": "o", "Noruega": "a", "Argélia": "a",
    "Panamá": "o", "África do Sul": "a", "Marrocos": "o", "Bolívia": "a", "Nigéria": "a", "Equador": "o",
    "Rússia": "a", "Jordânia": "a", "Venezuela": "a", "Iraque": "o", "República Dominicana": "a",
    "Jamaica": "a", "Libéria": "a", "Austrália": "a", "Costa Rica": "a", "Eslovênia": "a", "Líbia": "a",
    "Grécia": "a", "Guatemala": "a", "Marshall, Ilhas": "as", "Dinamarca": "a", "Suécia": "a", "Finlândia": "a",
    "Irlanda": "a", "Áustria": "a", "Romênia": "a", "Ucrânia": "a", "Hungria": "a", "Tcheca, República": "a",
    "Eslováquia": "a", "Bulgária": "a", "Croácia": "a", "Sérvia": "a", "Lituânia": "a", "Letônia": "a",
    "Estônia": "a", "Nova Zelândia": "a", "Tunísia": "a", "Etiópia": "a", "Quênia": "o", "Tanzânia": "a",
    "Costa do Marfim": "a", "Mauritânia": "a", "Guiana": "a", "Guiana Francesa": "a", "Bahamas": "as",
    "Nicarágua": "a", "Bielorrússia": "a", "Geórgia": "a", "Somália": "a", "Síria": "a", "Arménia": "a",
    "Armênia": "a", "Albânia": "a", "Mongólia": "a", "Coreia do Norte": "a", "Islândia": "a", "Catar": "o",
    "Kuwait": "o", "Bahrein": "o", "Iêmen": "o", "Líbano": "o", "Sudão": "o", "Senegal": "o", "Camarões": "os",
    "Gabão": "o", "Congo": "o", "Chade": "o", "Níger": "o", "Mali": "o", "Togo": "o", "Benin": "o",
    "Malawi": "o", "Zimbábue": "o", "Zâmbia": "a", "Uzbequistão": "o", "Cazaquistão": "o", "Afeganistão": "o",
    "Nepal": "o", "Sri Lanka": "o", "Camboja": "o", "Laos": "o", "Butão": "o", "Brunei": "o", "Timor-Leste": "o",
    "Haiti": "o", "Suriname": "o", "Salvador, El": "", "Honduras": "", "Cuba": "", "Portugal": "",
    "Singapura": "", "Taiwan (Formosa)": "", "Hong Kong": "", "Israel": "", "Angola": "", "Moçambique": "",
    "Gana": "", "Omã": "", "Bangladesh": "", "Mianmar": "", "Luxemburgo": "o", "Chipre": "", "Malta": "",
}


def art_pais(nome: str) -> str:
    return ARTIGO_PAIS.get(nome, "")


def com_artigo(nome: str, prep: str, art: str) -> str:
    """prep: 'para' | 'de' | '' ; art: o, a, os, as ou vazio."""
    if prep == "de":
        p = {"o": "do", "a": "da", "os": "dos", "as": "das", "": "de"}[art]
        return f"{p} {nome}"
    if prep == "para":
        return f"para {art} {nome}" if art else f"para {nome}"
    return f"{art} {nome}".strip()


def desc_corta(t: str, n: int = 158) -> str:
    if len(t) <= n:
        return t
    t = t[:n].rsplit(" ", 1)[0].rstrip(",;:–-")
    return t + "…"


# ---------------------------------------------------------------- utilidades
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def slug(t: str, n: int = 60) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return (t[:n].rstrip("-")) or "item"


def nf(v: float, d: int = 0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def us(v: float) -> str:
    a, s = abs(v), ("−" if v < 0 else "")
    if a >= 1e9:
        return f"{s}US$ {nf(a / 1e9, 2)} bi"
    if a >= 1e6:
        return f"{s}US$ {nf(a / 1e6, 0 if a >= 1e8 else 1)} mi"
    if a >= 1e3:
        return f"{s}US$ {nf(a / 1e3, 0)} mil"
    return f"{s}US$ {nf(a, 0)}"


def us_sem(v: float) -> str:
    return us(v).replace("US$ ", "")


def pct(a: float, b: float):
    return None if not b else (a / b - 1) * 100


def chip(a: float, b: float) -> str:
    if not b and a > 0:
        return '<span class="chg up">novo</span>'
    if not b:
        return '<span class="chg flat">—</span>'
    p = pct(a, b)
    if abs(p) < 0.05:
        return '<span class="chg flat">0,0%</span>'
    txt = nf(abs(p), 0 if abs(p) >= 1000 else 1)
    return f'<span class="chg {"up" if p >= 0 else "down"}">{"▲" if p >= 0 else "▼"} {txt}%</span>'


def var_txt(a: float, b: float) -> str:
    p = pct(a, b)
    if p is None:
        return ""
    return f"{'alta' if p >= 0 else 'queda'} de {nf(abs(p), 1)}%"


def var_par(a: float, b: float) -> str:
    p = pct(a, b)
    if p is None:
        return ""
    return f" ({'+' if p >= 0 else '−'}{nf(abs(p), 1)}%)"


def mes_nome(m: str) -> str:
    return f"{MESES[int(m[5:]) - 1]} de {m[:4]}"


def mes_curto(m: str) -> str:
    return f"{MES_CURTO[int(m[5:]) - 1]}/{m[2:4]}"


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def minusc(s: str) -> str:
    # mantém siglas (GLP, NPK) e nomes em maiúscula quando a 2ª letra também é
    return s if len(s) > 1 and s[1].isupper() else s[:1].lower() + s[1:]


def encurta(nome: str) -> str:
    n = nome.split(";")[0]
    n = re.sub(r"\s*\((exceto|excet|incluíd|incluindo|por exemplo)[^)]*\)", "", n, flags=re.I)
    n = re.sub(r"\s+", " ", n).strip()
    if len(n) > 80:
        corte = n.rfind(",", 20, 80)
        n = n[:corte] if corte > 0 else n[:78].rsplit(" ", 1)[0].rstrip(",;") + "…"
    return n


def amigavel(nome: str) -> str:
    n = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", nome.strip())
    if n.isupper():
        n = n.capitalize()
    if n.lower().startswith("bens não especificados"):
        n = "Outros"
    return n


def corta(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def nao_declarado(nome: str) -> bool:
    n = (nome or "").lower()
    return not n or n.startswith("não declarad") or n.startswith("nao declarad")


# ---------------------------------------------------------------- dados
class Base:
    def __init__(self, d: dict):
        self.d = d
        self.ref, self.ant = d["mes"], d["mes_ant"]
        populares = json.loads((SITE / "nomes_populares.json").read_text(encoding="utf-8"))
        for chave in ("produtos", "paises", "estados", "setores", "categorias"):
            for itens in (d.get(chave) or {}).values():
                for it in itens:
                    it["nome"] = it["nome"].replace("\xa0", " ").strip()
                    if chave == "produtos":
                        it["curto"] = populares.get(it["codigo"]) or encurta(it["nome"])
                    elif chave == "categorias":
                        it["nome"] = amigavel(it["nome"])
                    elif chave == "estados" and nao_declarado(it["nome"]):
                        it["nome"] = "UF não declarada"
        self.prod: dict[str, dict] = {}
        for fl in ("export", "import"):
            for r in d["produtos"][fl]:
                p = self.prod.setdefault(r["codigo"], {"codigo": r["codigo"], "nome": r["nome"], "curto": r["curto"]})
                p[fl] = r
        from collections import Counter
        # Endereços congelados: uma vez publicado, o endereço de um produto não muda
        # (mesmo que o nome popular seja melhorado depois). Ver site/urls_produtos.json.
        self.arq_urls = SITE / "urls_produtos.json"
        self.urls = json.loads(self.arq_urls.read_text(encoding="utf-8")) if self.arq_urls.exists() else {}
        rep = Counter(p["curto"] for p in self.prod.values())
        for p in self.prod.values():
            if rep[p["curto"]] > 1:
                p["curto"] = f"{p['curto']} (SH4 {p['codigo']})"
                for fl in ("export", "import"):
                    if p.get(fl):
                        p[fl]["curto"] = p["curto"]
            if p["codigo"] in self.urls:
                p["url"] = self.urls[p["codigo"]]
            else:
                p["url"] = f"/produto/{p['codigo']}-{slug(p['curto'].split(' (SH4')[0], 50)}/"
                self.urls[p["codigo"]] = p["url"]
        self.pais = self._indice("paises", "/pais/")
        self.uf = {k: v for k, v in self._indice("estados", "/estado/").items() if v["nome"] in ARTIGO_UF}
        # séries mensais desde 2015 (data/serie/*.json)
        a0, m0 = 2015, 1
        ar, mr = int(self.ref[:4]), int(self.ref[5:])
        self.meses = [f"{y}-{m:02d}" for y in range(a0, ar + 1) for m in range(1, 13) if (y, m) <= (ar, mr)]
        self.serie = {}
        pasta = RAIZ / "data" / "serie"
        for tipo in ("produtos", "paises", "estados"):
            for fl in ("export", "import"):
                alvo = self.serie.setdefault((tipo, fl), {})
                for y in range(a0, ar + 1):
                    arq = pasta / f"{tipo}_{fl}_{y}.json"
                    if not arq.exists():
                        continue
                    itens = json.loads(arq.read_text(encoding="utf-8")).get("itens", {})
                    base_i = (y - a0) * 12
                    for chave, it in itens.items():
                        ch = chave.replace("\xa0", " ").strip()
                        reg = alvo.setdefault(ch, {"v": [0] * len(self.meses), "k": [0] * len(self.meses)})
                        for j in range(12):
                            if base_i + j < len(self.meses):
                                reg["v"][base_i + j] += it["v"][j]
                                if "k" in it:
                                    reg["k"][base_i + j] += it["k"][j]
        self.tem_serie = any(self.serie[k] for k in self.serie)
        cz = d.get("cruzado") or {}
        self.cz = {}
        for chave in ("produto_pais", "produto_estado"):
            for fl in ("export", "import"):
                linhas = (cz.get(chave) or {}).get(fl) or []
                self.cz[(chave, fl)] = [[c, n.replace("\xa0", " ").strip(), a, b] for c, n, a, b in linhas]

    def _indice(self, chave, prefixo):
        out = {}
        for fl in ("export", "import"):
            for r in self.d[chave][fl]:
                s = slug(r["nome"])
                it = out.setdefault(s, {"slug": s, "nome": r["nome"], "url": f"{prefixo}{s}/"})
                it[fl] = r
        return out

    def serie_de(self, tipo: str, fl: str, chave: str):
        reg = self.serie.get((tipo, fl), {}).get(chave)
        if not reg:
            return [0] * len(self.meses), [0] * len(self.meses)
        return reg["v"], reg["k"]

    def serie_total(self, fl: str):
        mapa = {r["mes"]: r["fob"] for r in self.d["mensal"][fl]}
        return [mapa.get(m, 0) for m in self.meses]

    def tot(self, fl: str, m: str) -> float:
        for r in self.d["mensal"][fl]:
            if r["mes"] == m:
                return r["fob"]
        return 0.0

    def lista(self, chave: str, fl: str) -> list[dict]:
        return [r for r in self.d[chave][fl] if r["fob"] > 0 or r["fob_ant"] > 0]

    def url_prod(self, cod: str) -> str:
        return self.prod[cod]["url"] if cod in self.prod else ""

    def url_nome(self, tipo: str, nome: str) -> str:
        idx = self.pais if tipo == "pais" else self.uf
        it = idx.get(slug(nome))
        return it["url"] if it else ""

    def cruz(self, chave, fl, filtro_cod=None, filtro_nome=None):
        out = []
        for c, n, a, b in self.cz.get((chave, fl), []):
            if filtro_cod is not None and c != filtro_cod:
                continue
            if filtro_nome is not None and n != filtro_nome:
                continue
            if a > 0:  # nas listas de "quem compra/vende" só entra quem teve comércio no mês
                out.append({"codigo": c, "nome": n, "fob": a, "fob_ant": b})
        out.sort(key=lambda r: -r["fob"])
        return out


# ---------------------------------------------------------------- componentes
def tile(cls, lbl, val, unid, chg, href=None):
    tag, h = ("a", f' href="{href}"') if href else ("div", "")
    seta = " →" if href else ""
    u = f" <small>{unid}</small>" if unid else ""
    return f'<{tag} class="tile {cls}"{h}><span class="lbl">{lbl}{seta}</span><span class="val">{val}{u}</span>{chg}</{tag}>'


def hbars(rows, cor):
    if not rows:
        return ""
    mx = max(r["fob"] for r in rows) or 1
    out = []
    for r in rows:
        out.append(
            f'<div class="hbar"><span class="t">{esc(corta(r.get("curto") or r["nome"], 60))}</span>'
            f'<span class="v">{us(r["fob"])}</span><span class="track"><span style="width:{r["fob"] / mx * 100:.1f}%;background:{cor}"></span></span>'
            f'<span class="meta">{chip(r["fob"], r["fob_ant"])}<span>antes: {us(r["fob_ant"])}</span></span></div>')
    return '<div class="hbars">' + "".join(out) + "</div>"


def tabela(B, rows, tipo, total, modo="valor"):
    """tipo: produto | pais | estado. modo: valor | dif."""
    if not rows:
        return '<p class="small">Sem dados para este recorte.</p>'
    cab = {"produto": "Produto", "pais": "País", "estado": "Estado"}[tipo]
    mes = cap(mes_curto(B.ref))
    h = [f'<div class="scroll"><table><thead><tr><th></th><th>{cab}</th><th class="r">{mes}</th>'
         f'<th class="r">{"Var." if modo == "valor" else "Diferença"}</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        if tipo == "produto":
            p = B.prod.get(r["codigo"], {})
            nome = p.get("curto") or r.get("curto") or r["nome"]
            url = B.url_prod(r["codigo"])
            pre = f"SH4 {esc(r['codigo'])} · "
        else:
            nome = r["nome"]
            url = B.url_nome(tipo, r["nome"])
            pre = ""
        if modo == "valor":
            sub = f"{nf(r['fob'] / total * 100, 1)}% do total" if total else ""
            col = chip(r["fob"], r["fob_ant"])
        else:
            sub = f"{chip(r['fob'], r['fob_ant'])} · antes {us(r['fob_ant'])}"
            d = r["fob"] - r["fob_ant"]
            col = f'<span class="chg {"up" if d >= 0 else "down"}">{"+" if d >= 0 else ""}{us_sem(d)}</span>'
        link = f'<a href="{url}">{esc(corta(nome))}</a>' if url else esc(corta(nome))
        h.append(f'<tr><td class="n">{i}</td><td>{link}<span class="s">{pre}{sub}</span></td>'
                 f'<td class="r">{us(r["fob"])}</td><td class="r">{col}</td></tr>')
    h.append("</tbody></table></div>")
    return "".join(h)


def altas(rows, minimo=1e7):
    r = [x for x in rows if max(x["fob"], x["fob_ant"]) >= minimo and x["fob"] > x["fob_ant"]]
    return sorted(r, key=lambda x: -(x["fob"] - x["fob_ant"]))


def quedas(rows, minimo=1e7):
    r = [x for x in rows if max(x["fob"], x["fob_ant"]) >= minimo and x["fob"] < x["fob_ant"]]
    return sorted(r, key=lambda x: (x["fob"] - x["fob_ant"]))


def svg_mensal(B) -> str:
    ano, mes = int(B.ref[:4]), int(B.ref[5:])
    meses = []
    for i in range(12, -1, -1):
        y, m = ano, mes - i
        while m <= 0:
            m += 12
            y -= 1
        meses.append(f"{y}-{m:02d}")
    rows = [(k, B.tot("export", k), B.tot("import", k)) for k in meses]
    mx = max(max(r[1], r[2]) for r in rows) / 1e9
    top = max(10, int(-(-mx // 10) * 10))
    W, H, L, R, T, Bm = 420, 250, 24, 4, 16, 52
    ih, iw = H - T - Bm, W - L - R
    step = iw / len(rows)
    bw = step * 0.34
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="max-width:680px">']
    for g in range(0, top + 1, 10):
        y = T + ih - g / top * ih
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--line)"/>'
                 f'<text x="{L - 4}" y="{y + 3.5:.1f}" text-anchor="end" font-size="9">{g}</text>')
    for i, (k, e, im) in enumerate(rows):
        x0 = L + i * step + step / 2
        hi = i in (0, len(rows) - 1)
        op = 1 if hi else 0.6
        for v, cor, dx, nome in ((e, "var(--exp)", -bw - 0.6, "exportação"), (im, "var(--imp)", 0.6, "importação")):
            h_ = v / 1e9 / top * ih
            o.append(f'<rect x="{x0 + dx:.1f}" y="{T + ih - h_:.1f}" width="{bw:.1f}" height="{h_:.1f}" rx="1.5" fill="{cor}" opacity="{op}">'
                     f'<title>{mes_curto(k)}: {nome} {us(v)}</title></rect>')
        estilo = ' style="fill:var(--ink);font-weight:600"' if hi else ""
        o.append(f'<text x="{x0:.1f}" y="{T + ih + 13}" text-anchor="middle" font-size="9"{estilo}>{MES_CURTO[int(k[5:]) - 1]}</text>')
        sd = (e - im) / 1e9
        estilo = ' style="fill:var(--ink);font-weight:700"' if hi else ""
        o.append(f'<text x="{x0:.1f}" y="{T + ih + 33}" text-anchor="middle" font-size="8.5"{estilo}>{nf(sd, 1)}</text>')
    o.append(f'<text x="1" y="{T + ih + 33}" font-size="8.5">saldo</text></svg>')
    return "".join(o)


def svg_par(B, E0, E, I0, I) -> str:
    W, H, T, Bm = 360, 190, 22, 26
    ih = H - T - Bm
    mx = max(E0, E, I0, I) or 1
    bw = 44
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="max-width:560px">']
    for j, (rot, vals) in enumerate(((mes_curto(B.ant), (E0, I0)), (mes_curto(B.ref), (E, I)))):
        x0 = W / 4 + j * W / 2
        for i, (v, cor) in enumerate(zip(vals, ("var(--exp)", "var(--imp)"))):
            x = x0 - bw - 2 + i * (bw + 4)
            h_ = max(v / mx * ih, 0.5)
            o.append(f'<rect x="{x:.1f}" y="{T + ih - h_:.1f}" width="{bw}" height="{h_:.1f}" rx="2" fill="{cor}" opacity="{1 if j else 0.55}"/>'
                     f'<text x="{x + bw / 2:.1f}" y="{T + ih - h_ - 5:.1f}" text-anchor="middle" font-size="10" style="fill:var(--ink);font-weight:600">{us_sem(v)}</text>')
        o.append(f'<text x="{x0:.1f}" y="{T + ih + 17}" text-anchor="middle" font-size="10.5">{rot}</text>')
    o.append(f'<line x1="6" x2="{W - 6}" y1="{T + ih}" y2="{T + ih}" stroke="var(--line)"/></svg>')
    return "".join(o)


def passo_bonito(mx: float) -> float:
    if mx <= 0:
        return 1
    bruto = mx / 4
    p10 = 10 ** int(f"{bruto:e}".split("e")[1])
    for f in (1, 2, 2.5, 5, 10):
        if bruto <= f * p10:
            return f * p10
    return 10 * p10


def rot_eixo(v: float) -> str:
    if v >= 1e9:
        return nf(v / 1e9, 1 if v % 1e9 else 0) + " bi"
    if v >= 1e6:
        return nf(v / 1e6, 0) + " mi"
    if v >= 1e3:
        return nf(v / 1e3, 0) + " mil"
    return nf(v, 0)


def svg_serie(B, ev, iv) -> str:
    n = len(B.meses)
    if n < 2:
        return ""
    W, H, L, R, T, Bm = 360, 200, 40, 8, 12, 22
    iw, ih = W - L - R, H - T - Bm
    mx = max(max(ev), max(iv)) or 1
    st = passo_bonito(mx)
    top = st * (int(mx / st) + (0 if mx % st == 0 else 1))
    def x(i):
        return L + i / (n - 1) * iw
    def y(v):
        return T + ih - v / top * ih
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="max-width:720px">']
    g = 0.0
    while g <= top + 1e-6:
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="var(--line)"/>'
                 f'<text x="{L - 4}" y="{y(g) + 3.5:.1f}" text-anchor="end" font-size="10">{rot_eixo(g)}</text>')
        g += st
    for i, m in enumerate(B.meses):
        if m.endswith("-01") and int(m[:4]) % 2 == 1:
            o.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{T + ih}" y2="{T + ih + 3}" stroke="var(--muted)"/>'
                     f'<text x="{x(i):.1f}" y="{T + ih + 15}" text-anchor="middle" font-size="10">{m[:4]}</text>')
    for vals, cor in ((iv, "var(--imp)"), (ev, "var(--exp)")):
        if not any(vals):
            continue
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{cor}" stroke-width="1.5" stroke-linejoin="round"/>'
                 f'<circle cx="{x(n - 1):.1f}" cy="{y(vals[-1]):.1f}" r="2.6" fill="{cor}"/>')
    o.append("</svg>")
    return "".join(o)


def svg_13(B, ev, iv) -> str:
    """Barras dos últimos 13 meses (exportação e importação), com o mês atual e o
    mesmo mês do ano anterior em destaque."""
    n = min(13, len(B.meses))
    if n < 2:
        return ""
    meses, e13, i13 = B.meses[-n:], ev[-n:], iv[-n:]
    W, H, L, R, T, Bm = 360, 210, 40, 6, 20, 22
    iw, ih = W - L - R, H - T - Bm
    mx = max(max(e13), max(i13)) or 1
    st = passo_bonito(mx)
    top = st * (int(mx / st) + (0 if mx % st == 0 else 1))
    step = iw / n
    bw = step * 0.36
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="max-width:640px">']
    g = 0.0
    while g <= top + 1e-6:
        y = T + ih - g / top * ih
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--line)"/>'
                 f'<text x="{L - 4}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10">{rot_eixo(g)}</text>')
        g += st
    tem_e = any(e13)
    for k, (m, e, i) in enumerate(zip(meses, e13, i13)):
        x0 = L + k * step + step / 2
        hi = k in (0, n - 1)
        op = 1 if hi else 0.55
        for v, cor, dx, nome in ((e, "var(--exp)", -bw - 0.5, "exportação"), (i, "var(--imp)", 0.5, "importação")):
            h_ = v / top * ih
            o.append(f'<rect x="{x0 + dx:.1f}" y="{T + ih - h_:.1f}" width="{bw:.1f}" height="{max(h_, 0):.1f}" rx="1.5" fill="{cor}" opacity="{op}">'
                     f'<title>{mes_curto(m)}: {nome} {us(v)}</title></rect>')
        if hi:
            v = e if tem_e else i
            h_ = v / top * ih
            xr = x0 - bw / 2 - 0.5 if tem_e else x0 + bw / 2 + 0.5
            anc = "start" if k == 0 else "end"
            xr = max(xr - 6, L) if k == 0 else min(xr + 6, W - R)
            o.append(f'<text x="{xr:.1f}" y="{T + ih - h_ - 5:.1f}" text-anchor="{anc}" font-size="10" style="fill:var(--ink);font-weight:700">{us_sem(v)}</text>')
        estilo = ' style="fill:var(--ink);font-weight:700"' if hi else ""
        o.append(f'<text x="{x0:.1f}" y="{T + ih + 14}" text-anchor="middle" font-size="9.5"{estilo}>{MES_CURTO[int(m[5:]) - 1]}</text>')
    o.append("</svg>")
    return "".join(o)


def bloco_13(B, ev, iv, E0, E, I0, I, extra="") -> str:
    """Cartão com os últimos 13 meses; sem série, cai no comparativo de dois meses."""
    if any(ev[-13:]) or any(iv[-13:]):
        graf = svg_13(B, ev, iv)
        tit = "Últimos 13 meses"
        nota = (f'<p class="src">US$ FOB por mês. Em destaque, {mes_nome(B.ant)} e {mes_nome(B.ref)}; '
                f'o número em cima é o valor {"exportado" if any(ev[-13:]) else "importado"}.</p>')
    else:
        graf = svg_par(B, E0, E, I0, I)
        tit = f"{cap(mes_nome(B.ref))} contra {mes_nome(B.ant)}"
        nota = ""
    return (f'<div class="card chart"><div class="row-head"><h2>{tit}</h2>{LEGENDA}</div>'
            f'<div role="img" aria-label="Exportações e importações mês a mês">{graf}</div>{nota}{extra}</div>')


def toneladas(kg: float) -> str:
    t = kg / 1000
    if t >= 1e6:
        return f"{nf(t / 1e6, 1)} milhões de toneladas"
    if t >= 1e3:
        return f"{nf(t / 1e3, 1)} mil toneladas"
    return f"{nf(t, 0)} toneladas"


def por_ano(B, vals):
    """{ano: soma} e o último mês disponível do ano corrente."""
    out = {}
    for m, v in zip(B.meses, vals):
        out[int(m[:4])] = out.get(int(m[:4]), 0) + v
    return out


def ytd(B, vals, ano):
    mr = int(B.ref[5:])
    return sum(v for m, v in zip(B.meses, vals) if int(m[:4]) == ano and int(m[5:]) <= mr)


def tabela_anual(B, ev, iv, ek=None, saldo=False) -> str:
    ar = int(B.ref[:4])
    mr = int(B.ref[5:])
    pe, pi = por_ano(B, ev), por_ano(B, iv)
    linhas = []
    for ano in range(ar, 2014, -1):
        e, i = pe.get(ano, 0), pi.get(ano, 0)
        if ano == ar and mr < 12:
            e0, i0 = ytd(B, ev, ano - 1), ytd(B, iv, ano - 1)
            rot = f"{ano}*"
        else:
            e0, i0 = pe.get(ano - 1, 0), pi.get(ano - 1, 0)
            rot = str(ano)
        ce = chip(e, e0) if ano > 2015 else ""
        ci = chip(i, i0) if ano > 2015 else ""
        if saldo:
            linhas.append(f'<tr><td>{rot}</td><td class="r">{us_sem(e)}</td><td class="r">{us_sem(i)}</td><td class="r">{us_sem(e - i)}</td></tr>')
        else:
            linhas.append(f'<tr><td>{rot}</td><td class="r">{us_sem(e)}<span class="s">{ce}</span></td><td class="r">{us_sem(i)}<span class="s">{ci}</span></td></tr>')
    if saldo:
        cab = '<th>Ano</th><th class="r">Exportação</th><th class="r">Importação</th><th class="r">Saldo</th>'
    else:
        cab = '<th>Ano</th><th class="r">Exportação</th><th class="r">Importação</th>'
    nota = (f'<p class="src">Valores em US$. * {ar}: janeiro a {MESES[mr - 1]}, comparado com o mesmo período de {ar - 1}.</p>'
            if mr < 12 else '<p class="src">Valores em US$.</p>')
    t = f'<div class="scroll"><table><thead><tr>{cab}</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>{nota}'
    if ek and any(ek):
        pk = por_ano(B, ek)
        lv = []
        for ano in range(ar, 2014, -1):
            kg, val = pk.get(ano, 0), pe.get(ano, 0)
            if not kg:
                continue
            lv.append(f'<tr><td>{ano}{"*" if ano == ar and mr < 12 else ""}</td><td class="r">{nf(kg / 1e6, 1)}</td><td class="r">{nf(val / kg * 1000, 0)}</td></tr>')
        if lv:
            t += ('<h3>Volume e preço médio exportados</h3><div class="scroll"><table><thead><tr><th>Ano</th>'
                  '<th class="r">Mil toneladas</th><th class="r">US$ por tonelada</th></tr></thead><tbody>' + "".join(lv) + "</tbody></table></div>")
    return t


def destaque_serie(B, vals, rotulo) -> str:
    """Frase com o melhor ano completo e o acumulado do ano."""
    ar = int(B.ref[:4])
    pa = por_ano(B, vals)
    completos = {a: v for a, v in pa.items() if a < ar and v > 0}
    if not completos:
        return ""
    melhor = max(completos, key=completos.get)
    atual, ant = ytd(B, vals, ar), ytd(B, vals, ar - 1)
    txt = f"Desde 2015, o melhor ano {rotulo} foi {melhor}, com {us(completos[melhor])}."
    if ytd(B, vals, ar) > completos[melhor]:
        txt += f" Em {ar}, até {MESES[int(B.ref[5:]) - 1]}, o valor já soma {us(ytd(B, vals, ar))}: um novo recorde, com meses ainda por vir."
        return txt
    if ant:
        p = pct(atual, ant)
        txt += (f" Em {ar}, até {MESES[int(B.ref[5:]) - 1]}, o valor soma {us(atual)}, "
                f"{nf(abs(p), 1)}% {'acima' if p >= 0 else 'abaixo'} do mesmo período de {ar - 1}.")
    return txt


def bloco_serie(B, ev, iv, ek=None, rotulo="das exportações") -> str:
    if not (any(ev) or any(iv)):
        return ""
    principal = ev if any(ev) else iv
    rot = rotulo if any(ev) else rotulo.replace("exportações", "importações")
    frase = destaque_serie(B, principal, rot)
    return (f'<div class="card chart"><div class="row-head"><h2>Mês a mês desde 2015</h2>{LEGENDA}</div>'
            + (f'<p>{frase}</p>' if frase else "")
            + f'<div role="img" aria-label="Série mensal de exportações e importações desde 2015">{svg_serie(B, ev, iv)}</div>'
            + f'<p class="src">Valores mensais em US$ FOB. Último ponto: {mes_nome(B.ref)}.</p></div>'
            + f'<div class="card"><h2>Ano a ano</h2>{tabela_anual(B, ev, iv, ek)}</div>')


LEGENDA = ('<div class="legend"><span><i style="background:var(--exp)"></i>Exportação</span>'
           '<span><i style="background:var(--imp)"></i>Importação</span></div>')

NAV = [("/", "Início"), ("/exportacao/", "Exportação"), ("/importacao/", "Importação"),
       ("/produtos/", "Produtos"), ("/paises/", "Países"), ("/estados/", "Estados"), ("/sobre/", "Como funciona")]


def pagina(B, caminho, titulo, descricao, corpo, ativo="", jsonld=None, migalhas=None, imagem=None) -> str:
    url = BASE + caminho
    nav = "".join(f'<a href="{h}"' + (' aria-current="page"' if h == ativo else "") + f">{t}</a>" for h, t in NAV)
    bc = ""
    if migalhas:
        partes = ['<a href="/">Início</a>'] + [f'<a href="{h}">{esc(t)}</a>' if h else esc(t) for h, t in migalhas]
        bc = '<nav class="bc" aria-label="Você está em">' + " › ".join(partes) + "</nav>"
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    gerado = dt.datetime.fromisoformat(B.d["gerado_em"]).strftime("%d/%m/%Y")
    v = B.d["gerado_em"][:10]
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titulo)}</title>
<meta name="description" content="{esc(descricao)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Comex em Números">
<meta property="og:title" content="{esc(titulo)}">
<meta property="og:description" content="{esc(descricao)}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="pt_BR">
<meta property="og:image" content="{imagem or BASE + "/assets/og.png"}">
<link rel="alternate" type="application/rss+xml" title="Comex em Números: resumo do mês" href="{BASE}/feed.xml">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0b7a68">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/estilo.css?v={v}">
{ld}
</head>
<body>
<header class="top"><div class="top-in">
<a class="brand" href="/" aria-label="Comex em Números, início"><svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true"><rect x="1" y="1" width="26" height="26" rx="6" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".35"/><rect x="6" y="13" width="4" height="9" rx="1" fill="var(--exp)"/><rect x="12" y="8" width="4" height="14" rx="1" fill="var(--exp)"/><rect x="18" y="11" width="4" height="11" rx="1" fill="var(--imp)"/></svg><b>Comex <span>em Números</span></b></a>
<nav class="main" aria-label="Seções">{nav}</nav>
</div></header>
<div class="info-bar"><div><strong>Dados de {mes_nome(B.ref)}.</strong> Fonte: Comex Stat (Secex/MDIC), atualizado automaticamente em {gerado}.</div></div>
<main>
{bc}
{corpo}
</main>
<footer><div>
<span><strong>Comex em Números</strong> · versão beta</span>
<span>Fonte: Comex Stat, Secex/MDIC. Valores em US$ FOB. Variações sempre contra o mesmo mês do ano anterior ({mes_nome(B.ant)}). Por estado, vale a UF de origem do produto exportado ou de destino do importado.</span>
<span><a href="/resumo/">Resumos mensais</a> · <a href="/produtos/">Todos os produtos</a> · <a href="/paises/">Países</a> · <a href="/estados/">Estados</a> · <a href="/sobre/">Como funciona</a></span>
</div>{familia_html()}</footer>
<script src="/assets/app.js?v={v}" defer></script>
{GOAT}
</body>
</html>
"""


def resumo_fluxo(B, fl: str) -> str:
    tot, tot0 = B.tot(fl, B.ref), B.tot(fl, B.ant)
    dif = tot - tot0
    ps = B.lista("produtos", fl)
    a, q = altas(ps), quedas(ps)
    verbo = "exportou" if fl == "export" else "importou"
    p = pct(tot, tot0) or 0
    txt = (f'O Brasil {verbo} <strong class="num">{us(tot)}</strong> em {mes_nome(B.ref)}, '
           f'{"alta" if p >= 0 else "queda"} de <strong>{nf(abs(p), 1)}%</strong> sobre {MESES[int(B.ant[5:]) - 1]} do ano passado.')
    lider = (a or [None])[0] if dif >= 0 else (q or [None])[0]
    if lider and dif:
        c = lider["fob"] - lider["fob_ant"]
        share = abs(c / dif * 100)
        nome = esc(minusc(corta(lider["curto"], 60)))
        extra = f", {nf(share, 0)}% da variação total" if share <= 150 else ""
        txt += (f' {"O maior impulso veio de" if dif >= 0 else "A maior queda veio de"} '
                f'<a href="{B.url_prod(lider["codigo"])}"><strong>{nome}</strong></a> ({"+" if c >= 0 else ""}{us(c)}{extra}).')
    contra = (q or [None])[0] if dif >= 0 else (a or [None])[0]
    if contra:
        c = contra["fob"] - contra["fob_ant"]
        txt += (f' No sentido contrário, {"caiu" if dif >= 0 else "subiu"} '
                f'<a href="{B.url_prod(contra["codigo"])}">{esc(minusc(corta(contra["curto"], 60)))}</a> ({"+" if c >= 0 else ""}{us(c)}).')
    return txt


# ---------------------------------------------------------------- páginas
def pg_inicio(B) -> str:
    E, E0, I, I0 = B.tot("export", B.ref), B.tot("export", B.ant), B.tot("import", B.ref), B.tot("import", B.ant)
    s, s0 = E - I, E0 - I0
    pE = pct(E, E0) or 0
    mes = MESES[int(B.ref[5:]) - 1]
    titulo_h = (f'Exportações {"sobem" if pE >= 0 else "caem"} {nf(abs(pE), 1)}% em {mes} e '
                + (f"saldo chega a {us(s)}" if s >= 0 else f"balança fica negativa em {us(-s)}"))
    acE, acI = B.d["acumulado"]["export"], B.d["acumulado"]["import"]
    ps = B.lista("produtos", "export")
    tev, tiv = B.serie_total("export"), B.serie_total("import")
    serie_brasil = ""
    if sum(1 for v in tev if v) > 24:
        frase = destaque_serie(B, tev, "das exportações brasileiras")
        serie_brasil = (f'<div class="two"><div class="card chart"><div class="row-head"><h2>Balança desde 2015</h2>{LEGENDA}</div>'
                        + (f"<p>{frase}</p>" if frase else "")
                        + f'<div role="img" aria-label="Exportações e importações mensais do Brasil desde 2015">{svg_serie(B, tev, tiv)}</div></div>'
                        + f'<div class="card"><h2>Ano a ano</h2>{tabela_anual(B, tev, tiv, saldo=True)}</div></div>')
    saldo_chip = chip(s, s0) if s0 > 0 else f'<span class="chg flat">antes {nf(s0 / 1e9, 2)}</span>'
    ac_chip = chip(acE["fob"] - acI["fob"], acE["fob_ant"] - acI["fob_ant"]) if acE["fob_ant"] > acI["fob_ant"] else ""
    c = f"""<div class="card"><span class="eyebrow">Balança comercial · {mes_nome(B.ref)}</span><h1>{esc(titulo_h)}</h1>
<p class="lede">{resumo_fluxo(B, "export")}</p>
<p class="lede">Nas importações, o país comprou <strong class="num">{us(I)}</strong>{var_par(I, I0)}. O saldo do mês foi de <strong class="num">{us(s)}</strong>, contra {us(s0)} um ano antes.</p>
<p class="src">Resumo gerado automaticamente com os dados oficiais do Comex Stat. <a href="/resumo/{B.ref}/">Ler o resumo completo de {MESES[int(B.ref[5:]) - 1]} →</a></p></div>
<div class="tiles">{tile("exp", "Exportações", nf(E / 1e9, 2), "US$ bi", chip(E, E0), "/exportacao/")}{tile("imp", "Importações", nf(I / 1e9, 2), "US$ bi", chip(I, I0), "/importacao/")}{tile("bal", "Saldo", nf(s / 1e9, 2), "US$ bi", saldo_chip)}{tile("", "Corrente de comércio", nf((E + I) / 1e9, 2), "US$ bi", chip(E + I, E0 + I0))}</div>
<div class="two"><div class="card chart"><div class="row-head"><h2>Últimos 13 meses</h2>{LEGENDA}</div><div role="img" aria-label="Exportações e importações mensais do Brasil nos últimos 13 meses">{svg_mensal(B)}</div><p class="src">US$ bilhões FOB. Linha de baixo: saldo do mês. Em destaque, o mês atual e o mesmo mês do ano anterior.</p></div>
<div class="card"><h2>Acumulado no ano</h2><table><thead><tr><th>Jan–{MES_CURTO[int(B.ref[5:]) - 1]}/{B.ref[:4]}</th><th class="r">US$ bi</th><th class="r">vs {B.ant[:4]}</th></tr></thead><tbody>
<tr><td>Exportações</td><td class="r">{nf(acE["fob"] / 1e9, 2)}</td><td class="r">{chip(acE["fob"], acE["fob_ant"])}</td></tr>
<tr><td>Importações</td><td class="r">{nf(acI["fob"] / 1e9, 2)}</td><td class="r">{chip(acI["fob"], acI["fob_ant"])}</td></tr>
<tr><td><strong>Saldo</strong></td><td class="r"><strong>{nf((acE["fob"] - acI["fob"]) / 1e9, 2)}</strong></td><td class="r">{ac_chip}</td></tr></tbody></table></div></div>
{serie_brasil}
<div class="two"><div class="card"><div class="row-head"><h2>O que mais puxou as exportações</h2><a class="small" href="/exportacao/">Ver todos →</a></div><p class="small">Maiores aumentos em US$ contra {mes_nome(B.ant)}.</p>{tabela(B, altas(ps, 2e7)[:5], "produto", E, "dif")}</div>
<div class="card"><h2>Exportações por setor</h2>{hbars([r for r in B.d["setores"]["export"] if r["fob"] > 0], "var(--exp)")}</div></div>
<div class="two"><div class="card"><div class="row-head"><h2>Principais destinos</h2><a class="small" href="/paises/">Todos os países →</a></div>{tabela(B, B.lista("paises", "export")[:6], "pais", E)}</div>
<div class="card"><div class="row-head"><h2>Estados que mais exportam</h2><a class="small" href="/estados/">Todos →</a></div>{tabela(B, [r for r in B.lista("estados", "export") if r["nome"] != "UF não declarada"][:6], "estado", E)}</div></div>
<div class="card"><h3>Jornalista? Use este gráfico na sua matéria</h3><p class="small">Cole o código na sua página. O gráfico se atualiza sozinho todo mês e traz o crédito para o Comex em Números.</p>
<code class="embed" id="embed-code">&lt;iframe src="{BASE}/embed/balanca-mensal/"
  width="100%" height="360" frameborder="0" loading="lazy"&gt;&lt;/iframe&gt;</code>
<button type="button" class="btn ghost" id="copy-embed">Copiar código</button><span class="msg" id="copy-msg" aria-live="polite"></span>
<p class="small"><a href="/embed/balanca-mensal/">Ver como fica o gráfico →</a></p></div>"""
    desc = desc_corta(f"Balança comercial do Brasil em {mes_nome(B.ref)}: exportações de {us(E)}{var_par(E, E0)}, "
                      f"importações de {us(I)}{var_par(I, I0)} e saldo de {us(s)}. Por produto, país e estado.")
    ld = {"@context": "https://schema.org", "@type": "WebSite", "name": "Comex em Números", "url": BASE + "/",
          "inLanguage": "pt-BR", "description": "Exportações e importações do Brasil por produto, país e estado."}
    return pagina(B, "/", f"Balança comercial do Brasil em {mes_nome(B.ref)} | Comex em Números", desc, c, "/", ld)


def pg_fluxo(B, fl: str) -> str:
    tot, tot0 = B.tot(fl, B.ref), B.tot(fl, B.ant)
    ps = B.lista("produtos", fl)
    cor, cls = ("var(--exp)", "exp") if fl == "export" else ("var(--imp)", "imp")
    grupos = [r for r in (B.d["setores"][fl] if fl == "export" else B.d["categorias"][fl]) if r["fob"] > 0]
    mes = MESES[int(B.ref[5:]) - 1]
    nomefl = "Exportação" if fl == "export" else "Importação"
    tiles = tile(cls, f'Total {"exportado" if fl == "export" else "importado"}', nf(tot / 1e9, 2), "US$ bi", chip(tot, tot0))
    tiles += "".join(tile("", esc(corta(r["nome"], 34)), nf(r["fob"] / 1e9, 2), "US$ bi", chip(r["fob"], r["fob_ant"])) for r in grupos[:3])
    c = f"""<div class="card"><span class="eyebrow">{nomefl} · {mes_nome(B.ref)}</span><h1>{"O que o Brasil vendeu" if fl == "export" else "O que o Brasil comprou"} em {mes}</h1><p class="lede">{resumo_fluxo(B, fl)}</p></div>
<div class="tiles">{tiles}</div>
<div class="card tabgroup" data-tabs><div class="row-head"><h2>Produtos</h2><div class="seg" role="group" aria-label="Ordenar produtos">
<button type="button" data-t="valor" aria-pressed="true">Maior valor</button><button type="button" data-t="altas" aria-pressed="false">Maiores altas</button><button type="button" data-t="quedas" aria-pressed="false">Maiores quedas</button></div></div>
<div data-p="valor"><p class="small">Os 20 produtos de maior valor no mês (classificação SH4).</p>{tabela(B, ps[:20], "produto", tot)}</div>
<div data-p="altas" hidden><p class="small">Maiores aumentos em US$ contra {mes_nome(B.ant)} (produtos acima de US$ 10 mi).</p>{tabela(B, altas(ps)[:20], "produto", tot, "dif")}</div>
<div data-p="quedas" hidden><p class="small">Maiores quedas em US$ contra {mes_nome(B.ant)} (produtos acima de US$ 10 mi).</p>{tabela(B, quedas(ps)[:20], "produto", tot, "dif")}</div>
<div class="search"><label for="busca" class="small" style="align-self:center">Buscar</label><input id="busca" type="search" placeholder="Ex.: café, soja, aço, medicamentos" autocomplete="off"></div><div id="busca-res" aria-live="polite"></div>
<p class="small"><a href="/produtos/">Ver a lista completa de produtos →</a></p></div>
<div class="two"><div class="card"><h2>{"Por setor" if fl == "export" else "Por tipo de bem"}</h2>{hbars(grupos, cor)}</div>
<div class="card"><div class="row-head"><h2>{"Principais destinos" if fl == "export" else "Principais origens"}</h2><a class="small" href="/paises/">Todos →</a></div>{tabela(B, B.lista("paises", fl)[:8], "pais", tot)}</div></div>
<div class="card"><div class="row-head"><h2>{"Estados que mais exportam" if fl == "export" else "Estados que mais importam"}</h2><a class="small" href="/estados/">Todos →</a></div>{tabela(B, [r for r in B.lista("estados", fl) if r["nome"] != "UF não declarada"][:8], "estado", tot)}</div>"""
    top3 = ", ".join(minusc(r["curto"]) for r in ps[:3])
    desc = desc_corta(f"{nomefl} do Brasil em {mes_nome(B.ref)}: {us(tot)}{var_par(tot, tot0)}. Ranking dos produtos, maiores altas e quedas. "
                      f"Destaques: {top3}.")
    caminho = "/exportacao/" if fl == "export" else "/importacao/"
    tit = f'{"Exportações" if fl == "export" else "Importações"} do Brasil por produto | Comex em Números'
    return pagina(B, caminho, tit, desc, c, caminho, migalhas=[(None, nomefl)])


def ativo_prod(p) -> bool:
    e, i = p.get("export") or {}, p.get("import") or {}
    return bool(e.get("fob") or i.get("fob") or e.get("fob_ant") or i.get("fob_ant"))


def pg_produtos(B) -> str:
    itens = sorted((p for p in B.prod.values() if ativo_prod(p)),
                   key=lambda p: -((p.get("export") or {}).get("fob", 0) + (p.get("import") or {}).get("fob", 0)))
    linhas = []
    for p in itens:
        e, i = p.get("export") or {}, p.get("import") or {}
        linhas.append(f'<tr><td><a href="{p["url"]}">{esc(corta(p["curto"]))}</a><span class="s">SH4 {p["codigo"]}</span></td>'
                      f'<td class="r">{us(e["fob"]) if e.get("fob") else "—"}</td><td class="r">{us(i["fob"]) if i.get("fob") else "—"}</td></tr>')
    c = f"""<div class="card"><span class="eyebrow">Produtos · {mes_nome(B.ref)}</span><h1>Todos os produtos do comércio exterior</h1>
<p class="lede">{nf(len(linhas), 0)} produtos (posições SH4) com exportação ou importação, do maior para o menor movimento no mês. Toque em um produto para ver valores, volume, preço médio, destinos e estados.</p>
<div class="search"><label for="busca" class="small" style="align-self:center">Buscar</label><input id="busca" type="search" placeholder="Ex.: café, soja, aço, medicamentos" autocomplete="off"></div><div id="busca-res" aria-live="polite"></div></div>
<div class="card"><div class="scroll"><table><thead><tr><th>Produto</th><th class="r">Exportação</th><th class="r">Importação</th></tr></thead><tbody>{"".join(linhas)}</tbody></table></div></div>"""
    desc = f"Lista completa dos {nf(len(linhas), 0)} produtos exportados e importados pelo Brasil em {mes_nome(B.ref)}, com valores em US$ e páginas de detalhe."
    return pagina(B, "/produtos/", "Todos os produtos exportados e importados pelo Brasil | Comex em Números", desc, c, "/produtos/",
                  migalhas=[(None, "Produtos")])


def pg_lista(B, tipo: str) -> str:
    chave = "paises" if tipo == "pais" else "estados"
    tit = "Países" if tipo == "pais" else "Estados"
    blocos = []
    for fl in ("export", "import"):
        tot = B.tot(fl, B.ref)
        h2 = ({"export": "Destinos das exportações", "import": "Origens das importações"} if tipo == "pais"
              else {"export": "Exportações por estado", "import": "Importações por estado"})[fl]
        blocos.append(f'<div class="card"><h2>{h2}</h2>{tabela(B, [r for r in B.lista(chave, fl) if r["fob"] > 0], tipo, tot)}</div>')
    texto = ("Para quem o Brasil vende e de quem compra. Toque em um país para ver o comércio bilateral e os produtos."
             if tipo == "pais" else "Quanto cada estado exporta e importa. Toque em um estado para ver os produtos. "
             "\"UF não declarada\" reúne as operações em que o estado de origem ou destino não foi informado à Receita.")
    c = f'<div class="card"><span class="eyebrow">{tit} · {mes_nome(B.ref)}</span><h1>{tit}</h1><p class="lede">{texto}</p></div><div class="cols">{"".join(blocos)}</div>'
    caminho = "/paises/" if tipo == "pais" else "/estados/"
    desc = (f"Exportações e importações do Brasil por país em {mes_nome(B.ref)}: principais destinos e origens, com variação anual."
            if tipo == "pais" else f"Exportações e importações por estado em {mes_nome(B.ref)}: ranking das UFs, com variação anual.")
    t = ("Comércio exterior do Brasil por país" if tipo == "pais" else "Exportações e importações por estado") + " | Comex em Números"
    return pagina(B, caminho, t, desc, c, caminho, migalhas=[(None, tit)])


def pg_produto(B, p: dict) -> str:
    e, i = p.get("export") or {}, p.get("import") or {}
    E, E0, I, I0 = e.get("fob", 0), e.get("fob_ant", 0), i.get("fob", 0), i.get("fob_ant", 0)
    nome, cod = p["curto"], p["codigo"]
    rank = None
    if E:
        rank = next((k for k, r in enumerate(B.lista("produtos", "export"), 1) if r["codigo"] == cod), None)
    frases = []
    if E:
        frases.append(f'O Brasil exportou <strong class="num">{us(E)}</strong> em {esc(minusc(nome))} em {mes_nome(B.ref)}'
                      + (f", {var_txt(E, E0)} sobre um ano antes" if E0 else "") + "."
                      + (f" É o {rank}º produto da pauta de exportação no mês." if rank else ""))
    elif E0:
        frases.append(f"O Brasil não exportou {esc(minusc(nome))} em {mes_nome(B.ref)}. Um ano antes, tinham sido {us(E0)}.")
    if I:
        frases.append(f'As importações somaram <strong class="num">{us(I)}</strong>{var_par(I, I0)}.' if E or E0 else
                      f'O Brasil importou <strong class="num">{us(I)}</strong> em {esc(minusc(nome))} em {mes_nome(B.ref)}{var_par(I, I0)}.')
    elif I0:
        frases.append(f"Não houve importação no mês (um ano antes: {us(I0)}).")
    ekg, ekg0 = e.get("kg", 0), e.get("kg_ant", 0)
    tiles = tile("exp", "Exportações", us_sem(E), "US$", chip(E, E0)) + tile("imp", "Importações", us_sem(I), "US$", chip(I, I0))
    tiles += tile("bal", "Saldo", us_sem(E - I), "US$", f'<span class="chg flat">antes {us_sem(E0 - I0)}</span>')
    if E and ekg > 0:
        pr, pr0 = E / ekg * 1000, (E0 / ekg0 * 1000 if ekg0 else 0)
        tiles += tile("", "Preço médio exportado", nf(pr, 0), "US$/t", chip(pr, pr0) if pr0 else '<span class="chg flat">—</span>')
    else:
        ikg, ikg0 = i.get("kg", 0), i.get("kg_ant", 0)
        pr = I / ikg * 1000 if ikg else 0
        pr0 = I0 / ikg0 * 1000 if ikg0 else 0
        tiles += tile("", "Preço médio importado", nf(pr, 0) if pr else "—", "US$/t" if pr else "", chip(pr, pr0) if pr and pr0 else '<span class="chg flat">—</span>')
    vol = ""
    if E and ekg and E0 and ekg0:
        qv, pv = pct(ekg, ekg0), pct(E / ekg, E0 / ekg0)
        vol = (f'<p class="small">Na exportação, a quantidade embarcada variou {"+" if qv >= 0 else "−"}{nf(abs(qv), 1)}% '
               f'({toneladas(ekg)} no mês) e o preço médio, {"+" if pv >= 0 else "−"}{nf(abs(pv), 1)}%.</p>')
    secoes = []
    dest = B.cruz("produto_pais", "export", filtro_cod=cod)
    orig = B.cruz("produto_pais", "import", filtro_cod=cod)
    ufe = [r for r in B.cruz("produto_estado", "export", filtro_cod=cod) if not nao_declarado(r["nome"])]
    ufi = [r for r in B.cruz("produto_estado", "import", filtro_cod=cod) if not nao_declarado(r["nome"])]
    def par_cards(a, b):
        cards = [x for x in (a, b) if x]
        if not cards:
            return ""
        return f'<div class="cols">{"".join(cards)}</div>' if len(cards) == 2 else cards[0]
    if E:
        secoes.append(par_cards(
            f'<div class="card"><h2>Para onde vai</h2><p class="small">Países que mais compraram {esc(minusc(nome))} do Brasil em {mes_nome(B.ref)}.</p>{tabela(B, dest[:10], "pais", E)}</div>' if dest else "",
            f'<div class="card"><h2>Estados que mais exportam</h2>{tabela(B, ufe[:10], "estado", E)}</div>' if ufe else ""))
    if I:
        secoes.append(par_cards(
            f'<div class="card"><h2>De onde vem</h2><p class="small">Países de onde o Brasil mais importou em {mes_nome(B.ref)}.</p>{tabela(B, orig[:10], "pais", I)}</div>' if orig else "",
            f'<div class="card"><h2>Estados que mais importam</h2>{tabela(B, ufi[:10], "estado", I)}</div>' if ufi else ""))
    oficial = f'<p class="oficial">Nome oficial (SH4 {esc(cod)}): {esc(p["nome"])}</p>' if p["nome"] != nome else ""
    sev, sek = B.serie_de("produtos", "export", cod)  # noqa: F841
    siv, _ = B.serie_de("produtos", "import", cod)
    serie_html = bloco_serie(B, sev, siv, sek, f"das exportações de {esc(minusc(nome))}")
    c = f"""<div class="card"><span class="eyebrow">Produto · SH4 {esc(cod)}</span><h1>{esc(nome)}</h1>{oficial}<p class="lede">{" ".join(frases)}</p></div>
<div class="tiles">{tiles}</div>
{bloco_13(B, sev, siv, E0, E, I0, I, vol)}
{"".join(secoes)}
{serie_html}"""
    t = f"{cap(nome)}: exportação e importação | Comex em Números"
    if len(t) > 70:
        t = f"{corta(cap(nome.split(' (SH4')[0]), 36)} (SH4 {cod}): exportação e importação"
    nome_d = minusc(nome.split(" (SH4")[0])
    if not E and not I:
        desc = (f"{cap(nome_d)}: sem comércio em {mes_curto(B.ref)}. Um ano antes, exportações de {us(E0)} e importações de {us(I0)}. "
                "Série mensal desde 2015.")
    elif E:
        desc = (f"O Brasil exportou {us(E)} em {nome_d} em {mes_curto(B.ref)}{var_par(E, E0)}. "
                "Destinos, estados, volume, preço e série desde 2015.")
    else:
        desc = (f"O Brasil importou {us(I)} em {nome_d} em {mes_curto(B.ref)}{var_par(I, I0)}. "
                "De onde vem, estados, preço e série desde 2015.")
    desc = desc_corta(desc)
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"Comércio exterior do Brasil: {nome} (SH4 {cod})",
          "description": desc, "url": BASE + p["url"], "inLanguage": "pt-BR", "temporalCoverage": f"{B.ant}/{B.ref}",
          "isAccessibleForFree": True, "creator": {"@type": "Organization", "name": "Comex em Números", "url": BASE + "/"},
          "isBasedOn": "https://comexstat.mdic.gov.br/"}
    return pagina(B, p["url"], t, desc, c, "/produtos/", ld, migalhas=[("/produtos/", "Produtos"), (None, corta(nome, 40))])


def pg_lugar(B, tipo: str, it: dict) -> str:
    e, i = it.get("export") or {}, it.get("import") or {}
    E, E0, I, I0 = e.get("fob", 0), e.get("fob_ant", 0), i.get("fob", 0), i.get("fob_ant", 0)
    nome = it["nome"]
    chave = "paises" if tipo == "pais" else "estados"
    rank = next((k for k, r in enumerate(B.lista(chave, "export"), 1) if r["nome"] == nome), None) if E else None
    EXP = B.tot("export", B.ref)
    if tipo == "pais":
        ap = art_pais(nome)
        para, de_p = com_artigo(nome, "para", ap), com_artigo(nome, "de", ap)
        frase = (f'Em {mes_nome(B.ref)}, o Brasil exportou <strong class="num">{us(E)}</strong> {esc(para)}{var_par(E, E0)} '
                 f'e importou <strong class="num">{us(I)}</strong>{var_par(I, I0)}. O saldo foi de <strong class="num">{us(E - I)}</strong>.')
        if rank:
            frase += f" É o {rank}º maior destino das exportações brasileiras, com {nf(E / EXP * 100, 1)}% do total."
        cz_e = B.cruz("produto_pais", "export", filtro_nome=nome)
        cz_i = B.cruz("produto_pais", "import", filtro_nome=nome)
        h_e, h_i = f"O que o Brasil vende {esc(para)}", f"O que o Brasil compra {esc(de_p)}"
        t = f"Comércio Brasil–{nome}: exportações e importações | Comex em Números"
        desc = desc_corta(f"Em {mes_curto(B.ref)}, o Brasil exportou {us(E)} {para}{var_par(E, E0)} e importou {us(I)}{var_par(I, I0)}. "
                          "Produtos, saldo e série desde 2015.")
        migalha = ("/paises/", "Países")
    else:
        art = ARTIGO_UF.get(nome, "")
        o_nome = f"{art} {nome}".strip()
        de = {"a": "da", "o": "do", "": "de"}[art]
        frase = (f'Em {mes_nome(B.ref)}, as exportações {de} {esc(nome)} somaram <strong class="num">{us(E)}</strong>{var_par(E, E0)} '
                 f'e as importações, <strong class="num">{us(I)}</strong>{var_par(I, I0)}. O saldo foi de <strong class="num">{us(E - I)}</strong>.')
        if rank:
            frase += f" É o {rank}º estado exportador do país, com {nf(E / EXP * 100, 1)}% do total."
        cz_e = B.cruz("produto_estado", "export", filtro_nome=nome)
        cz_i = B.cruz("produto_estado", "import", filtro_nome=nome)
        h_e, h_i = f"O que {esc(o_nome)} exporta", f"O que {esc(o_nome)} importa"
        t = f"O que {o_nome} exporta e importa | Comex em Números"
        desc = desc_corta(f"Exportações {de} {nome} em {mes_curto(B.ref)}: {us(E)}{var_par(E, E0)}. Importações: {us(I)}{var_par(I, I0)}. "
                          "Principais produtos e série desde 2015.")
        migalha = ("/estados/", "Estados")
    tiles = (tile("exp", "Exportações", us_sem(E), "US$", chip(E, E0)) + tile("imp", "Importações", us_sem(I), "US$", chip(I, I0))
             + tile("bal", "Saldo", us_sem(E - I), "US$", f'<span class="chg flat">antes {us_sem(E0 - I0)}</span>')
             + tile("", "Corrente de comércio", us_sem(E + I), "US$", chip(E + I, E0 + I0)))
    sev, _ = B.serie_de(chave, "export", nome)
    siv, _ = B.serie_de(chave, "import", nome)
    rot = f"das exportações {esc(para)}" if tipo == "pais" else f"das exportações {de} {esc(nome)}"
    serie_html = bloco_serie(B, sev, siv, None, rot)
    ce = (f'<div class="card"><h2>{h_e}</h2><p class="small">Principais produtos exportados em {mes_nome(B.ref)}.</p>{tabela(B, cz_e[:15], "produto", E)}</div>' if cz_e else "")
    ci = (f'<div class="card"><h2>{h_i}</h2><p class="small">Principais produtos importados em {mes_nome(B.ref)}.</p>{tabela(B, cz_i[:15], "produto", I)}</div>' if cz_i else "")
    secoes = f'<div class="cols">{ce}{ci}</div>' if ce and ci else (ce or ci)
    c = f"""<div class="card"><span class="eyebrow">{"País" if tipo == "pais" else "Estado"}</span><h1>{esc(nome)}</h1><p class="lede">{frase}</p></div>
<div class="tiles">{tiles}</div>
{bloco_13(B, sev, siv, E0, E, I0, I)}
{secoes}
{serie_html}"""
    return pagina(B, it["url"], t, desc, c, migalha[0], migalhas=[migalha, (None, nome)])


def titulo_mes(B) -> str:
    E, E0, I = B.tot("export", B.ref), B.tot("export", B.ant), B.tot("import", B.ref)
    s = E - I
    pE = pct(E, E0) or 0
    mes = MESES[int(B.ref[5:]) - 1]
    return (f'Exportações {"sobem" if pE >= 0 else "caem"} {nf(abs(pE), 1)}% em {mes} e '
            + (f"saldo chega a {us(s)}" if s >= 0 else f"balança fica negativa em {us(-s)}"))


def texto_post(B) -> str:
    """Texto pronto para o LinkedIn (vai no feed RSS e o Zapier publica)."""
    E, E0, I, I0 = B.tot("export", B.ref), B.tot("export", B.ant), B.tot("import", B.ref), B.tot("import", B.ant)
    ps = B.lista("produtos", "export")
    a, q = altas(ps, 2e7)[:3], quedas(ps, 2e7)[:2]
    dest = [r for r in B.lista("paises", "export") if r["fob"] > 0][:3]
    l = [f"Balança comercial de {mes_nome(B.ref)}", "",
         f"O Brasil exportou {us(E)}{var_par(E, E0)} e importou {us(I)}{var_par(I, I0)} na comparação com {mes_nome(B.ant)}. "
         f"Saldo de {us(E - I)}.", ""]
    if a:
        l.append("O que mais puxou as exportações:")
        l += [f"▲ {B.prod[r['codigo']]['curto']}: +{us(r['fob'] - r['fob_ant'])}" for r in a]
        l.append("")
    if q:
        l.append("Maiores quedas:")
        l += [f"▼ {B.prod[r['codigo']]['curto']}: {us(r['fob'] - r['fob_ant'])}" for r in q]
        l.append("")
    if dest:
        nomes = [f"{r['nome']} ({us(r['fob'])})" for r in dest]
        l += ["Principais destinos: " + ", ".join(nomes[:-1]) + f" e {nomes[-1]}.", ""]
    l += ["Ranking completo por produto, país e estado, com série desde 2015:", f"{BASE}/resumo/{B.ref}/", "",
          "#comercioexterior #exportacao #importacao #balancacomercial #comex"]
    return "\n".join(l)


def corpo_resumo(B, post: str) -> str:
    E, E0, I, I0 = B.tot("export", B.ref), B.tot("export", B.ant), B.tot("import", B.ref), B.tot("import", B.ant)
    s, s0 = E - I, E0 - I0
    pe, pi = B.lista("produtos", "export"), B.lista("produtos", "import")
    sem_nd = lambda rs: [r for r in rs if r["nome"] != "UF não declarada"]
    return f"""<div class="card"><span class="eyebrow">Resumo do mês · {mes_nome(B.ref)}</span><h1>{esc(titulo_mes(B))}</h1>
<img src="card.png" alt="Exportações, importações e saldo de {mes_nome(B.ref)}" width="1200" height="627" style="width:100%;height:auto;border-radius:8px;border:1px solid var(--line)">
<p class="lede">{resumo_fluxo(B, "export")}</p><p class="lede">{resumo_fluxo(B, "import")}</p></div>
<div class="tiles">{tile("exp", "Exportações", nf(E / 1e9, 2), "US$ bi", chip(E, E0), "/exportacao/")}{tile("imp", "Importações", nf(I / 1e9, 2), "US$ bi", chip(I, I0), "/importacao/")}{tile("bal", "Saldo", nf(s / 1e9, 2), "US$ bi", f'<span class="chg flat">antes {nf(s0 / 1e9, 2)}</span>')}{tile("", "Corrente de comércio", nf((E + I) / 1e9, 2), "US$ bi", chip(E + I, E0 + I0))}</div>
<div class="cols"><div class="card"><h2>Exportações que mais subiram</h2>{tabela(B, altas(pe, 2e7)[:5], "produto", E, "dif")}</div>
<div class="card"><h2>Exportações que mais caíram</h2>{tabela(B, quedas(pe, 2e7)[:5], "produto", E, "dif")}</div></div>
<div class="cols"><div class="card"><h2>Importações que mais subiram</h2>{tabela(B, altas(pi, 2e7)[:5], "produto", I, "dif")}</div>
<div class="card"><h2>Importações que mais caíram</h2>{tabela(B, quedas(pi, 2e7)[:5], "produto", I, "dif")}</div></div>
<div class="cols"><div class="card"><h2>Principais destinos</h2>{tabela(B, B.lista("paises", "export")[:5], "pais", E)}</div>
<div class="card"><h2>Estados que mais exportaram</h2>{tabela(B, sem_nd(B.lista("estados", "export"))[:5], "estado", E)}</div></div>
<div class="card"><h2>Compartilhe este resumo</h2><p class="small">Texto pronto para LinkedIn, WhatsApp ou e-mail.</p>
<textarea id="post" readonly rows="12" style="width:100%;font:inherit;font-size:.9rem;padding:10px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink)">{esc(post)}</textarea>
<button type="button" class="btn ghost" id="copy-post">Copiar texto</button><span class="msg" id="copy-post-msg" aria-live="polite"></span></div>"""


def salva_resumo(B) -> dict:
    RESUMOS.mkdir(parents=True, exist_ok=True)
    post = texto_post(B)
    E, E0, I = B.tot("export", B.ref), B.tot("export", B.ant), B.tot("import", B.ref)
    snap = {
        "mes": B.ref, "gerado_em": B.d["gerado_em"], "titulo": titulo_mes(B),
        "descricao": desc_corta(f"Resumo da balança comercial de {mes_nome(B.ref)}: exportações de {us(E)}{var_par(E, E0)}, "
                                f"importações de {us(I)} e saldo de {us(E - I)}. O que subiu, o que caiu e os principais destinos."),
        "post": post, "corpo": corpo_resumo(B, post),
    }
    arq = RESUMOS / f"{B.ref}.json"
    if arq.exists():  # mantém a data da primeira publicação do mês (o feed não repete o post)
        snap["gerado_em"] = json.loads(arq.read_text(encoding="utf-8")).get("gerado_em", snap["gerado_em"])
    arq.write_text(json.dumps(snap, ensure_ascii=False, indent=0), encoding="utf-8")
    if gera_card:
        ano, mes = int(B.ref[:4]), int(B.ref[5:])
        barras = []
        for i in range(12, -1, -1):
            y, m = ano, mes - i
            while m <= 0:
                m += 12
                y -= 1
            k = f"{y}-{m:02d}"
            barras.append((MES_CURTO[m - 1], B.tot("export", k), B.tot("import", k)))
        s, s0 = E - I, E0 - B.tot("import", B.ant)
        pE, pI = pct(E, E0) or 0, pct(I, B.tot("import", B.ant)) or 0
        gera_card(RESUMOS / f"{B.ref}.png", f"Balança comercial · {mes_nome(B.ref)}",
                  [("Exportações (US$)", f"{nf(E / 1e9, 2)} bi", f"{'▲' if pE >= 0 else '▼'} {nf(abs(pE), 1)}%", pE >= 0),
                   ("Importações (US$)", f"{nf(I / 1e9, 2)} bi", f"{'▲' if pI >= 0 else '▼'} {nf(abs(pI), 1)}%", pI >= 0),
                   ("Saldo (US$)", f"{nf(s / 1e9, 2)} bi", f"antes: {nf(s0 / 1e9, 2)} bi", None)],
                  barras, f"Fonte: Comex Stat (Secex/MDIC) · comexemnumeros.com.br/resumo/{B.ref}/")
    return snap


def pgs_resumos(B, urls) -> list[dict]:
    snaps = sorted((json.loads(f.read_text(encoding="utf-8")) for f in RESUMOS.glob("*.json")), key=lambda x: x["mes"], reverse=True)
    for sn in snaps:
        cam = f"/resumo/{sn['mes']}/"
        png = RESUMOS / f"{sn['mes']}.png"
        img = None
        if png.exists():
            (SAIDA / "resumo" / sn["mes"]).mkdir(parents=True, exist_ok=True)
            shutil.copy(png, SAIDA / "resumo" / sn["mes"] / "card.png")
            img = f"{BASE}{cam}card.png"
        corpo = sn["corpo"] if img else sn["corpo"].replace('<img src="card.png"', '<img hidden src="card.png"')
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": sn["titulo"], "inLanguage": "pt-BR",
              "datePublished": sn["gerado_em"], "author": {"@type": "Organization", "name": "Comex em Números", "url": BASE + "/"},
              "image": img or BASE + "/assets/og.png", "mainEntityOfPage": BASE + cam}
        escreve(cam, pagina(B, cam, f"{sn['titulo']} | Comex em Números", sn["descricao"], corpo, "/", ld,
                            migalhas=[("/resumo/", "Resumos mensais"), (None, mes_nome(sn["mes"]))], imagem=img), urls)
    itens = "".join(f'<li><a href="/resumo/{x["mes"]}/">{cap(mes_nome(x["mes"]))}</a>: {esc(x["titulo"])}</li>' for x in snaps)
    corpo = (f'<div class="card"><span class="eyebrow">Resumos mensais</span><h1>A balança comercial mês a mês</h1>'
             f'<p class="lede">Todo mês, quando o MDIC publica os dados, sai aqui um resumo com o que subiu, o que caiu e os principais destinos. '
             f'Também dá para seguir pelo <a href="/feed.xml">feed RSS</a>.</p><ul class="plain">{itens}</ul></div>')
    escreve("/resumo/", pagina(B, "/resumo/", "Resumos mensais da balança comercial | Comex em Números",
                               "Resumo mensal da balança comercial brasileira: exportações, importações, saldo, maiores altas e quedas.",
                               corpo, "/", migalhas=[(None, "Resumos mensais")]), urls)
    return snaps


def feed_rss(snaps) -> str:
    itens = []
    for sn in snaps[:12]:
        link = f"{BASE}/resumo/{sn['mes']}/"
        data = format_datetime(dt.datetime.fromisoformat(sn["gerado_em"]))
        png = RESUMOS / f"{sn['mes']}.png"
        enc = f'<enclosure url="{link}card.png" type="image/png" length="{png.stat().st_size}"/>' if png.exists() else ""
        itens.append(f"<item><title>{esc(sn['titulo'])}</title><link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
                     f"<pubDate>{data}</pubDate><description><![CDATA[{sn['post']}]]></description>{enc}</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            f'<title>Comex em Números: resumo do mês</title><link>{BASE}/</link>'
            '<description>Resumo mensal das exportações e importações do Brasil, com dados oficiais do Comex Stat.</description>'
            f'<language>pt-BR</language><atom:link href="{BASE}/feed.xml" rel="self" type="application/rss+xml"/>'
            + "".join(itens) + "</channel></rss>")


def pg_sobre(B) -> str:
    np_ = sum(1 for p in B.prod.values() if (p.get("export") or {}).get("fob"))
    ni = sum(1 for p in B.prod.values() if (p.get("import") or {}).get("fob"))
    c = f"""<div class="card"><span class="eyebrow">Como funciona</span><h1>O Comex Stat, sem precisar saber código NCM</h1>
<p class="lede">Os dados oficiais de comércio exterior do Brasil são públicos e gratuitos, mas difíceis de consultar. O Comex em Números busca cada atualização mensal do MDIC e transforma em páginas prontas, com nomes que as pessoas procuram.</p></div>
<div class="two"><div class="card"><h2>Neste mês</h2><table><tbody>
<tr><td>Produtos exportados (SH4)</td><td class="r">{nf(np_, 0)}</td></tr><tr><td>Produtos importados (SH4)</td><td class="r">{nf(ni, 0)}</td></tr>
<tr><td>Países parceiros</td><td class="r">{nf(len(B.pais), 0)}</td></tr><tr><td>Estados</td><td class="r">{len(B.uf)}</td></tr></tbody></table></div>
<div class="card"><h2>Fonte e método</h2><ul class="plain"><li>Fonte: API do Comex Stat, Secex/MDIC. Valores em US$ FOB.</li><li>Atualização automática no início de cada mês, quando o MDIC publica o mês anterior.</li><li>Variações sempre contra o mesmo mês do ano anterior.</li><li>Produtos na classificação SH4 (posição do Sistema Harmonizado). Os nomes curtos são nossos; o nome oficial aparece em cada página.</li><li>Estado: UF de origem do produto exportado e de destino do importado.</li></ul></div></div>"""
    return pagina(B, "/sobre/", "Como funciona | Comex em Números",
                  "Como o Comex em Números transforma os dados oficiais do Comex Stat (Secex/MDIC) em páginas por produto, país e estado.",
                  c, "/sobre/", migalhas=[(None, "Como funciona")])


def pg_embed(B) -> str:
    E, E0 = B.tot("export", B.ref), B.tot("export", B.ant)
    v = B.d["gerado_em"][:10]
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Balança comercial mensal | Comex em Números</title><meta name="robots" content="noindex">
<link rel="stylesheet" href="/assets/estilo.css?v={v}"></head>
<body style="background:var(--surface)"><div class="embed-page chart"><div class="row-head"><strong>Balança comercial do Brasil, últimos 13 meses</strong>{LEGENDA}</div>
{svg_mensal(B)}
<span class="src">US$ bilhões FOB. Exportações em {mes_nome(B.ref)}: {us(E)}{var_par(E, E0)}. Fonte: Comex Stat/MDIC · <a href="{BASE}/" target="_blank" rel="noopener">Comex em Números</a></span></div>{GOAT}</body></html>"""


def pg_404() -> str:
    return """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Página não encontrada | Comex em Números</title><meta name="robots" content="noindex"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/estilo.css"></head>
<body><main><div class="card"><h1>Página não encontrada</h1><p>Este endereço não existe ou mudou. <a href="/">Voltar ao início</a> ou <a href="/produtos/">ver todos os produtos</a>.</p></div></main>""" + GOAT + "</body></html>"


def redirect(destino: str) -> str:
    return (f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Redirecionando…</title>'
            f'<link rel="canonical" href="{BASE}{destino}"><meta name="robots" content="noindex">'
            f'<meta http-equiv="refresh" content="0; url={destino}"></head><body><a href="{destino}">Continuar</a></body></html>')


# ---------------------------------------------------------------- saída
def escreve(caminho: str, conteudo: str, urls=None):
    destino = SAIDA / caminho.strip("/") / "index.html" if caminho.endswith("/") else SAIDA / caminho.lstrip("/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    if urls is not None:
        urls.append(caminho)


def main() -> None:
    if not DADOS.exists():
        print("Sem data/dados.json; nada a gerar.")
        return
    B = Base(json.loads(DADOS.read_text(encoding="utf-8")))
    for pasta in ("produto", "pais", "estado", "exportacao", "importacao", "produtos", "paises", "estados", "sobre", "embed", "assets", "resumo"):
        shutil.rmtree(SAIDA / pasta, ignore_errors=True)
    (SAIDA / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy(SITE / "estilo.css", SAIDA / "assets" / "estilo.css")
    shutil.copy(SITE / "app.js", SAIDA / "assets" / "app.js")
    for arq in ("og.png", "apple-touch-icon.png"):
        shutil.copy(SITE / arq, SAIDA / "assets" / arq)
    for arq in ("favicon.ico", "favicon.svg"):
        shutil.copy(SITE / arq, SAIDA / arq)

    urls: list[str] = []
    escreve("/", pg_inicio(B), urls)
    escreve("/exportacao/", pg_fluxo(B, "export"), urls)
    escreve("/importacao/", pg_fluxo(B, "import"), urls)
    escreve("/produtos/", pg_produtos(B), urls)
    escreve("/paises/", pg_lista(B, "pais"), urls)
    escreve("/estados/", pg_lista(B, "estado"), urls)
    escreve("/sobre/", pg_sobre(B), urls)
    escreve("/embed/balanca-mensal/", pg_embed(B))
    salva_resumo(B)
    snaps = pgs_resumos(B, urls)
    (SAIDA / "feed.xml").write_text(feed_rss(snaps), encoding="utf-8")

    busca = []
    n_prod = 0
    for p in B.prod.values():
        if not ativo_prod(p):
            continue
        escreve(p["url"], pg_produto(B, p), urls)
        escreve(f"/produto/{p['codigo']}/", redirect(p["url"]))
        busca.append([p["codigo"], p["curto"], p["nome"], p["url"]])
        n_prod += 1
    for it in B.pais.values():
        escreve(it["url"], pg_lugar(B, "pais", it), urls)
    for it in B.uf.values():
        escreve(it["url"], pg_lugar(B, "estado", it), urls)

    B.arq_urls.write_text(json.dumps(dict(sorted(B.urls.items())), ensure_ascii=False, indent=0), encoding="utf-8")
    (SAIDA / "assets" / "busca.json").write_text(json.dumps(busca, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    hoje = B.d["gerado_em"][:10]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{BASE}{u}</loc><lastmod>{hoje}</lastmod></url>" for u in urls]
    sm.append("</urlset>")
    (SAIDA / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (SAIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /embed/\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (SAIDA / "404.html").write_text(pg_404(), encoding="utf-8")
    (SAIDA / ".nojekyll").write_text("", encoding="utf-8")
    (SAIDA / "CNAME").write_text(DOMINIO + "\n", encoding="utf-8")
    (SAIDA / "dados.json").unlink(missing_ok=True)
    print(f"Site gerado: {len(urls)} páginas no sitemap ({n_prod} produtos, {len(B.pais)} países, {len(B.uf)} estados).")


if __name__ == "__main__":
    main()
