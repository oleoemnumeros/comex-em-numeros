"""Gera o site estático do Comex em Números em docs/.

Uma página HTML de verdade para cada produto (SH4), país e estado, com
título, descrição e conteúdo já prontos no HTML, para o Google indexar.
Também gera sitemap.xml, robots.txt, 404.html, busca e a página de embed.

Entrada: data/dados.json (gerado por scripts/atualizar.py)
         site/estilo.css, site/app.js, site/nomes_populares.json
"""
from __future__ import annotations

import datetime as dt
import gzip
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
LICENCA = "https://creativecommons.org/licenses/by/4.0/"
BASE = f"https://{DOMINIO}"
# Contador de visitas (GoatCounter: sem cookies, não precisa de aviso de LGPD)
GOAT = '<script data-goatcounter="https://comexemnumeros.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

# Família em Números: para incluir um novo portal, acrescente uma linha nesta lista
FAMILIA = [
    ("Óleo em Números", "Petróleo e gás", "https://oleoemnumeros.com.br/", "#B45309"),
    ("Comex em Números", "Exportações e importações", "https://comexemnumeros.com.br/", "var(--exp)"),
    ("Voo em Números", "Pontualidade aérea", "https://vooemnumeros.com.br/", "#7C5CE0"),
    ("Economia em Números", "Macroeconomia", "https://economiaemnumeros.com.br/", "#2A5BC4"),
]


# ---------------------------------------------------------------- links cruzados por município
# Cada portal publica a lista das próprias páginas de município; aqui lemos a dos outros e guardamos
# uma cópia em data/familia/ para o caso de o outro site estar fora do ar na hora da geração.
INDICES_FAMILIA = {
    "oleo": ("https://oleoemnumeros.com.br/royalties/indice.json", "Royalties de petróleo", "Óleo em Números",
             "Quanto a cidade recebe de royalties e participação especial"),
    "economia": ("https://economiaemnumeros.com.br/municipios/busca.json", "Economia", "Economia em Números",
                 "População, PIB, Bolsa Família e contas da prefeitura"),
}


def chave_cidade(nome: str, uf: str) -> str:
    t = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t) + "-" + str(uf).strip().upper()


def carrega_familia() -> dict:
    """{chave_cidade: [(rótulo, portal, descrição, url), ...]}"""
    import urllib.request
    pasta = RAIZ / "data" / "familia"
    out: dict = {}
    for nome, (url, rot, portal, desc) in INDICES_FAMILIA.items():
        cache = pasta / f"{nome}.json"
        itens = None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "comexemnumeros"}), timeout=15) as r:
                itens = json.loads(r.read().decode("utf-8"))
            pasta.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(itens, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        except Exception:  # noqa: BLE001
            if cache.exists():
                itens = json.loads(cache.read_text(encoding="utf-8"))
        base = url.split("/", 3)[:3]
        for it in itens or []:
            try:
                cid, uf, caminho = it[0], it[1], it[2]
            except (IndexError, TypeError):
                continue
            link = caminho if caminho.startswith("http") else "/".join(base) + caminho
            out.setdefault(chave_cidade(cid, uf), []).append((rot, portal, desc, link))
    return out


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
UF_SIGLA = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}
# cidades que pedem artigo: "do Rio de Janeiro", "do Recife"
ARTIGO_CIDADE = {"Rio de Janeiro": "o", "Recife": "o", "Rio Grande": "o", "Guarujá": "o", "Crato": "o",
                 "Cabo de Santo Agostinho": "o", "Eusébio": "o", "Gama": "o", "Pecém": "o"}

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
    """prep: 'para' | 'de' | 'com' | '' ; art: o, a, os, as ou vazio."""
    if prep == "de":
        p = {"o": "do", "a": "da", "os": "dos", "as": "das", "": "de"}[art]
        return f"{p} {nome}"
    if prep == "para":
        return f"para {art} {nome}" if art else f"para {nome}"
    if prep == "com":
        return f"com {art} {nome}" if art else f"com {nome}"
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
    if p >= 900:  # 10 vezes ou mais: "▲ 37x" lê melhor que "▲ 3.600%"
        return f'<span class="chg up" title="+{nf(p, 0)}%">▲ {nf(a / b, 0)}x</span>'
    txt = nf(abs(p), 1)
    return f'<span class="chg {"up" if p >= 0 else "down"}">{"▲" if p >= 0 else "▼"} {txt}%</span>'


def junta(*partes) -> str:
    """Une as partes não vazias: 'a', 'a e b', 'a, b e c'."""
    p = [x for x in partes if x]
    return p[0] if len(p) == 1 else (", ".join(p[:-1]) + " e " + p[-1] if p else "")


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


PEQUENAS = {"de", "do", "da", "dos", "das", "e", "em", "na", "no"}
_NOMES_PORTOS = None
VIAS = {"MARITIMA": "Marítima", "AEREA": "Aérea", "RODOVIARIA": "Rodoviária", "FERROVIARIA": "Ferroviária",
        "FLUVIAL": "Fluvial", "LACUSTRE": "Lacustre", "MEIOS PROPRIOS": "Meios próprios",
        "CONDUTO/REDE DE TRANSMISSAO": "Dutos e rede elétrica", "VIA NAO DECLARADA": "Não declarada",
        "VICINAL FRONTEIRICO": "Vicinal fronteiriço", "EM MAOS": "Em mãos", "COURIER": "Courier (remessa expressa)",
        "ENTRADA/SAIDA FICTA": "Entrada/saída ficta", "POSTAL": "Postal"}


def _chave_urf(raw: str) -> str:
    n = re.sub(r"^\d{5,8}\s*-\s*", "", re.sub(r"\s+", " ", (raw or "").replace("\xa0", " ")).strip())
    n = unicodedata.normalize("NFKD", n.upper()).encode("ascii", "ignore").decode()
    return n


def nome_urf(raw: str) -> str:
    """'0817800 - PORTO DE SANTOS' -> 'Porto de Santos (SP)'."""
    global _NOMES_PORTOS
    if _NOMES_PORTOS is None:
        arq = RAIZ / "site" / "nomes_portos.json"
        _NOMES_PORTOS = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    k = _chave_urf(raw)
    if k in _NOMES_PORTOS:
        return _NOMES_PORTOS[k]
    if k in ("NAO INFORMADO", "NAO DECLARADO", "NAO DECLARADA", ""):
        return "Não declarado"
    n = re.sub(r"^(ALF|IRF|ARF|DRF|IRF -|ALF -|ARF -|DRF -)\s*-?\s*", "", re.sub(r"^\d{5,8}\s*-\s*", "", raw.strip()))
    partes = []
    for i, w in enumerate(n.lower().split()):
        partes.append(w if (i > 0 and w in PEQUENAS) else "-".join(x.capitalize() for x in w.split("-")))
    return " ".join(partes)


def nome_via(raw: str) -> str:
    k = _chave_urf(raw)
    return VIAS.get(k, raw.strip().capitalize())


NOTAS_PORTOS = {
    "Porto do Açu (RJ)": "Dados da unidade da Receita Federal em Campos dos Goytacazes, responsável pelo Porto do Açu, em São João da Barra.",
}


def pelo(nome: str) -> str:
    """'pelo Porto de Santos (SP)', 'pelo Aeroporto de Guarulhos (SP)', 'por São Luís (MA)'."""
    return ("pelo " if re.match(r"(Porto|Aeroporto) ", nome) else "por ") + nome


def nao_declarado(nome: str) -> bool:
    n = (nome or "").lower()
    return (not n or n.startswith("não declarad") or n.startswith("nao declarad")
            or n.startswith("não informad") or n.startswith("nao informad"))


