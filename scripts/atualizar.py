"""Robô do Comex em Números.

Baixa da API oficial do Comex Stat (Secex/MDIC) os dados do último mês
disponível e do mesmo mês do ano anterior e grava tudo em data/dados.json.

Uso:
    python scripts/atualizar.py            # só baixa se houver mês novo
    FORCAR=1 python scripts/atualizar.py   # baixa de novo mesmo assim

A API limita o número de requisições (HTTP 429). O robô espera entre as
chamadas e tenta de novo quando é bloqueado.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

API = "https://api-comexstat.mdic.gov.br"
RAIZ = Path(__file__).resolve().parent.parent
ARQ_DADOS = RAIZ / "data" / "dados.json"
ARQ_DEBUG = RAIZ / "data" / "debug.json"
PASTA_SERIE = RAIZ / "data" / "serie"
ANO_INICIO = 2015
PAUSA = 4          # segundos entre chamadas
ESPERA_429 = 12    # segundos após bloqueio por excesso de chamadas
TENTATIVAS = 6
UA = "ComexEmNumeros/1.0 (+https://comexemnumeros.com.br)"
VERSAO = 5  # mude quando o formato de data/dados.json mudar: força nova coleta

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

debug: dict = {"consultas": []}
_ssl_ok = True


def log(msg: str) -> None:
    print(msg, flush=True)


def chamar(metodo: str, caminho: str, corpo=None, params=None):
    """Chamada à API com espera, novas tentativas e plano B de SSL."""
    global _ssl_ok
    url = API + caminho
    ultimo = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            r = requests.request(
                metodo, url, json=corpo, params=params, timeout=180,
                verify=_ssl_ok,
                headers={"Accept": "application/json", "User-Agent": UA},
            )
        except requests.exceptions.SSLError as e:
            # Os servidores do governo usam certificados ICP-Brasil, que nem
            # todo sistema reconhece.
            log(f"  aviso: falha de SSL ({e}); tentando sem verificar o certificado")
            _ssl_ok = False
            ultimo = e
            continue
        except requests.RequestException as e:
            ultimo = e
            log(f"  erro de rede (tentativa {tentativa}): {e}")
            time.sleep(ESPERA_429)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            log(f"  HTTP {r.status_code} (tentativa {tentativa}); esperando {ESPERA_429 * tentativa}s")
            time.sleep(ESPERA_429 * tentativa)
            ultimo = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{metodo} {caminho} -> HTTP {r.status_code}: {r.text[:500]}")
        time.sleep(PAUSA)
        return r.json()
    raise RuntimeError(f"{metodo} {caminho} falhou após {TENTATIVAS} tentativas: {ultimo}")


def linhas(resposta) -> list[dict]:
    """Extrai a lista de linhas dos formatos de resposta conhecidos."""
    d = resposta.get("data", resposta) if isinstance(resposta, dict) else resposta
    if isinstance(d, dict) and "list" in d:
        d = d["list"]
    while isinstance(d, list) and len(d) == 1 and isinstance(d[0], list):
        d = d[0]
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    if isinstance(d, dict):
        return [d]
    return []


def num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return float(s.replace(".", "").replace(",", "."))


def mes_da_linha(l: dict) -> tuple[int, int] | None:
    ano = l.get("year") or l.get("ano")
    mes = l.get("monthNumber") or l.get("coMes") or l.get("month") or l.get("mes")
    if ano is None or mes is None:
        return None
    if isinstance(mes, str) and not mes.strip().isdigit():
        m = re.match(r"^\s*(\d{1,2})", mes)
        if m:
            mes = int(m.group(1))
        else:
            mes = MESES_PT.get(mes.strip().lower())
            if mes is None:
                return None
    return int(ano), int(mes)


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:60] or "item"


def rotulo_e_codigo(l: dict, detalhe: str) -> tuple[str, str]:
    """Descobre o nome e o código de um item (produto, país, estado...)."""
    nome = l.get(detalhe)
    codigo = None
    for k, v in l.items():
        kl = k.lower()
        if k == detalhe or kl.startswith("metric") or kl in ("year", "monthnumber", "month"):
            continue
        if detalhe.lower() in kl and ("code" in kl or "id" == kl[-2:]) or kl in (f"co{detalhe.lower()}", f"{detalhe.lower()}code"):
            codigo = v
    nome = str(nome if nome is not None else "").strip()
    m = re.match(r"^\s*(\d{2,8})\s*[-–]\s*(.+)$", nome)
    if m and codigo is None:
        codigo, nome = m.group(1), m.group(2).strip()
    if codigo is None:
        codigo = slug(nome)
    return nome, str(codigo)


def consulta(fluxo: str, de: str, ate: str, detalhes: list[str], por_mes: bool, rotulo: str, rota: str = "/general"):
    corpo = {
        "flow": fluxo,
        "monthDetail": por_mes,
        "period": {"from": de, "to": ate},
        "filters": [],
        "details": detalhes,
        "metrics": ["metricFOB", "metricKG"],
    }
    log(f"- {rotulo}: {fluxo} {de}..{ate} {detalhes or '[total]'}")
    resp = chamar("POST", rota, corpo, params={"language": "pt"})
    ls = linhas(resp)
    debug["consultas"].append({
        "rotulo": rotulo, "rota": rota, "fluxo": fluxo, "periodo": [de, ate], "detalhes": detalhes,
        "n_linhas": len(ls), "exemplo": ls[:3],
    })
    log(f"  {len(ls)} linhas")
    return ls


def ultimo_mes() -> tuple[int, int]:
    try:
        r = chamar("GET", "/general/dates/updated")
        debug["dates_updated"] = r
        d = r.get("data", r) if isinstance(r, dict) else r
        if isinstance(d, list) and d:
            d = d[0]
        if isinstance(d, dict):
            ano = d.get("year") or d.get("ano")
            mes = d.get("monthNumber") or d.get("month") or d.get("mes")
            if ano and mes and str(mes).isdigit():
                return int(ano), int(mes)
            txt = json.dumps(d)
        else:
            txt = str(d)
        m = re.search(r"(20\d{2})[-/](\d{2})", txt)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception as e:  # noqa: BLE001
        log(f"aviso: não consegui ler a data de atualização ({e})")
    # Plano B: procura o mês mais recente com dados.
    hoje = dt.date.today()
    a, m = hoje.year, hoje.month
    for _ in range(4):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        p = f"{a}-{m:02d}"
        if linhas(chamar("POST", "/general", {
            "flow": "export", "monthDetail": True, "period": {"from": p, "to": p},
            "filters": [], "details": [], "metrics": ["metricFOB"],
        }, params={"language": "pt"})):
            return a, m
    raise RuntimeError("não encontrei nenhum mês com dados")


def agrega(ls: list[dict], detalhe: str) -> dict:
    out: dict[str, dict] = {}
    for l in ls:
        nome, cod = rotulo_e_codigo(l, detalhe)
        it = out.setdefault(cod, {"codigo": cod, "nome": nome, "fob": 0.0, "kg": 0.0})
        it["fob"] += num(l.get("metricFOB"))
        it["kg"] += num(l.get("metricKG"))
    return out


def agrega2(ls: list[dict], d1: str, d2: str) -> dict:
    """Soma FOB por (código de d1, nome de d2)."""
    out: dict[tuple, float] = {}
    for l in ls:
        _, cod = rotulo_e_codigo(l, d1)
        nome2 = str(l.get(d2) or "").strip()
        k = (cod, nome2)
        out[k] = out.get(k, 0.0) + num(l.get("metricFOB"))
    return out


def comparar(atual: dict, anterior: dict) -> list[dict]:
    res = []
    for cod in set(atual) | set(anterior):
        a = atual.get(cod, {})
        b = anterior.get(cod, {})
        res.append({
            "codigo": cod,
            "nome": a.get("nome") or b.get("nome") or cod,
            "fob": round(a.get("fob", 0.0)),
            "fob_ant": round(b.get("fob", 0.0)),
            "kg": round(a.get("kg", 0.0)),
            "kg_ant": round(b.get("kg", 0.0)),
        })
    res.sort(key=lambda x: -x["fob"])
    return res


def series_historicas(ano_ref: int, mes_ref: int) -> None:
    """Série mensal por produto, país e estado, um arquivo por ano e fluxo.

    Anos antigos são baixados uma vez só. O ano atual e o anterior são
    baixados de novo sempre que sai um mês novo (o MDIC revisa os dados).
    """
    ref = f"{ano_ref}-{mes_ref:02d}"
    PASTA_SERIE.mkdir(parents=True, exist_ok=True)
    for tipo, detalhe in (("produtos", "heading"), ("paises", "country"), ("estados", "state"), ("portos", "urf")):
        for fluxo in ("export", "import"):
            for ano in range(ANO_INICIO, ano_ref + 1):
                arq = PASTA_SERIE / f"{tipo}_{fluxo}_{ano}.json"
                if arq.exists():
                    try:
                        atual = json.loads(arq.read_text(encoding="utf-8"))
                    except ValueError:
                        atual = {}
                    recente = ano >= ano_ref - 1
                    if not recente or atual.get("ate") == ref:
                        continue
                fim = ref if ano == ano_ref else f"{ano}-12"
                try:
                    ls = consulta(fluxo, f"{ano}-01", fim, [detalhe], True, f"serie_{tipo}")
                except Exception as e:  # noqa: BLE001
                    log(f"  ERRO na série {tipo}/{fluxo}/{ano}: {e}")
                    debug.setdefault("erros", []).append(f"serie {tipo}/{fluxo}/{ano}: {e}")
                    continue
                itens: dict[str, dict] = {}
                for l in ls:
                    am = mes_da_linha(l)
                    if not am or am[0] != ano:
                        continue
                    nome, cod = rotulo_e_codigo(l, detalhe)
                    chave = cod if tipo == "produtos" else nome.replace("\xa0", " ").strip()
                    it = itens.setdefault(chave, {"n": nome.replace("\xa0", " ").strip(), "v": [0] * 12, "k": [0] * 12})
                    it["v"][am[1] - 1] += round(num(l.get("metricFOB")))
                    it["k"][am[1] - 1] += round(num(l.get("metricKG")))
                if tipo != "produtos":
                    for it in itens.values():
                        del it["k"]
                arq.write_text(json.dumps({"ano": ano, "ate": ref, "fluxo": fluxo, "itens": itens},
                                          ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                log(f"  série {tipo}/{fluxo}/{ano}: {len(itens)} itens")


PASTA_PP = RAIZ / "data" / "prodpais"


def _grava_gz(arq: Path, obj: dict) -> None:
    dado = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    arq.write_bytes(gzip.compress(dado, mtime=0))


def _le_gz(arq: Path) -> dict:
    try:
        return json.loads(gzip.decompress(arq.read_bytes()))
    except Exception:  # noqa: BLE001
        return {}


def produto_pais_historico(ano_ref: int, mes_ref: int) -> None:
    """Produto x país: últimos 13 meses (mês a mês), anos fechados desde 2015 e acumulado do ano.

    Arquivos compactados em data/prodpais/. Linhas: [SH4, país, fob, kg].
    Meses e anos antigos são baixados uma vez só; os recentes, de novo a cada mês novo.
    """
    ref = f"{ano_ref}-{mes_ref:02d}"
    PASTA_PP.mkdir(parents=True, exist_ok=True)
    pedidos = []  # (arquivo, de, até, rebaixar_se_desatualizado)
    for i in range(13):
        a, m = divmod((ano_ref * 12 + mes_ref - 1) - i, 12)
        ym = f"{a}-{m + 1:02d}"
        pedidos.append((f"mes_{ym}", ym, ym, i < 3))
    for a in range(ANO_INICIO, ano_ref):
        pedidos.append((f"ano_{a}", f"{a}-01", f"{a}-12", a == ano_ref - 1))
    pedidos.append((f"acum_{ano_ref}", f"{ano_ref}-01", ref, True))
    pedidos.append((f"acum_{ano_ref - 1}", f"{ano_ref - 1}-01", f"{ano_ref - 1}-{mes_ref:02d}", True))
    for fluxo in ("export", "import"):
        for nome, de, ate, recente in pedidos:
            arq = PASTA_PP / f"{fluxo}_{nome}.json.gz"
            if arq.exists():
                atual = _le_gz(arq)
                if atual.get("linhas") and (not recente or atual.get("ref") == ref) and atual.get("ate") == ate:
                    continue
            try:
                ls = consulta(fluxo, de, ate, ["heading", "country"], False, "prodpais")
            except Exception as e:  # noqa: BLE001
                log(f"  ERRO produto x país {fluxo}/{nome}: {e}")
                debug.setdefault("erros", []).append(f"prodpais {fluxo}/{nome}: {e}")
                continue
            soma: dict[tuple, list] = {}
            for l in ls:
                _, cod = rotulo_e_codigo(l, "heading")
                pais = str(l.get("country") or "").replace("\xa0", " ").strip()
                v = soma.setdefault((cod, pais), [0.0, 0.0])
                v[0] += num(l.get("metricFOB"))
                v[1] += num(l.get("metricKG"))
            linhas_ = sorted(([c, p, round(f), round(k)] for (c, p), (f, k) in soma.items() if f >= 1000), key=lambda x: -x[2])
            if not linhas_:
                log(f"  produto x país {fluxo}/{nome}: vazio, não gravei")
                continue
            _grava_gz(arq, {"fluxo": fluxo, "de": de, "ate": ate, "ref": ref, "linhas": linhas_})
            log(f"  produto x país {fluxo}/{nome}: {len(linhas_)} linhas")
    # apaga meses que saíram da janela de 13 meses? Não: ficam, e a série mensal cresce com o tempo.


PASTA_MUN = RAIZ / "data" / "municipios"


def _mun(l: dict) -> tuple[str, str]:
    """(código IBGE, 'Cidade - UF') de uma linha da rota /cities."""
    cod = l.get("coMunGeo") or next((str(v) for k, v in l.items() if k.lower().startswith("comun")), "")
    nome = l.get("noMunMinsgUf") or next((str(v) for k, v in l.items() if k.lower().startswith("nomun")), "")
    return str(cod), str(nome).replace("\xa0", " ").strip()


def municipios(ano_ref: int, mes_ref: int) -> None:
    """Comércio exterior por município (domicílio fiscal de quem exporta ou importa).

    data/municipios/{fluxo}_{tipo}_{período}.json.gz
      rank_AAAA-MM: [cod, nome, fob, kg]   prod_AAAA-MM: [cod, sh4, fob, kg]   pais_AAAA-MM: [cod, país, fob]
      serie_AAAA:   {cod: [fob x 12]}
    """
    ref = f"{ano_ref}-{mes_ref:02d}"
    ant = f"{ano_ref - 1}-{mes_ref:02d}"
    PASTA_MUN.mkdir(parents=True, exist_ok=True)
    pedidos = []
    for ym in (ref, ant):
        pedidos += [("rank", ym, ym, ["city"], False), ("prod", ym, ym, ["city", "heading"], False),
                    ("pais", ym, ym, ["city", "country"], False)]
    for a in range(ANO_INICIO, ano_ref + 1):
        pedidos.append(("serie", f"{a}", None, ["city"], True))
    for fluxo in ("export", "import"):
        for tipo, per, ate, det, por_mes in pedidos:
            if tipo == "serie":
                a = int(per)
                de, ate_ = f"{a}-01", (ref if a == ano_ref else f"{a}-12")
                recente = a >= ano_ref - 1
            else:
                de, ate_ = per, per
                recente = True
            arq = PASTA_MUN / f"{fluxo}_{tipo}_{per}.json.gz"
            if arq.exists():
                atual = _le_gz(arq)
                if atual.get("dados") and (not recente or atual.get("ref") == ref) and atual.get("ate") == ate_:
                    continue
            try:
                ls = consulta(fluxo, de, ate_, det, por_mes, f"mun-{tipo}", rota="/cities")
            except Exception as e:  # noqa: BLE001
                log(f"  ERRO município {fluxo}/{tipo}_{per}: {e}")
                debug.setdefault("erros", []).append(f"municipios {fluxo}/{tipo}_{per}: {e}")
                continue
            if tipo == "serie":
                dados: dict = {}
                for l in ls:
                    cod, nome = _mun(l)
                    m = mes_da_linha(l)
                    if not cod or not m:
                        continue
                    v = dados.setdefault(cod, [nome, [0] * 12])
                    v[1][int(m[1]) - 1] += round(num(l.get("metricFOB")))
            else:
                soma: dict = {}
                for l in ls:
                    cod, nome = _mun(l)
                    if tipo == "rank":
                        k = (cod, nome)
                    elif tipo == "prod":
                        k = (cod, rotulo_e_codigo(l, "heading")[1])
                    else:
                        k = (cod, str(l.get("country") or "").replace("\xa0", " ").strip())
                    v = soma.setdefault(k, [0.0, 0.0])
                    v[0] += num(l.get("metricFOB"))
                    v[1] += num(l.get("metricKG"))
                lim = 0 if tipo == "rank" else 1000
                dados = sorted(([a_, b_, round(f), round(k)] for (a_, b_), (f, k) in soma.items() if f > lim), key=lambda x: -x[2])
                if tipo == "pais":
                    dados = [x[:3] for x in dados]
            if not dados:
                log(f"  município {fluxo}/{tipo}_{per}: vazio. Exemplo: {ls[:1]}")
                continue
            _grava_gz(arq, {"fluxo": fluxo, "de": de, "ate": ate_, "ref": ref, "dados": dados})
            log(f"  município {fluxo}/{tipo}_{per}: {len(dados)} registros")


def main() -> int:
    forcar = os.environ.get("FORCAR") == "1"
    ano, mes = ultimo_mes()
    ref = f"{ano}-{mes:02d}"
    ant = f"{ano - 1}-{mes:02d}"
    log(f"Último mês disponível no Comex Stat: {ref}")

    # Série histórica (só baixa o que falta ou o que mudou)
    series_historicas(ano, mes)
    produto_pais_historico(ano, mes)
    municipios(ano, mes)
    ARQ_DEBUG.parent.mkdir(parents=True, exist_ok=True)
    ARQ_DEBUG.write_text(json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")

    if ARQ_DADOS.exists() and not forcar:
        atual = json.loads(ARQ_DADOS.read_text(encoding="utf-8"))
        if atual.get("mes") == ref and atual.get("versao") == VERSAO:
            log("Os dados já estão atualizados. Nada a fazer.")
            return 0

    dados: dict = {
        "versao": VERSAO,
        "mes": ref,
        "mes_ant": ant,
        "gerado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fonte": "Comex Stat - Secex/MDIC (api-comexstat.mdic.gov.br)",
        "mensal": {},
    }

    # 1) Série mensal (total do Brasil), do início do ano anterior até o mês de referência
    for fluxo in ("export", "import"):
        # A API trata "de/até" como faixa de anos E faixa de meses (jan-out de cada
        # ano, por exemplo). Por isso a busca é feita ano a ano.
        ls = []
        for y in range(ANO_INICIO, ano + 1):
            ls += consulta(fluxo, f"{y}-01", ref if y == ano else f"{y}-12", [], True, "mensal")
        serie: dict[str, dict] = {}
        for l in ls:
            am = mes_da_linha(l)
            if not am:
                continue
            k = f"{am[0]}-{am[1]:02d}"
            s = serie.setdefault(k, {"mes": k, "fob": 0.0, "kg": 0.0})
            s["fob"] += num(l.get("metricFOB"))
            s["kg"] += num(l.get("metricKG"))
        dados["mensal"][fluxo] = [
            {"mes": k, "fob": round(v["fob"]), "kg": round(v["kg"])} for k, v in sorted(serie.items())
        ]

    # 2) Recortes do mês de referência contra o mesmo mês do ano anterior
    recortes = {
        "produtos": "heading",      # SH4
        "paises": "country",
        "estados": "state",
        "setores": "ISICSection",  # Agropecuária, Ind. Extrativa, Ind. de Transformação
        "categorias": "BECLevel1",  # bens de capital, intermediários, consumo, combustíveis
        "portos": "urf",            # unidade da Receita: porto, aeroporto ou fronteira
        "vias": "via",              # modal: marítima, aérea, rodoviária...
    }
    for chave, detalhe in recortes.items():
        dados[chave] = {}
        for fluxo in ("export", "import"):
            try:
                a = agrega(consulta(fluxo, ref, ref, [detalhe], False, chave), detalhe)
                b = agrega(consulta(fluxo, ant, ant, [detalhe], False, chave), detalhe)
                dados[chave][fluxo] = comparar(a, b)
            except Exception as e:  # noqa: BLE001
                log(f"  ERRO em {chave}/{fluxo}: {e}")
                dados[chave][fluxo] = []
                debug.setdefault("erros", []).append(f"{chave}/{fluxo}: {e}")

    # 3) Cruzamentos: produto x país e produto x estado.
    #    Formato compacto: [código SH4, nome do país/estado, fob atual, fob ano anterior]
    dados["cruzado"] = {}
    for chave, detalhe in (("produto_pais", "country"), ("produto_estado", "state"), ("produto_porto", "urf")):
        dados["cruzado"][chave] = {}
        for fluxo in ("export", "import"):
            try:
                a = agrega2(consulta(fluxo, ref, ref, ["heading", detalhe], False, chave), "heading", detalhe)
                b = agrega2(consulta(fluxo, ant, ant, ["heading", detalhe], False, chave), "heading", detalhe)
                linhas_ = []
                for k in set(a) | set(b):
                    fa, fb = a.get(k, 0.0), b.get(k, 0.0)
                    if max(fa, fb) >= 1000:  # ignora fluxos abaixo de US$ 1 mil
                        linhas_.append([k[0], k[1], round(fa), round(fb)])
                linhas_.sort(key=lambda x: -x[2])
                dados["cruzado"][chave][fluxo] = linhas_
                log(f"  {chave}/{fluxo}: {len(linhas_)} combinações")
            except Exception as e:  # noqa: BLE001
                log(f"  ERRO em {chave}/{fluxo}: {e}")
                dados["cruzado"][chave][fluxo] = []
                debug.setdefault("erros", []).append(f"{chave}/{fluxo}: {e}")

    # 4) Acumulado no ano (a partir da série mensal)
    acum = {}
    for fluxo, serie in dados["mensal"].items():
        cur = sum(x["fob"] for x in serie if x["mes"].startswith(f"{ano}-") and x["mes"] <= ref)
        prev = sum(x["fob"] for x in serie if x["mes"].startswith(f"{ano - 1}-") and x["mes"][5:] <= ref[5:])
        acum[fluxo] = {"fob": cur, "fob_ant": prev}
    dados["acumulado"] = acum

    ARQ_DADOS.parent.mkdir(parents=True, exist_ok=True)
    ARQ_DADOS.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ARQ_DEBUG.write_text(json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")

    tot = {f: next((x["fob"] for x in dados["mensal"][f] if x["mes"] == ref), 0) for f in ("export", "import")}
    log(f"OK. {ref}: exportações US$ {tot['export'] / 1e9:.2f} bi, importações US$ {tot['import'] / 1e9:.2f} bi")
    if not tot["export"]:
        log("ERRO: total de exportações zerado; confira data/debug.json")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        ARQ_DEBUG.parent.mkdir(parents=True, exist_ok=True)
        debug["erro_fatal"] = str(e)
        ARQ_DEBUG.write_text(json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"ERRO FATAL: {e}")
        sys.exit(1)