# ---------------------------------------------------------------- dados
class Base:
    csv: dict
    def __init__(self, d: dict):
        self.csv = {}
        self.d = d
        self.ref, self.ant = d["mes"], d["mes_ant"]
        populares = json.loads((SITE / "nomes_populares.json").read_text(encoding="utf-8"))
        for chave in ("produtos", "paises", "estados", "setores", "categorias", "portos", "vias"):
            for itens in (d.get(chave) or {}).values():
                for it in itens:
                    it["nome"] = it["nome"].replace("\xa0", " ").strip()
                    if chave == "produtos":
                        it["curto"] = populares.get(it["codigo"]) or encurta(it["nome"])
                    elif chave == "categorias":
                        it["nome"] = amigavel(it["nome"])
                    elif chave == "estados" and nao_declarado(it["nome"]):
                        it["nome"] = "UF não declarada"
                    elif chave == "portos":
                        it["nome"] = nome_urf(it["nome"])
                    elif chave == "vias":
                        it["nome"] = nome_via(it["nome"])
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
        self.porto = (self._indice("portos", "/porto/") if d.get("portos") else {})
        self.porto = {k: v for k, v in self.porto.items() if not nao_declarado(v["nome"])}
        # séries mensais desde 2015 (data/serie/*.json)
        a0, m0 = 2015, 1
        ar, mr = int(self.ref[:4]), int(self.ref[5:])
        self.meses = [f"{y}-{m:02d}" for y in range(a0, ar + 1) for m in range(1, 13) if (y, m) <= (ar, mr)]
        self.serie = {}
        pasta = RAIZ / "data" / "serie"
        for tipo in ("produtos", "paises", "estados", "portos"):
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
                        if tipo == "portos":
                            ch = nome_urf(ch)
                        reg = alvo.setdefault(ch, {"v": [0] * len(self.meses), "k": [0] * len(self.meses)})
                        for j in range(12):
                            if base_i + j < len(self.meses):
                                reg["v"][base_i + j] += it["v"][j]
                                if "k" in it:
                                    reg["k"][base_i + j] += it["k"][j]
        self.tem_serie = any(self.serie[k] for k in self.serie)
        self._carrega_municipios()
        self.familia = carrega_familia() if self.mun else {}
        # só ganha página o local com movimento relevante nos últimos 12 meses (≥ US$ 10 mi), para evitar páginas vazias
        def mov12(nome):
            return sum(sum(self.serie_de("portos", fl, nome)[0][-12:]) for fl in ("export", "import"))
        if self.tem_serie:
            self.porto = {k: v for k, v in self.porto.items() if mov12(v["nome"]) >= 1e7}
        self._carrega_pares()
        cz = d.get("cruzado") or {}
        self.cz = {}
        for chave in ("produto_pais", "produto_estado", "produto_porto"):
            for fl in ("export", "import"):
                linhas = (cz.get(chave) or {}).get(fl) or []
                lim = nome_urf if chave == "produto_porto" else (lambda x: x.replace("\xa0", " ").strip())
                self.cz[(chave, fl)] = [[c, lim(n), a, b] for c, n, a, b in linhas]

    def _carrega_pares(self):
        """Produto x país: meses (data/prodpais/*_mes_*), anos fechados (*_ano_*) e acumulado do ano (*_acum_*)."""
        self.par = {}
        self.par_url = {}
        pasta = RAIZ / "data" / "prodpais"
        if not pasta.exists():
            return
        for arq in sorted(pasta.glob("*.json.gz")):
            fl, tipo, per = arq.name[:-8].split("_", 2)
            try:
                obj = json.loads(gzip.decompress(arq.read_bytes()))
            except Exception:  # noqa: BLE001
                continue
            if tipo == "acum" and obj.get("ate", "")[5:] != self.ref[5:]:
                continue  # acumulado de outro mês de corte
            for cod, pais, fob, kg in obj.get("linhas", []):
                reg = self.par.setdefault((cod, pais), {})
                reg.setdefault(fl, {}).setdefault(tipo, {})[per] = (fob, kg)
        # quem ganha página: ≥ US$ 10 mi em 12 meses (exportação ou importação), produto e país com página própria
        ult12 = self.meses[-12:]
        for (cod, pais), reg in self.par.items():
            if cod not in self.prod or slug(pais) not in self.pais or nao_declarado(pais):
                continue
            tot = max(sum(reg.get(fl, {}).get("mes", {}).get(m, (0, 0))[0] for m in ult12) for fl in ("export", "import"))
            if tot >= 1e7:
                self.par_url[(cod, pais)] = f'{self.prod[cod]["url"]}{slug(pais)}/'

    def _carrega_municipios(self):
        """data/municipios: ranking, produtos e países do mês (e de um ano antes) e série mensal desde 2015."""
        self.mun = {}
        self.mun_serie = {"export": {}, "import": {}}
        self.mun_prod = {}
        self.mun_pais = {}
        pasta = RAIZ / "data" / "municipios"
        if not pasta.exists():
            return
        ref, ant = self.ref, self.ant

        def le(nome):
            arq = pasta / nome
            if not arq.exists():
                return {}
            try:
                return json.loads(gzip.decompress(arq.read_bytes()))
            except Exception:  # noqa: BLE001
                return {}
        idx = {m: k for k, m in enumerate(self.meses)}
        for fl in ("export", "import"):
            for a in range(2015, int(ref[:4]) + 1):
                ob = le(f"{fl}_serie_{a}.json.gz")
                for chave, (nome, vals) in (ob.get("dados") or {}).items():
                    arr = self.mun_serie[fl].setdefault(nome, [0] * len(self.meses))
                    for m, v in enumerate(vals):
                        k = idx.get(f"{a}-{m + 1:02d}")
                        if k is not None:
                            arr[k] = v
            for per, campo in ((ref, "fob"), (ant, "fob_ant")):
                for _, nome, fob, kg in le(f"{fl}_rank_{per}.json.gz").get("dados", []):
                    self._mun_reg(nome).setdefault(fl, {"fob": 0, "fob_ant": 0})[campo] = fob
                for nome, cod, fob, kg in le(f"{fl}_prod_{per}.json.gz").get("dados", []):
                    self.mun_prod.setdefault((nome, fl), {}).setdefault(cod, [0, 0])[0 if per == ref else 1] = fob
                for nome, pais, fob in le(f"{fl}_pais_{per}.json.gz").get("dados", []):
                    pais = pais.replace("\xa0", " ").strip()
                    self.mun_pais.setdefault((nome, fl), {}).setdefault(pais, [0, 0])[0 if per == ref else 1] = fob
        for nome in list(self.mun_serie["export"]) + list(self.mun_serie["import"]):
            self._mun_reg(nome)
        # página para quem movimentou ≥ US$ 10 mi em 12 meses
        for nome, r in list(self.mun.items()):
            t12 = max(sum(self.mun_serie[fl].get(nome, [0])[-12:]) for fl in ("export", "import"))
            if t12 < 1e7 or r["uf"] not in UF_SIGLA:
                r["url"] = ""

    def _mun_reg(self, nome):
        if nome not in self.mun:
            cidade, _, uf = nome.rpartition(" - ")
            cidade = cidade or nome
            self.mun[nome] = {"nome": nome, "cidade": cidade, "uf": uf.strip(), "rotulo": f"{cidade} ({uf.strip()})",
                              "url": f"/municipio/{slug(nome)}/"}
        return self.mun[nome]

    def mun_lista(self, fl, uf=None):
        out = []
        for r in self.mun.values():
            if not r["url"] or (uf and r["uf"] != uf):
                continue
            v = r.get(fl) or {}
            if v.get("fob", 0) > 0:
                out.append({"codigo": r["nome"], "nome": r["rotulo"], "fob": v["fob"], "fob_ant": v.get("fob_ant", 0), "url": r["url"]})
        return sorted(out, key=lambda x: -x["fob"])

    def url_par(self, cod: str, pais: str) -> str:
        return self.par_url.get((cod, pais), "")

    def par_mes(self, cod, pais, fl):
        """(valores, kg) mês a mês alinhados a self.meses."""
        m = self.par.get((cod, pais), {}).get(fl, {}).get("mes", {})
        return [m.get(x, (0, 0))[0] for x in self.meses], [m.get(x, (0, 0))[1] for x in self.meses]

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
        return [r for r in (self.d.get(chave) or {}).get(fl, []) if r["fob"] > 0 or r["fob_ant"] > 0]

    def url_prod(self, cod: str) -> str:
        return self.prod[cod]["url"] if cod in self.prod else ""

    def url_nome(self, tipo: str, nome: str) -> str:
        idx = {"pais": self.pais, "estado": self.uf, "porto": self.porto}[tipo]
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


def tabela(B, rows, tipo, total, modo="valor", urlf=None):
    """tipo: produto | pais | estado | porto. modo: valor | dif. urlf: função que dá o link de cada linha."""
    if not rows:
        return '<p class="small">Sem dados para este recorte.</p>'
    cab = {"produto": "Produto", "pais": "País", "estado": "Estado", "porto": "Porto ou local", "municipio": "Município"}[tipo]
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
            url = r.get("url") or (B.url_nome(tipo, r["nome"]) if tipo != "municipio" else "")
            pre = ""
        if modo == "valor":
            sub = f"{nf(r['fob'] / total * 100, 1)}% do total" if total else ""
            col = chip(r["fob"], r["fob_ant"])
        else:
            sub = f"{chip(r['fob'], r['fob_ant'])} · antes {us(r['fob_ant'])}"
            d = r["fob"] - r["fob_ant"]
            col = f'<span class="chg {"up" if d >= 0 else "down"}">{"+" if d >= 0 else ""}{us_sem(d)}</span>'
        if urlf:
            url = urlf(r) or url
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


def svg_preco(B, series, unid) -> str:
    """Linhas de preço médio mensal desde 2015. series: [(valores ou None, cor)]."""
    n = len(B.meses)
    vals_all = [v for vals, _ in series for v in vals if v]
    if n < 2 or not vals_all:
        return ""
    W, H, L, R, T, Bm = 360, 200, 44, 8, 12, 22
    iw, ih = W - L - R, H - T - Bm
    mx = max(vals_all)
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
                 f'<text x="{L - 4}" y="{y(g) + 3.5:.1f}" text-anchor="end" font-size="10">{nf(g, 0) if g < 1e5 else rot_eixo(g).replace(" mi", "")}</text>')
        g += st
    for i, m in enumerate(B.meses):
        if m.endswith("-01") and int(m[:4]) % 2 == 1:
            o.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{T + ih}" y2="{T + ih + 3}" stroke="var(--muted)"/>'
                     f'<text x="{x(i):.1f}" y="{T + ih + 15}" text-anchor="middle" font-size="10">{m[:4]}</text>')
    for vals, cor in series:
        seg, ultimo = [], None
        for i, v in enumerate(vals):
            if v:
                seg.append(f"{x(i):.1f},{y(v):.1f}")
                ultimo = (i, v)
            elif seg:
                if len(seg) > 1:
                    o.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{cor}" stroke-width="1.4" stroke-linejoin="round"/>')
                seg = []
        if len(seg) > 1:
            o.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{cor}" stroke-width="1.4" stroke-linejoin="round"/>')
        if ultimo:
            o.append(f'<circle cx="{x(ultimo[0]):.1f}" cy="{y(ultimo[1]):.1f}" r="2.6" fill="{cor}"/>')
    o.append(f'<text x="{L}" y="{T - 2}" font-size="10">{unid}</text></svg>')
    return "".join(o)


def svg_13(B, ev, iv, rot_imp=None) -> str:
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
    tem_e = any(e13) if rot_imp is None else not rot_imp
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


def bloco_13(B, ev, iv, E0, E, I0, I, extra="", rot_imp=None) -> str:
    """Cartão com os últimos 13 meses; sem série, cai no comparativo de dois meses."""
    if any(ev[-13:]) or any(iv[-13:]):
        graf = svg_13(B, ev, iv, rot_imp)
        tit = "Últimos 13 meses"
        exp_rot = any(ev[-13:]) if rot_imp is None else not rot_imp
        nota = (f'<p class="src">US$ FOB por mês. Em destaque, {mes_nome(B.ant)} e {mes_nome(B.ref)}; '
                f'o número em cima é o valor {"exportado" if exp_rot else "importado"}.</p>')
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


def csv_texto(meses, colunas: dict) -> str:
    """CSV com ';' (abre direto no Excel em português). Pula os meses iniciais sem movimento."""
    nomes = list(colunas)
    ini = next((k for k in range(len(meses)) if any(colunas[c][k] for c in nomes)), len(meses))
    linhas = ["mes;" + ";".join(nomes)]
    for k in range(ini, len(meses)):
        linhas.append(meses[k] + ";" + ";".join(str(round(colunas[c][k] or 0)) for c in nomes))
    return "\ufeff" + "\r\n".join(linhas) + "\r\n"


def link_csv(nome_arq: str) -> str:
    return f' <a class="csv" href="dados.csv" download="{esc(nome_arq)}">Baixar dados (CSV)</a>'


def bloco_preco(B, nome, ev, ek, iv, ik) -> str:
    """Preço médio mensal (exportação e importação) e quebra valor = volume x preço no acumulado do ano."""
    def serie_preco(v, k):
        return [(a / b * 1000) if (b and b >= 1000 and a) else 0 for a, b in zip(v, k)]
    pe, pi = serie_preco(ev, ek), serie_preco(iv, ik)
    # só mostra o fluxo com peso relevante em pelo menos 12 meses
    usa_e = sum(1 for x in pe if x) >= 12
    usa_i = sum(1 for x in pi if x) >= 12
    if not (usa_e or usa_i):
        return ""
    ref_vals = [x for x in (pe if usa_e else pi) if x]
    por_kg = (sorted(ref_vals)[len(ref_vals) // 2]) >= 100_000
    div = 1000 if por_kg else 1
    unid = "US$/kg" if por_kg else "US$/t"
    series = []
    if usa_i:
        series.append(([x / div for x in pi], "var(--imp)"))
    if usa_e:
        series.append(([x / div for x in pe], "var(--exp)"))
    graf = svg_preco(B, series, unid)
    # acumulado do ano x mesmo período do ano anterior: quanto veio de volume e quanto de preço
    ar = int(B.ref[:4])
    frases = []
    for fl, v, k, usa in (("export", ev, ek, usa_e), ("import", iv, ik, usa_i)):
        if not usa:
            continue
        V, V0, K, K0 = ytd(B, v, ar), ytd(B, v, ar - 1), ytd(B, k, ar), ytd(B, k, ar - 1)
        if not (V and V0 and K and K0):
            continue
        dv, dk, dp = pct(V, V0), pct(K, K0), pct(V / K, V0 / K0)
        verbo = "exportado" if fl == "export" else "importado"
        sv = lambda x: f'{"+" if x >= 0 else "−"}{nf(abs(x), 1)}%'
        if (dv >= 0) != (dk >= 0) and abs(dk) >= 3:
            gancho = "valor e volume andaram em sentidos opostos. O volume variou "
        else:
            gancho = ""
        if gancho:
            frases.append(f"No acumulado de {ar}, o valor {verbo} variou {sv(dv)}, mas {gancho}{sv(dk)} ({toneladas(K)}) "
                          f"e o preço médio, {sv(dp)}.")
        else:
            frases.append(f"No acumulado de {ar}, o valor {verbo} variou {sv(dv)}: o volume, {sv(dk)} ({toneladas(K)}), "
                          f"e o preço médio, {sv(dp)}.")
    leg = ('<div class="legend">' + ('<span><i class="sw" style="background:var(--exp)"></i>Exportação</span>' if usa_e else "")
           + ('<span><i class="sw" style="background:var(--imp)"></i>Importação</span>' if usa_i else "") + "</div>")
    return (f'<div class="card chart"><h2>Preço médio e volume</h2>'
            + (f'<p class="small">{" ".join(frases)}</p>' if frases else "")
            + leg + f'<div role="img" aria-label="Preço médio mensal desde 2015 em {unid}">{graf}</div>'
            f'<p class="src">Preço médio = valor FOB ÷ peso líquido, mês a mês, em {unid}. Meses com menos de 1 tonelada ficam de fora. '
            f'Dentro de uma mesma posição SH4 há produtos diferentes, então mudanças de mix também mexem no preço médio.</p></div>')


def bloco_serie(B, ev, iv, ek=None, rotulo="das exportações", url=None, ik=None) -> str:
    if not (any(ev) or any(iv)):
        return ""
    csv = ""
    if url:
        B.csv[url] = csv_texto(B.meses, {"exportacao_us_fob": ev, "importacao_us_fob": iv} | ({"exportacao_kg": ek} if ek else {})
                               | ({"importacao_kg": ik} if ik else {}))
        csv = link_csv("comexemnumeros-" + url.strip("/").replace("/", "-") + ".csv")
    principal = ev if any(ev) else iv
    rot = rotulo if any(ev) else rotulo.replace("exportações", "importações")
    frase = destaque_serie(B, principal, rot)
    return (f'<div class="card chart"><div class="row-head"><h2>Mês a mês desde 2015</h2>{LEGENDA}</div>'
            + (f'<p>{frase}</p>' if frase else "")
            + f'<div role="img" aria-label="Série mensal de exportações e importações desde 2015">{svg_serie(B, ev, iv)}</div>'
            + f'<p class="src">Valores mensais em US$ FOB. Último ponto: {mes_nome(B.ref)}.{csv}</p></div>'
            + f'<div class="card"><h2>Ano a ano</h2>{tabela_anual(B, ev, iv, ek)}</div>')


LEGENDA = ('<div class="legend"><span><i style="background:var(--exp)"></i>Exportação</span>'
           '<span><i style="background:var(--imp)"></i>Importação</span></div>')

NAV = [("/", "Início"), ("/exportacao/", "Exportação"), ("/importacao/", "Importação"),
       ("/produtos/", "Produtos"), ("/paises/", "Países"), ("/estados/", "Estados"), ("/municipios/", "Municípios"), ("/portos/", "Portos"), ("/sobre/", "Como funciona")]


def pagina(B, caminho, titulo, descricao, corpo, ativo="", jsonld=None, migalhas=None, imagem=None) -> str:
    url = BASE + caminho
    # o Google corta títulos acima de ~60 caracteres: tira a marca da <title> quando passa disso
    titulo_tag = titulo[:-len(" | Comex em Números")] if len(titulo) > 62 and titulo.endswith(" | Comex em Números") else titulo
    nav = "".join(f'<a href="{h}"' + (' aria-current="page"' if h == ativo else "") + f">{t}</a>" for h, t in NAV)
    bc = ""
    lds = [jsonld] if jsonld else []
    if migalhas:
        itens = [{"@type": "ListItem", "position": 1, "name": "Início", "item": BASE + "/"}]
        for i, (h, t_) in enumerate(migalhas, 2):
            itens.append({"@type": "ListItem", "position": i, "name": t_, "item": BASE + (h or caminho)})
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": itens})
    if migalhas:
        partes = ['<a href="/">Início</a>'] + [f'<a href="{h}">{esc(t)}</a>' if h else esc(t) for h, t in migalhas]
        bc = '<nav class="bc" aria-label="Você está em">' + " › ".join(partes) + "</nav>"
    ld = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in lds)
    gerado = dt.datetime.fromisoformat(B.d["gerado_em"]).strftime("%d/%m/%Y")
    v = B.d["gerado_em"][:10]
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titulo_tag)}</title>
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
<span><a href="/resumo/">Resumos mensais</a> · <a href="/produtos/">Todos os produtos</a> · <a href="/paises/">Países</a> · <a href="/estados/">Estados</a> · <a href="/municipios/">Municípios</a> · <a href="/portos/">Portos</a> · <a href="/sobre/">Como funciona</a> · <a href="/sugestoes/">Sugestões e críticas</a></span>
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


def tabela_volume(B, rows) -> str:
    h = [f'<div class="scroll"><table><thead><tr><th></th><th>Produto</th><th class="r">Mil t</th><th class="r">Var.</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        p = B.prod.get(r["codigo"], {})
        nome = p.get("curto") or r["nome"]
        url = B.url_prod(r["codigo"])
        pr = preco(r["fob"], r["kg"])
        sub = f'SH4 {esc(r["codigo"])} · {us(r["fob"])}' + (f" · {pr[1].split('/')[0]} {pr[0]}/{pr[1].split('/')[1]}" if pr else "")
        h.append(f'<tr><td class="n">{i}</td><td><a href="{url}">{esc(corta(nome))}</a><span class="s">{sub}</span></td>'
                 f'<td class="r">{nf(r["kg"] / 1e6, 0) if r["kg"] >= 1e7 else nf(r["kg"] / 1e6, 1)}</td><td class="r">{chip(r["kg"], r.get("kg_ant", 0))}</td></tr>')
    h.append("</tbody></table></div>")
    return "".join(h)


def tabela_preco(B, rows) -> str:
    h = [f'<div class="scroll"><table><thead><tr><th></th><th>Produto</th><th class="r">Preço</th><th class="r">Var.</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        p = B.prod.get(r["codigo"], {})
        nome = p.get("curto") or r["nome"]
        pr, pr0 = preco(r["fob"], r["kg"]), preco(r["fob_ant"], r["kg_ant"])
        dv = pct(r["kg"], r["kg_ant"])
        sub = f'{us(r["fob"])} · volume {"+" if dv >= 0 else "−"}{nf(abs(dv), 1)}% · antes {pr0[0] if pr0 else "—"}'
        h.append(f'<tr><td class="n">{i}</td><td><a href="{B.url_prod(r["codigo"])}">{esc(corta(nome))}</a><span class="s">{sub}</span></td>'
                 f'<td class="r">{pr[0]}<span class="s">{pr[1]}</span></td><td class="r">{chip(r["fob"] / r["kg"], r["fob_ant"] / r["kg_ant"])}</td></tr>')
    h.append("</tbody></table></div>")
    return "".join(h)


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
<button type="button" data-t="valor" aria-pressed="true">Valor</button><button type="button" data-t="volume" aria-pressed="false">Volume</button><button type="button" data-t="preco" aria-pressed="false">Preço</button><button type="button" data-t="altas" aria-pressed="false">Altas</button><button type="button" data-t="quedas" aria-pressed="false">Quedas</button></div></div>
<div data-p="valor"><p class="small">Os 20 produtos de maior valor no mês (classificação SH4).</p>{tabela(B, ps[:20], "produto", tot)}</div>
<div data-p="volume" hidden><p class="small">Os 20 produtos de maior peso no mês, em mil toneladas, com a variação do volume contra {mes_nome(B.ant)}.</p>{tabela_volume(B, sorted([r for r in ps if r.get("kg", 0) > 0], key=lambda r: -r["kg"])[:20])}</div>
<div data-p="preco" hidden><p class="small">Maiores variações do preço médio (US$ por tonelada ou por quilo) contra {mes_nome(B.ant)}, entre produtos acima de US$ 50 mi e 1 mil toneladas nos dois meses.</p>{tabela_preco(B, sorted([r for r in ps if r["fob"] >= 5e7 and r.get("kg", 0) >= 1e6 and r.get("kg_ant", 0) >= 1e6 and r["fob_ant"] > 0], key=lambda r: -abs(pct(r["fob"] / r["kg"], r["fob_ant"] / r["kg_ant"])))[:20])}</div>
<div data-p="altas" hidden><p class="small">Maiores aumentos em US$ contra {mes_nome(B.ant)} (produtos acima de US$ 10 mi).</p>{tabela(B, altas(ps)[:20], "produto", tot, "dif")}</div>
<div data-p="quedas" hidden><p class="small">Maiores quedas em US$ contra {mes_nome(B.ant)} (produtos acima de US$ 10 mi).</p>{tabela(B, quedas(ps)[:20], "produto", tot, "dif")}</div>
<div class="search"><label for="busca" class="small" style="align-self:center">Buscar</label><input id="busca" type="search" placeholder="Ex.: café, soja, aço, medicamentos" autocomplete="off"></div><div id="busca-res" aria-live="polite"></div>
<p class="small"><a href="/produtos/">Ver a lista completa de produtos →</a></p></div>
<div class="two"><div class="card"><h2>{"Por setor" if fl == "export" else "Por tipo de bem"}</h2>{hbars(grupos, cor)}</div>
<div class="card"><div class="row-head"><h2>{"Principais destinos" if fl == "export" else "Principais origens"}</h2><a class="small" href="/paises/">Todos →</a></div>{tabela(B, B.lista("paises", fl)[:8], "pais", tot)}</div></div>
<div class="card"><div class="row-head"><h2>{"Estados que mais exportam" if fl == "export" else "Estados que mais importam"}</h2><a class="small" href="/estados/">Todos →</a></div>{tabela(B, [r for r in B.lista("estados", fl) if r["nome"] != "UF não declarada"][:8], "estado", tot)}</div>
{bloco_portos_fluxo(B, fl, tot)}"""
    top3 = ", ".join(minusc(r["curto"]) for r in ps[:3])
    desc = desc_corta(f"{nomefl} do Brasil em {mes_nome(B.ref)}: {us(tot)}{var_par(tot, tot0)}. Ranking dos produtos, maiores altas e quedas. "
                      f"Destaques: {top3}.")
    caminho = "/exportacao/" if fl == "export" else "/importacao/"
    tit = f'{"Exportações" if fl == "export" else "Importações"} do Brasil por produto | Comex em Números'
    return pagina(B, caminho, tit, desc, c, caminho, migalhas=[(None, nomefl)])


def bloco_portos_fluxo(B, fl, tot) -> str:
    portos = [r for r in B.lista("portos", fl) if r["fob"] > 0 and not nao_declarado(r["nome"])]
    if not portos:
        return ""
    vias = [r for r in B.lista("vias", fl) if r["fob"] > 0]
    cor = "var(--exp)" if fl == "export" else "var(--imp)"
    return (f'<div class="two"><div class="card"><div class="row-head"><h2>{"Por onde sai" if fl == "export" else "Por onde entra"}</h2>'
            f'<a class="small" href="/portos/">Todos →</a></div>{tabela(B, portos[:8], "porto", tot)}</div>'
            + (f'<div class="card"><h2>Por meio de transporte</h2>{hbars(vias[:6], cor)}</div>' if vias else "") + "</div>")


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
    chave = {"pais": "paises", "estado": "estados", "porto": "portos"}[tipo]
    tit = {"pais": "Países", "estado": "Estados", "porto": "Portos"}[tipo]
    blocos = []
    for fl in ("export", "import"):
        tot = B.tot(fl, B.ref)
        h2 = {"pais": {"export": "Destinos das exportações", "import": "Origens das importações"},
              "estado": {"export": "Exportações por estado", "import": "Importações por estado"},
              "porto": {"export": "Por onde saem as exportações", "import": "Por onde entram as importações"}}[tipo][fl]
        linhas = [r for r in B.lista(chave, fl) if r["fob"] > 0 and not (tipo == "porto" and nao_declarado(r["nome"]))]
        blocos.append(f'<div class="card"><h2>{h2}</h2>{tabela(B, linhas[:60], tipo, tot)}</div>')
    texto = {"pais": "Para quem o Brasil vende e de quem compra. Toque em um país para ver o comércio bilateral e os produtos.",
             "estado": "Quanto cada estado exporta e importa. Toque em um estado para ver os produtos. "
                       "\"UF não declarada\" reúne as operações em que o estado de origem ou destino não foi informado à Receita.",
             "porto": "Por onde as mercadorias saem e entram no Brasil: portos, aeroportos e postos de fronteira. Toque em um local "
                      "para ver os produtos. O dado é a unidade da Receita Federal onde a carga foi despachada, que nem sempre é o porto "
                      "físico de embarque: por Niterói (RJ), por exemplo, passa quase só petróleo."}[tipo]
    if tipo in ("pais", "porto"):
        nomes = {}
        for fl in ("export", "import"):
            for r in B.lista(chave, fl):
                if not (tipo == "porto" and nao_declarado(r["nome"])):
                    u = B.url_nome(tipo, r["nome"])
                    if u:
                        nomes[r["nome"]] = u
        az = " · ".join(f'<a href="{u}">{esc(n)}</a>' for n, u in sorted(nomes.items(), key=lambda t: t[0]))
        blocos.append(f'<div class="card"><h2>{"Todos os países" if tipo == "pais" else "Todos os locais"} (A–Z)</h2><p class="small">{az}</p></div>')
    c = f'<div class="card"><span class="eyebrow">{tit} · {mes_nome(B.ref)}</span><h1>{tit}</h1><p class="lede">{texto}</p></div><div class="cols">{"".join(blocos)}</div>'
    caminho = {"pais": "/paises/", "estado": "/estados/", "porto": "/portos/"}[tipo]
    desc = {"pais": f"Exportações e importações do Brasil por país em {mes_nome(B.ref)}: principais destinos e origens, com variação anual.",
            "estado": f"Exportações e importações por estado em {mes_nome(B.ref)}: ranking das UFs, com variação anual.",
            "porto": f"Ranking dos portos, aeroportos e fronteiras por onde passam as exportações e importações do Brasil em {mes_nome(B.ref)}."}[tipo]
    t = {"pais": "Comércio exterior do Brasil por país", "estado": "Exportações e importações por estado",
         "porto": "Exportações e importações por porto"}[tipo] + " | Comex em Números"
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
            f'<div class="card"><h2>Para onde vai</h2><p class="small">Países que mais compraram {esc(minusc(nome))} do Brasil em {mes_nome(B.ref)}.</p>{tabela(B, dest[:25], "pais", E, urlf=lambda r: B.url_par(cod, r["nome"]))}</div>' if dest else "",
            f'<div class="card"><h2>Estados que mais exportam</h2>{tabela(B, ufe[:10], "estado", E)}</div>' if ufe else ""))
    pse = [r for r in B.cruz("produto_porto", "export", filtro_cod=cod) if not nao_declarado(r["nome"])]
    psi = [r for r in B.cruz("produto_porto", "import", filtro_cod=cod) if not nao_declarado(r["nome"])]
    if E and pse:
        secoes.append(f'<div class="card"><h2>Por onde sai</h2><p class="small">Portos, aeroportos e fronteiras por onde {esc(minusc(nome))} foi exportado em {mes_nome(B.ref)}.</p>{tabela(B, pse[:8], "porto", E)}</div>')
    if I:
        secoes.append(par_cards(
            f'<div class="card"><h2>De onde vem</h2><p class="small">Países de onde o Brasil mais importou em {mes_nome(B.ref)}.</p>{tabela(B, orig[:25], "pais", I, urlf=lambda r: B.url_par(cod, r["nome"]))}</div>' if orig else "",
            f'<div class="card"><h2>Estados que mais importam</h2>{tabela(B, ufi[:10], "estado", I)}</div>' if ufi else ""))
    if I and psi:
        secoes.append(f'<div class="card"><h2>Por onde entra</h2><p class="small">Portos, aeroportos e fronteiras por onde {esc(minusc(nome))} foi importado em {mes_nome(B.ref)}.</p>{tabela(B, psi[:8], "porto", I)}</div>')
    oficial = f'<p class="oficial">Nome oficial (SH4 {esc(cod)}): {esc(p["nome"])}</p>' if p["nome"] != nome else ""
    sev, sek = B.serie_de("produtos", "export", cod)  # noqa: F841
    siv, sik = B.serie_de("produtos", "import", cod)
    serie_html = bloco_serie(B, sev, siv, sek, f"das exportações de {esc(minusc(nome))}", url=p["url"], ik=sik)
    preco_html = bloco_preco(B, nome, sev, sek, siv, sik)
    c = f"""<div class="card"><span class="eyebrow">Produto · SH4 {esc(cod)}</span><h1>{esc(nome)}</h1>{oficial}<p class="lede">{" ".join(frases)}</p></div>
<div class="tiles">{tiles}</div>
{bloco_13(B, sev, siv, E0, E, I0, I, vol)}
{preco_html}
{"".join(secoes)}
{serie_html}"""
    t = f"{cap(nome)}: exportação e importação | Comex em Números"
    if len(t) > 70:
        t = f"{corta(cap(nome.split(' (SH4')[0]), 36)} (SH4 {cod}): exportação e importação"
    nome_d = minusc(nome.split(" (SH4")[0])
    if not E and not I:
        desc = (f"{cap(nome_d)}: sem comércio em {mes_curto(B.ref)}. Um ano antes, "
                + junta(f"exportações de {us(E0)}" if E0 else "", f"importações de {us(I0)}" if I0 else "") + ". Série mensal desde 2015.")
    elif E:
        desc = (f"O Brasil exportou {us(E)} em {nome_d} em {mes_curto(B.ref)}{var_par(E, E0)}. "
                "Destinos, estados, volume, preço e série desde 2015.")
    else:
        desc = (f"O Brasil importou {us(I)} em {nome_d} em {mes_curto(B.ref)}{var_par(I, I0)}. "
                "De onde vem, estados, preço e série desde 2015.")
    desc = desc_corta(desc)
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"Comércio exterior do Brasil: {nome} (SH4 {cod})",
          "description": desc, "url": BASE + p["url"], "inLanguage": "pt-BR", "temporalCoverage": f"{B.ant}/{B.ref}",
          "isAccessibleForFree": True, "license": LICENCA, "creator": {"@type": "Organization", "name": "Comex em Números", "url": BASE + "/"},
          "isBasedOn": "https://comexstat.mdic.gov.br/"}
    return pagina(B, p["url"], t, desc, c, "/produtos/", ld, migalhas=[("/produtos/", "Produtos"), (None, corta(nome, 40))])


def pg_lugar(B, tipo: str, it: dict) -> str:
    e, i = it.get("export") or {}, it.get("import") or {}
    E, E0, I, I0 = e.get("fob", 0), e.get("fob_ant", 0), i.get("fob", 0), i.get("fob_ant", 0)
    nome = it["nome"]
    chave = {"pais": "paises", "estado": "estados", "porto": "portos"}[tipo]
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
        desc = desc_corta(f"Em {mes_curto(B.ref)}, o Brasil "
                          + (junta(f"exportou {us(E)} {para}{var_par(E, E0)}" if E else "", f"importou {us(I)}{var_par(I, I0)}" if I else "")
                             or f"não teve comércio {com_artigo(nome, 'com', art_pais(nome))}")
                          + ". Produtos, saldo e série desde 2015.")
        migalha = ("/paises/", "Países")
    elif tipo == "porto":
        frase = (f'Em {mes_nome(B.ref)}, ' + (junta(
            f'saíram {esc(pelo(nome))} <strong class="num">{us(E)}</strong> em exportações{var_par(E, E0)}' if E else "",
            (f'entraram' if E else f'entraram {esc(pelo(nome))}') + f' <strong class="num">{us(I)}</strong> em importações{var_par(I, I0)}' if I else "")
            or f'não houve movimento {esc(pelo(nome))}') + '.')
        if rank:
            frase += f" É o {rank}º local de saída das exportações brasileiras, com {nf(E / EXP * 100, 1)}% do total."
        cz_e = B.cruz("produto_porto", "export", filtro_nome=nome)
        cz_i = B.cruz("produto_porto", "import", filtro_nome=nome)
        h_e, h_i = f"O que sai {esc(pelo(nome))}", f"O que entra {esc(pelo(nome))}"
        if nome in NOTAS_PORTOS:
            frase += f' <span class="small">{esc(NOTAS_PORTOS[nome])}</span>'
        t = f"{nome}: o que sai e o que entra | Comex em Números"
        desc = desc_corta(f"{nome} em {mes_curto(B.ref)}: "
                          + (junta(f"exportações de {us(E)}{var_par(E, E0)}" if E else "", f"importações de {us(I)}{var_par(I, I0)}" if I else "")
                             or "sem movimento") + ". Produtos que mais saem e entram, e série desde 2015.")
        migalha = ("/portos/", "Portos")
        de = "de"
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
        desc = desc_corta(f"{nome} em {mes_curto(B.ref)}: "
                          + (junta(f"exportações de {us(E)}{var_par(E, E0)}" if E else "", f"importações de {us(I)}{var_par(I, I0)}" if I else "")
                             or "sem comércio exterior") + ". Principais produtos e série desde 2015.")
        migalha = ("/estados/", "Estados")
    tiles = (tile("exp", "Exportações", us_sem(E), "US$", chip(E, E0)) + tile("imp", "Importações", us_sem(I), "US$", chip(I, I0))
             + tile("bal", "Saldo", us_sem(E - I), "US$", f'<span class="chg flat">antes {us_sem(E0 - I0)}</span>')
             + tile("", "Corrente de comércio", us_sem(E + I), "US$", chip(E + I, E0 + I0)))
    sev, _ = B.serie_de(chave, "export", nome)
    siv, _ = B.serie_de(chave, "import", nome)
    rot = {"pais": lambda: f"das exportações {esc(para)}", "estado": lambda: f"das exportações {de} {esc(nome)}",
           "porto": lambda: f"das exportações {esc(pelo(nome))}"}[tipo]()
    serie_html = bloco_serie(B, sev, siv, None, rot, url=it["url"])
    uf_ = (lambda r: B.url_par(r["codigo"], nome)) if tipo == "pais" else None
    bloco_mun = ""
    if tipo == "estado":
        sig = next((k for k, v in UF_SIGLA.items() if v == nome), "")
        me, mi = B.mun_lista("export", sig), B.mun_lista("import", sig)
        partes = []
        if me:
            partes.append(f'<div class="card"><h2>Municípios que mais exportam</h2>{tabela(B, me[:10], "municipio", E)}</div>')
        if mi:
            partes.append(f'<div class="card"><h2>Municípios que mais importam</h2>{tabela(B, mi[:10], "municipio", I)}</div>')
        bloco_mun = (f'<div class="two" id="municipios">{"".join(partes)}</div>' if len(partes) == 2
                     else f'<div id="municipios">{"".join(partes)}</div>' if partes else "")
    ce = (f'<div class="card"><h2>{h_e}</h2><p class="small">Principais produtos exportados em {mes_nome(B.ref)}.</p>{tabela(B, cz_e[:15], "produto", E, urlf=uf_)}</div>' if cz_e else "")
    ci = (f'<div class="card"><h2>{h_i}</h2><p class="small">Principais produtos importados em {mes_nome(B.ref)}.</p>{tabela(B, cz_i[:15], "produto", I, urlf=uf_)}</div>' if cz_i else "")
    secoes = f'<div class="cols">{ce}{ci}</div>' if ce and ci else (ce or ci)
    c = f"""<div class="card"><span class="eyebrow">{ {"pais": "País", "estado": "Estado", "porto": "Porto ou local de despacho"}[tipo] }</span><h1>{esc(nome)}</h1><p class="lede">{frase}</p></div>
<div class="tiles">{tiles}</div>
{bloco_13(B, sev, siv, E0, E, I0, I)}
{secoes}
{bloco_mun}
{serie_html}"""
    return pagina(B, it["url"], t, desc, c, migalha[0], migalhas=[migalha, (None, nome)])


AVISO_MUN = ("O município é o domicílio fiscal da empresa que exportou ou importou, que nem sempre é onde a mercadoria "
             "foi produzida ou consumida. Exportações de petróleo da Petrobras, por exemplo, aparecem no Rio de Janeiro.")


def de_cidade(r) -> str:
    art = ARTIGO_CIDADE.get(r["cidade"], "")
    return f"d{art} {r['rotulo']}" if art else f"de {r['rotulo']}"


def par_cards(a, b):
    cards = [x for x in (a, b) if x]
    if not cards:
        return ""
    return f'<div class="cols">{"".join(cards)}</div>' if len(cards) == 2 else cards[0]


def pg_municipio(B, r) -> str:
    nome = r["nome"]
    e, i = r.get("export") or {}, r.get("import") or {}
    E, E0, I, I0 = e.get("fob", 0), e.get("fob_ant", 0), i.get("fob", 0), i.get("fob_ant", 0)
    sev = B.mun_serie["export"].get(nome, [0] * len(B.meses))
    siv = B.mun_serie["import"].get(nome, [0] * len(B.meses))
    uf_nome = UF_SIGLA.get(r["uf"], r["uf"])
    dc = de_cidade(r)
    rk_br = next((k for k, x in enumerate(B.mun_lista("export"), 1) if x["codigo"] == nome), None) if E else None
    rk_uf = next((k for k, x in enumerate(B.mun_lista("export", r["uf"]), 1) if x["codigo"] == nome), None) if E else None
    partes = []
    if E:
        partes.append(f'exportaram <strong class="num">{us(E)}</strong>{var_par(E, E0)}')
    if I:
        partes.append(f'importaram <strong class="num">{us(I)}</strong>{var_par(I, I0)}')
    if partes:
        frase = f"Em {mes_nome(B.ref)}, empresas {esc(dc)} " + junta(*partes) + "."
    else:
        frase = f"Em {mes_nome(B.ref)}, não houve exportação nem importação registrada por empresas {esc(dc)}."
    if rk_br and rk_uf:
        o_uf = {"o": "do", "a": "da", "os": "dos", "as": "das"}.get(ARTIGO_UF.get(uf_nome, ""), "de")
        frase += f" É o {rk_br}º município que mais exportou no Brasil e o {rk_uf}º {o_uf} {esc(uf_nome)}."
    tiles = (tile("exp", "Exportações", us_sem(E), "US$", chip(E, E0)) + tile("imp", "Importações", us_sem(I), "US$", chip(I, I0))
             + tile("bal", "Saldo", us_sem(E - I), "US$", f'<span class="chg flat">antes {us_sem(E0 - I0)}</span>')
             + tile("", "Corrente de comércio", us_sem(E + I), "US$", chip(E + I, E0 + I0)))

    def linhas_prod(fl):
        d = B.mun_prod.get((nome, fl), {})
        out = [{"codigo": c, "nome": (B.prod.get(c) or {}).get("curto", c), "fob": a, "fob_ant": b} for c, (a, b) in d.items() if a > 0]
        return sorted(out, key=lambda x: -x["fob"])

    def linhas_pais(fl):
        d = B.mun_pais.get((nome, fl), {})
        out = [{"codigo": "", "nome": pa, "fob": a, "fob_ant": b} for pa, (a, b) in d.items() if a > 0 and not nao_declarado(pa)]
        return sorted(out, key=lambda x: -x["fob"])
    pe, pi, ce, ci = linhas_prod("export"), linhas_prod("import"), linhas_pais("export"), linhas_pais("import")
    blocos = []
    if pe or ce:
        blocos.append(par_cards(
            f'<div class="card"><h2>O que exporta</h2><p class="small">Produtos exportados por empresas {esc(dc)} em {mes_nome(B.ref)}.</p>{tabela(B, pe[:12], "produto", E)}</div>' if pe else "",
            f'<div class="card"><h2>Para onde vende</h2>{tabela(B, ce[:10], "pais", E)}</div>' if ce else ""))
    if pi or ci:
        blocos.append(par_cards(
            f'<div class="card"><h2>O que importa</h2><p class="small">Produtos importados por empresas {esc(dc)} em {mes_nome(B.ref)}.</p>{tabela(B, pi[:12], "produto", I)}</div>' if pi else "",
            f'<div class="card"><h2>De onde compra</h2>{tabela(B, ci[:10], "pais", I)}</div>' if ci else ""))
    vizinhos = [x for x in B.mun_lista("export", r["uf"]) if x["codigo"] != nome][:8]
    url_uf = B.url_nome("estado", uf_nome)
    viz = (f'<div class="card"><div class="row-head"><h2>Outros municípios {"do" if ARTIGO_UF.get(uf_nome) == "o" else "da" if ARTIGO_UF.get(uf_nome) == "a" else "de"} {esc(uf_nome)}</h2>'
           + (f'<a class="small" href="{url_uf}">Ver estado →</a>' if url_uf else "") + f'</div>{tabela(B, vizinhos, "municipio", 0)}</div>') if vizinhos else ""
    serie_html = bloco_serie(B, sev, siv, None, f"das exportações {esc(dc)}", url=r["url"])
    outros = B.familia.get(chave_cidade(r["cidade"], r["uf"]), [])
    mais = ""
    if outros:
        itens = "".join(f'<li><a href="{esc(u)}">{esc(rot)} {esc(dc)}</a><span class="small"> · {esc(portal)}: {esc(d)}</span></li>'
                        for rot, portal, d, u in outros)
        mais = f'<div class="card"><h2>Mais sobre {esc(r["rotulo"])}</h2><ul class="plain">{itens}</ul></div>'
    c = f"""<div class="card"><span class="eyebrow">Município · {esc(uf_nome)}</span><h1>{esc(r["rotulo"])}</h1><p class="lede">{frase}</p>
<p class="small">{AVISO_MUN}</p></div>
<div class="tiles">{tiles}</div>
{bloco_13(B, sev, siv, E0, E, I0, I)}
{"".join(blocos)}
{serie_html}
{mais}
{viz}"""
    t = f"Exportações e importações {dc} | Comex em Números"
    if len(t) > 75:
        t = f"Comércio exterior {dc}"
    desc = desc_corta(f"{r['rotulo']} em {mes_curto(B.ref)}: "
                      + (junta(f"exportações de {us(E)}{var_par(E, E0)}" if E else "", f"importações de {us(I)}{var_par(I, I0)}" if I else "")
                         or "sem comércio exterior") + ". Produtos, países e série desde 2015.")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"Comércio exterior {dc}", "description": desc,
          "url": BASE + r["url"], "inLanguage": "pt-BR", "temporalCoverage": f"2015-01/{B.ref}", "isAccessibleForFree": True,
          "license": LICENCA, "creator": {"@type": "Organization", "name": "Comex em Números", "url": BASE + "/"},
          "isBasedOn": "https://comexstat.mdic.gov.br/"}
    mig = [("/municipios/", "Municípios")] + ([(url_uf, uf_nome)] if url_uf else []) + [(None, r["rotulo"])]
    return pagina(B, r["url"], t, desc, c, "/municipios/", ld, migalhas=mig)


def pg_municipios(B) -> str:
    blocos = []
    for fl in ("export", "import"):
        tot = B.tot(fl, B.ref)
        lst = B.mun_lista(fl)
        h2 = "Municípios que mais exportam" if fl == "export" else "Municípios que mais importam"
        blocos.append(f'<div class="card"><h2>{h2}</h2>{tabela(B, lst[:100], "municipio", tot)}</div>')
    por_uf = " · ".join(f'<a href="{B.url_nome("estado", n)}#municipios">{s_}</a>' for s_, n in sorted(UF_SIGLA.items()) if B.url_nome("estado", n))
    n_pag = sum(1 for r in B.mun.values() if r["url"])
    por_est = {}
    for r in B.mun.values():
        if r["url"]:
            por_est.setdefault(r["uf"], []).append(r)
    todos = "".join(
        f'<h3 id="uf-{esc(uf.lower())}">{esc(UF_SIGLA[uf])}</h3><p class="small">' +
        " · ".join(f'<a href="{r["url"]}">{esc(r["cidade"])}</a>' for r in sorted(rs, key=lambda x: x["cidade"])) + "</p>"
        for uf, rs in sorted(por_est.items(), key=lambda t: UF_SIGLA[t[0]]))
    blocos.append(f'<div class="card"><h2>Todos os municípios com página</h2>{todos}</div>')
    c = f"""<div class="card"><span class="eyebrow">Ranking · {cap(mes_nome(B.ref))}</span><h1>Exportações e importações por município</h1>
<p class="lede">Os municípios brasileiros que mais exportaram e importaram em {mes_nome(B.ref)}. Toque em um município para ver produtos, países e a série desde 2015. São {nf(n_pag, 0)} municípios com página própria (pelo menos US$ 10 milhões em 12 meses).</p>
<p class="small">{AVISO_MUN}</p><p class="small">Por estado: {por_uf}</p></div>
<div class="cols">{"".join(blocos)}</div>"""
    desc = f"Ranking dos municípios que mais exportam e importam no Brasil em {mes_nome(B.ref)}, com produtos, países e série desde 2015."
    return pagina(B, "/municipios/", "Exportações por município: ranking do Brasil | Comex em Números", desc, c, "/municipios/",
                  migalhas=[(None, "Municípios")])


def preco(v: float, kg: float):
    """('6.985', 'US$/t') ou, para produtos caros, ('2.120', 'US$/kg'). None sem peso relevante."""
    if kg < 1000 or not v:
        return None
    pt = v / kg * 1000
    return (nf(pt / 1000, 0), "US$/kg") if pt >= 100_000 else (nf(pt, 0), "US$/t")


def svg_anos(anos, vals, cor, parcial=False) -> str:
    """Barras por ano; a última pode ser o ano em curso (mais clara)."""
    if not any(vals):
        return ""
    W, H, L, R, T, Bm = 360, 170, 40, 6, 14, 22
    iw, ih = W - L - R, H - T - Bm
    mx = max(vals) or 1
    st = passo_bonito(mx)
    top = st * (int(mx / st) + (0 if mx % st == 0 else 1))
    n = len(vals)
    step = iw / n
    bw = step * 0.62
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="max-width:640px">']
    g = 0.0
    while g <= top + 1e-6:
        y = T + ih - g / top * ih
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--line)"/>'
                 f'<text x="{L - 4}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10">{rot_eixo(g)}</text>')
        g += st
    for k, (a, v) in enumerate(zip(anos, vals)):
        x0 = L + k * step + (step - bw) / 2
        h_ = v / top * ih
        op = 0.5 if (parcial and k == n - 1) else 1
        o.append(f'<rect x="{x0:.1f}" y="{T + ih - h_:.1f}" width="{bw:.1f}" height="{max(h_, 0):.1f}" rx="1.5" fill="{cor}" opacity="{op}">'
                 f'<title>{a}: {us(v)}</title></rect>'
                 f'<text x="{x0 + bw / 2:.1f}" y="{T + ih + 14}" text-anchor="middle" font-size="9.5">{str(a)[2:]}</text>')
    o.append("</svg>")
    return "".join(o)


def pg_par(B, cod: str, pais: str) -> str:
    p = B.prod[cod]
    nome = p["curto"]
    nome_d = minusc(nome.split(" (SH4")[0])
    ap = art_pais(pais)
    para, de_p = com_artigo(pais, "para", ap), com_artigo(pais, "de", ap)
    reg = B.par.get((cod, pais), {})
    ev, ek = B.par_mes(cod, pais, "export")
    iv, ik = B.par_mes(cod, pais, "import")
    j, j0 = len(B.meses) - 1, len(B.meses) - 13
    E, E0, I, I0 = ev[j], (ev[j0] if j0 >= 0 else 0), iv[j], (iv[j0] if j0 >= 0 else 0)
    K, K0, KI, KI0 = ek[j], (ek[j0] if j0 >= 0 else 0), ik[j], (ik[j0] if j0 >= 0 else 0)
    exp_princ = sum(ev[-12:]) >= sum(iv[-12:])
    url = B.url_par(cod, pais)

    # frases: primeiro o fluxo principal, com volume, preço e fatia; o outro em uma linha
    def frase(fl, V, V0, KG, KG0, principal):
        exp = fl == "export"
        prep = para if exp else de_p
        verbo = "exportou" if exp else "importou"
        if not V:
            if not V0:
                return ""
            return (f"Em {mes_nome(B.ref)}, o Brasil não {verbo} {esc(nome_d)} {esc(prep)}. Um ano antes, tinham sido {us(V0)}."
                    if principal else f"Não houve {'exportação' if exp else 'importação'} no mês (um ano antes: {us(V0)}).")
        if not principal:
            return f'O Brasil também {verbo} <strong class="num">{us(V)}</strong> {esc(prep)}{var_par(V, V0)}.'
        f = f'Em {mes_nome(B.ref)}, o Brasil {verbo} <strong class="num">{us(V)}</strong> em {esc(nome_d)} {esc(prep)}'
        f += f", {var_txt(V, V0)} sobre um ano antes." if V0 else "."
        pr, pr0 = preco(V, KG), preco(V0, KG0)
        if pr:
            f += f" Foram {toneladas(KG)}, a {pr[1].split('/')[0]} {pr[0]} por {'tonelada' if pr[1].endswith('/t') else 'quilo'}"
            f += f" (um ano antes, {pr0[1].split('/')[0]} {pr0[0]})." if pr0 and pr0[1] == pr[1] else "."
        tot_p = (p.get(fl) or {}).get("fob", 0)
        lst = B.cruz("produto_pais", fl, filtro_cod=cod)
        pos = next((k for k, r in enumerate(lst, 1) if r["nome"] == pais), None)
        if tot_p and pos:
            o_pais = esc(cap(com_artigo(pais, "", ap)))
            f += (f" {o_pais} ficou com {nf(V / tot_p * 100, 1)}% das {'exportações' if exp else 'importações'} brasileiras do produto"
                  f" e foi {'o' if exp else 'a'} {pos}{'º destino' if exp else 'ª origem'} no mês.")
        return f
    if exp_princ:
        fr = [frase("export", E, E0, K, K0, True), frase("import", I, I0, KI, KI0, False)]
    else:
        fr = [frase("import", I, I0, KI, KI0, True), frase("export", E, E0, K, K0, False)]
    fr = [x for x in fr if x]
    if not fr:
        fr.append(f"Sem comércio de {esc(nome_d)} com {esc(com_artigo(pais, '', ap))} em {mes_nome(B.ref)}. Veja abaixo os meses anteriores.")

    # números do topo: fluxo principal, volume, preço e (se houver) o outro fluxo; senão, a fatia do país
    V, V0, KG, KG0 = (E, E0, K, K0) if exp_princ else (I, I0, KI, KI0)
    cls = "exp" if exp_princ else "imp"
    tiles = tile(cls, "Exportações" if exp_princ else "Importações", us_sem(V), "US$", chip(V, V0))
    t_kg = KG / 1000
    tiles += tile("", "Volume exportado" if exp_princ else "Volume importado",
                  nf(t_kg, 0) if t_kg >= 10 else nf(t_kg, 1), "t", chip(KG, KG0) if KG0 else '<span class="chg flat">—</span>')
    pr, pr0 = preco(V, KG), preco(V0, KG0)
    if pr:
        v_pr = float(pr[0].replace(".", "").replace(",", "."))
        v_pr0 = float(pr0[0].replace(".", "").replace(",", ".")) if pr0 and pr0[1] == pr[1] else 0
        tiles += tile("", "Preço médio", pr[0], pr[1], chip(v_pr, v_pr0) if v_pr0 else '<span class="chg flat">—</span>')
    else:
        tiles += tile("", "Preço médio", "—", "", '<span class="chg flat">—</span>')
    outro_12 = sum(iv[-12:]) if exp_princ else sum(ev[-12:])
    if outro_12:
        W_, W0_ = (I, I0) if exp_princ else (E, E0)
        tiles += tile("imp" if exp_princ else "exp", "Importações" if exp_princ else "Exportações", us_sem(W_), "US$", chip(W_, W0_))
    else:
        fl_ = "export" if exp_princ else "import"
        tp = (p.get(fl_) or {}).get("fob", 0)
        tp0 = (p.get(fl_) or {}).get("fob_ant", 0)
        sh = V / tp * 100 if tp else 0
        sh0 = V0 / tp0 * 100 if tp0 else 0
        dif = (f'<span class="chg flat">antes {nf(sh0, 1)}%</span>' if tp0 else '<span class="chg flat">—</span>')
        tiles += tile("", f"Fatia {'das exportações' if exp_princ else 'das importações'} do produto", nf(sh, 1), "%", dif)

    # ano a ano
    ar, mr = int(B.ref[:4]), int(B.ref[5:])
    fl_p = "export" if exp_princ else "import"
    def ano_de(fl, a):
        r = reg.get(fl, {})
        if a == ar:
            return r.get("acum", {}).get(str(ar), (0, 0))
        return r.get("ano", {}).get(str(a), (0, 0))
    anos = list(range(2015, ar + 1))
    linhas, vals = [], []
    kg_tot = sum(ano_de(fl_p, a)[1] for a in anos)
    v_tot = sum(ano_de(fl_p, a)[0] for a in anos)
    por_kg = bool(kg_tot) and v_tot / kg_tot * 1000 >= 100_000
    for a in reversed(anos):
        v, kg = ano_de(fl_p, a)
        v0 = (reg.get(fl_p, {}).get("acum", {}).get(str(ar - 1), (0, 0))[0] if a == ar else ano_de(fl_p, a - 1)[0])
        rot = f"{a}*" if (a == ar and mr < 12) else str(a)
        if kg >= 1000:
            pr_a = nf(v / kg, 0) if por_kg else nf(v / kg * 1000, 0)
        else:
            pr_a = "—"
        vol = nf(kg / 1e3, 0) if por_kg else (nf(kg / 1e6, 1) if kg >= 1e5 else nf(kg / 1e6, 2))
        linhas.append(f'<tr><td>{rot}</td><td class="r">{us_sem(v)}<span class="s">{chip(v, v0) if a > 2015 else ""}</span></td>'
                      f'<td class="r">{vol}</td><td class="r">{pr_a}</td></tr>')
    for a in anos:
        vals.append(ano_de(fl_p, a)[0])
    cab = (f'<th>Ano</th><th class="r">{"Exportação" if exp_princ else "Importação"}</th>'
           f'<th class="r">{"Toneladas" if por_kg else "Mil t"}</th><th class="r">{"US$/kg" if por_kg else "US$/t"}</th>')
    nota = (f'<p class="src">Valores em US$ FOB. * {ar}: janeiro a {MESES[mr - 1]}, comparado com o mesmo período de {ar - 1}.</p>'
            if mr < 12 else '<p class="src">Valores em US$ FOB.</p>')
    lin_csv = ["ano;exportacao_us_fob;exportacao_kg;importacao_us_fob;importacao_kg"]
    for a in anos:
        e_, i_ = ano_de("export", a), ano_de("import", a)
        if e_[0] or i_[0]:
            rot_a = f"{a} (jan-{MES_CURTO[mr - 1]})" if (a == ar and mr < 12) else str(a)
            lin_csv.append(f"{rot_a};{round(e_[0])};{round(e_[1])};{round(i_[0])};{round(i_[1])}")
    url_csv = B.url_par(cod, pais)
    B.csv[url_csv] = "\ufeff" + "\r\n".join(lin_csv) + "\r\n"
    nota = nota.replace("</p>", link_csv("comexemnumeros-" + url_csv.strip("/").replace("/", "-") + ".csv") + "</p>", 1)
    graf_anos = svg_anos(anos, vals, "var(--exp)" if exp_princ else "var(--imp)", parcial=mr < 12)
    anual = (f'<div class="card chart"><h2>Ano a ano</h2>'
             + (f'<div role="img" aria-label="Valor por ano">{graf_anos}</div>' if graf_anos else "")
             + f'<div class="scroll"><table><thead><tr>{cab}</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>{nota}</div>')

    # vizinhos: outros destinos do produto e outros produtos para o país
    fl_v = "export" if exp_princ else "import"
    outros_p = [r for r in B.cruz("produto_pais", fl_v, filtro_cod=cod) if r["nome"] != pais][:8]
    outros_c = [r for r in B.cruz("produto_pais", fl_v, filtro_nome=pais) if r["codigo"] != cod][:8]
    tot_prod = (p.get(fl_v) or {}).get("fob", 0)
    tot_pais = ((B.pais.get(slug(pais)) or {}).get(fl_v) or {}).get("fob", 0)
    h_p = f"Outros destinos de {esc(nome_d)}" if exp_princ else f"Outras origens de {esc(nome_d)}"
    h_c = (f"Outros produtos que o Brasil vende {esc(para)}" if exp_princ else f"Outros produtos que o Brasil compra {esc(de_p)}")
    viz = ""
    if outros_p:
        viz += (f'<div class="card"><div class="row-head"><h2>{h_p}</h2><a class="small" href="{p["url"]}">Ver produto →</a></div>'
                f'{tabela(B, outros_p, "pais", tot_prod, urlf=lambda r: B.url_par(cod, r["nome"]))}</div>')
    if outros_c:
        viz += (f'<div class="card"><div class="row-head"><h2>{h_c}</h2><a class="small" href="{B.url_nome("pais", pais)}">Ver país →</a></div>'
                f'{tabela(B, outros_c, "produto", tot_pais, urlf=lambda r: B.url_par(r["codigo"], pais))}</div>')
    viz = f'<div class="cols">{viz}</div>' if outros_p and outros_c else viz

    if exp_princ:
        h1 = f"Exportação de {nome_d} {para}"
    else:
        h1 = f"Importação de {nome_d} {de_p}"
    t = f"{cap(h1)} | Comex em Números"
    if len(t) > 75:
        t = cap(h1)
    if " (SH4" in nome:  # dois SH4 com o mesmo nome curto
        t = f"{cap(h1)} (SH4 {cod})"
    if len(t) > 75:  # nome longo: encurta o produto e mantém o país
        cabeca = "Exportação de " if exp_princ else "Importação de "
        cauda = f" {para}" if exp_princ else f" {de_p}"
        sh = f" (SH4 {cod})"
        t = cabeca + corta(nome_d, max(20, 74 - len(cabeca) - len(cauda) - len(sh))) + cauda + sh
    if exp_princ:
        desc = (f"Em {mes_curto(B.ref)}, o Brasil exportou {us(E)} em {nome_d} {para}{var_par(E, E0)}." if E else
                f"Exportações de {nome_d} {para}: sem embarques em {mes_curto(B.ref)}.")
    else:
        desc = (f"Em {mes_curto(B.ref)}, o Brasil importou {us(I)} em {nome_d} {de_p}{var_par(I, I0)}." if I else
                f"Importações de {nome_d} {de_p}: nada em {mes_curto(B.ref)}.")
    desc = desc_corta(desc + " Toneladas, preço médio, últimos 13 meses e anos desde 2015.")
    c = f"""<div class="card"><span class="eyebrow">Produto e país · SH4 {esc(cod)}</span><h1>{esc(cap(h1))}</h1><p class="lede">{" ".join(fr)}</p>
<p class="small"><a href="{p["url"]}">{esc(cap(nome))}: todos os países →</a> · <a href="{B.url_nome("pais", pais)}">{esc(pais)}: todos os produtos →</a></p></div>
<div class="tiles">{tiles}</div>
{bloco_13(B, ev, iv, E0, E, I0, I, rot_imp=not exp_princ)}
{anual}
{viz}"""
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"{cap(h1)} (SH4 {cod})",
          "description": desc, "url": BASE + url, "inLanguage": "pt-BR", "temporalCoverage": f"2015-01/{B.ref}",
          "isAccessibleForFree": True, "license": LICENCA, "creator": {"@type": "Organization", "name": "Comex em Números", "url": BASE + "/"},
          "isBasedOn": "https://comexstat.mdic.gov.br/"}
    return pagina(B, url, t, desc, c, "/produtos/", ld,
                  migalhas=[("/produtos/", "Produtos"), (p["url"], corta(nome, 30)), (None, pais)])


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


# Sugestões e críticas: a mensagem chega por e-mail via FormSubmit (sem cadastro e sem servidor próprio).
# Para esconder o e-mail do HTML, troque FORM_EMAIL pelo código aleatório que o FormSubmit envia após a ativação.
FORM_EMAIL = "oleoemnumeros@gmail.com"
FORM_JS = """<script>
(function () {
  var f = document.getElementById("sug"); if (!f || !window.fetch) return;
  var msg = document.getElementById("sug-msg"), ok = document.getElementById("enviado"), b = f.querySelector("button");
  try { var r = document.referrer; if (r && new URL(r).host === location.host && r.indexOf("/sugestoes/") < 0) f.elements.pagina.value = r; } catch (e) {}
  f.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (f.elements._honey.value) return;
    b.disabled = true; msg.textContent = "Enviando…";
    var d = {}; new FormData(f).forEach(function (v, k) { if (k !== "_next") d[k] = v; });
    fetch("https://formsubmit.co/ajax/__EMAIL__", {method: "POST", headers: {"Content-Type": "application/json", "Accept": "application/json"}, body: JSON.stringify(d)})
      .then(function (x) { return x.json(); })
      .then(function (j) {
        if (j && (j.success === true || j.success === "true")) { ok.className += " on"; f.hidden = true; ok.focus(); }
        else throw new Error("falhou");
      })
      .catch(function () { b.disabled = false; msg.textContent = "Não foi possível enviar agora. Tente de novo em instantes ou escreva para __EMAIL__."; });
  });
})();
</script>"""


def form_sugestoes(nome_site: str, base: str) -> str:
    """Corpo da página /sugestoes/: formulário com envio sem sair da página e alternativa sem JavaScript."""
    return (
        '<p class="lede">Viu um erro, sentiu falta de um dado ou tem uma ideia? Escreva aqui. Cada mensagem chega ao e-mail do portal e é lida por uma pessoa.</p>'
        '<div class="sug-ok" id="enviado" tabindex="-1" role="status"><strong>Mensagem enviada. Obrigado!</strong>'
        '<p>Lemos todas. Se você deixou um e-mail, a resposta vai para ele.</p></div>'
        f'<form class="sug" id="sug" method="post" action="https://formsubmit.co/{FORM_EMAIL}">'
        '<label>Tipo de mensagem<select name="tipo"><option>Sugestão</option><option>Crítica</option>'
        '<option>Erro em um dado ou página</option><option>Outro assunto</option></select></label>'
        '<label>Sua mensagem<textarea name="mensagem" required minlength="10" maxlength="3000" rows="6" placeholder="Conte o que você viu, sentiu falta ou sugere. Se for um erro, diga a página e o número."></textarea></label>'
        '<label><span>Seu nome <span class="opc">(opcional)</span></span><input name="nome" maxlength="80" autocomplete="name"></label>'
        '<label><span>Seu e-mail, se quiser resposta <span class="opc">(opcional)</span></span><input type="email" name="email" maxlength="120" autocomplete="email"></label>'
        f'<input type="hidden" name="_subject" value="[{esc(nome_site)}] Sugestão ou crítica">'
        '<input type="hidden" name="_template" value="table">'
        f'<input type="hidden" name="_next" value="{base}/sugestoes/#enviado">'
        f'<input type="hidden" name="site" value="{esc(nome_site)}">'
        '<input type="hidden" name="pagina" value="">'
        '<input class="hp" type="text" name="_honey" tabindex="-1" autocomplete="off" aria-hidden="true">'
        '<button type="submit">Enviar mensagem</button>'
        '<p class="sug-msg" id="sug-msg" role="status" aria-live="polite"></p></form>'
        '<p class="small">O envio passa pelo serviço FormSubmit (formsubmit.co), que entrega a mensagem ao e-mail do portal. '
        'Não pedimos cadastro nem guardamos mais nada além do que você escrever. '
        f'Se preferir, escreva direto para <a href="mailto:{FORM_EMAIL}">{FORM_EMAIL}</a>.</p>'
        + FORM_JS.replace("__EMAIL__", FORM_EMAIL))


def pg_sugestoes(B) -> str:
    c = '<div class="card"><span class="eyebrow">Fale com a gente</span><h1>Sugestões e críticas</h1>' + form_sugestoes("Comex em Números", BASE) + "</div>"
    return pagina(B, "/sugestoes/", "Sugestões e críticas | Comex em Números",
                  "Envie uma sugestão, crítica ou correção para o Comex em Números. A mensagem chega por e-mail e é lida por uma pessoa.",
                  c, "/sugestoes/", migalhas=[(None, "Sugestões e críticas")])


def pg_sobre(B) -> str:
    np_ = sum(1 for p in B.prod.values() if (p.get("export") or {}).get("fob"))
    ni = sum(1 for p in B.prod.values() if (p.get("import") or {}).get("fob"))
    c = f"""<div class="card"><span class="eyebrow">Como funciona</span><h1>O Comex Stat, sem precisar saber código NCM</h1>
<p class="lede">Os dados oficiais de comércio exterior do Brasil são públicos e gratuitos, mas difíceis de consultar. O Comex em Números busca cada atualização mensal do MDIC e transforma em páginas prontas, com nomes que as pessoas procuram.</p></div>
<div class="two"><div class="card"><h2>Neste mês</h2><table><tbody>
<tr><td>Produtos exportados (SH4)</td><td class="r">{nf(np_, 0)}</td></tr><tr><td>Produtos importados (SH4)</td><td class="r">{nf(ni, 0)}</td></tr>
<tr><td>Países parceiros</td><td class="r">{nf(len(B.pais), 0)}</td></tr><tr><td>Estados</td><td class="r">{len(B.uf)}</td></tr></tbody></table></div>
<div class="card"><h2>Fonte e método</h2><ul class="plain"><li>Fonte: API do Comex Stat, Secex/MDIC. Valores em US$ FOB.</li><li>Atualização automática no início de cada mês, quando o MDIC publica o mês anterior.</li><li>Variações sempre contra o mesmo mês do ano anterior.</li><li>Produtos na classificação SH4 (posição do Sistema Harmonizado). Os nomes curtos são nossos; o nome oficial aparece em cada página.</li><li>Estado: UF de origem do produto exportado e de destino do importado.</li><li>Porto: unidade da Receita Federal onde a carga foi despachada (porto, aeroporto ou posto de fronteira). Nem sempre é o local físico de embarque. Só ganham página os locais com pelo menos US$ 10 milhões de movimento nos últimos 12 meses.</li><li>Produto e país: página para cada combinação com pelo menos US$ 10 milhões em 12 meses, na exportação ou na importação. Mês a mês a partir de outubro de 2025 (a janela cresce a cada atualização) e totais anuais desde 2015.</li><li>Município: domicílio fiscal da empresa que exportou ou importou (não necessariamente onde a mercadoria foi produzida). Página para os municípios com pelo menos US$ 10 milhões em 12 meses.</li><li>Toda página com série tem o botão "Baixar dados (CSV)", com separador ponto e vírgula, que abre direto no Excel.</li></ul></div></div>"""
    return pagina(B, "/sobre/", "Como funciona | Comex em Números",
                  "Como o Comex em Números transforma os dados oficiais do Comex Stat (Secex/MDIC) em páginas por produto, país, estado e porto.",
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
    # Tenta achar o produto pelo endereço (ex.: /exportacao/desperdicios-de-seda) e redireciona;
    # se não achar, mostra a busca já preenchida.
    js = """<script>
(function(){
  var partes=location.pathname.split("/").filter(Boolean), alvo=partes[partes.length-1]||"";
  var cod=(location.pathname.match(/(?:^|\\/)(\\d{4})(?:-|\\/|$)/)||[])[1];
  if(cod){location.replace("/produto/"+cod+"/");return;}
  if(!alvo)return;
  var q=decodeURIComponent(alvo).replace(/-/g," ");
  var inp=document.getElementById("busca"); if(inp){inp.value=q;}
  fetch("/assets/busca.json").then(function(r){return r.json();}).then(function(lista){
    var s="-"+alvo.toLowerCase();
    var achou=lista.filter(function(p){var u=p[3].split("/")[2]||"";return u.slice(4)===s||u.slice(4).indexOf(s)===0;});
    if(achou.length===1){location.replace(achou[0][3]);return;}
    if(inp){inp.dispatchEvent(new Event("input"));}
  }).catch(function(){});
})();
</script>"""
    return ("""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Página não encontrada | Comex em Números</title><meta name="robots" content="noindex"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/estilo.css"></head>
<body><main><div class="card"><h1>Página não encontrada</h1><p>Este endereço não existe ou mudou. Procure o produto abaixo, <a href="/">volte ao início</a> ou veja <a href="/produtos/">todos os produtos</a>, <a href="/paises/">países</a> e <a href="/municipios/">municípios</a>.</p>
<div class="search"><label for="busca" class="small" style="align-self:center">Buscar</label><input id="busca" type="search" placeholder="Ex.: café, soja, aço" autocomplete="off"></div><div id="busca-res" aria-live="polite"></div></div></main>
<script src="/assets/app.js" defer></script>""" + js + GOAT + "</body></html>")


def redirect(destino: str) -> str:
    return (f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Redirecionando…</title>'
            f'<link rel="canonical" href="{BASE}{destino}"><meta name="robots" content="noindex">'
            f'<meta http-equiv="refresh" content="0; url={destino}"></head><body><a href="{destino}">Continuar</a></body></html>')


# endereços que mudaram de nome: continuam funcionando
RENOMEADOS = {"/porto/campos-dos-goytacazes-rj/": "/porto/porto-do-acu-rj/"}


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
    B.par_url = {k: v for k, v in B.par_url.items() if ativo_prod(B.prod[k[0]])}
    for pasta in ("produto", "pais", "estado", "porto", "municipio", "municipios", "exportacao", "importacao", "produtos", "paises", "estados", "portos", "sobre", "embed", "assets", "resumo"):
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
    escreve("/sugestoes/", pg_sugestoes(B), urls)
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
    if B.mun:
        indice = sorted([r["cidade"], r["uf"], r["url"]] for r in B.mun.values() if r["url"])
        (SAIDA / "municipios").mkdir(parents=True, exist_ok=True)
        (SAIDA / "municipios" / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        escreve("/municipios/", pg_municipios(B), urls)
        for r in B.mun.values():
            if r["url"]:
                escreve(r["url"], pg_municipio(B, r), urls)
    for velho, novo in RENOMEADOS.items():
        escreve(velho, redirect(novo))
    for (cod, pais) in B.par_url:
        escreve(B.par_url[(cod, pais)], pg_par(B, cod, pais), urls)
    for it in B.uf.values():
        escreve(it["url"], pg_lugar(B, "estado", it), urls)
    if B.porto:
        escreve("/portos/", pg_lista(B, "porto"), urls)
        for it in B.porto.values():
            if (it.get("export") or {}).get("fob") or (it.get("import") or {}).get("fob"):
                escreve(it["url"], pg_lugar(B, "porto", it), urls)

    B.arq_urls.write_text(json.dumps(dict(sorted(B.urls.items())), ensure_ascii=False, indent=0), encoding="utf-8")
    (SAIDA / "assets" / "busca.json").write_text(json.dumps(busca, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    hoje = B.d["gerado_em"][:10]
    for u, txt in B.csv.items():
        (SAIDA / u.strip("/") / "dados.csv").write_text(txt, encoding="utf-8")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{BASE}{u}</loc><lastmod>{hoje}</lastmod></url>" for u in urls]
    sm.append("</urlset>")
    (SAIDA / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (SAIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /embed/\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (SAIDA / "404.html").write_text(pg_404(), encoding="utf-8")
    (SAIDA / ".nojekyll").write_text("", encoding="utf-8")
    (SAIDA / "CNAME").write_text(DOMINIO + "\n", encoding="utf-8")
    (SAIDA / "dados.json").unlink(missing_ok=True)
    print(f"Site gerado: {len(urls)} páginas no sitemap ({n_prod} produtos, {len(B.pais)} países, {len(B.uf)} estados, {len(B.porto)} portos, {len(B.par_url)} produto×país, {sum(1 for r in B.mun.values() if r["url"])} municípios).")


if __name__ == "__main__":
    main()
