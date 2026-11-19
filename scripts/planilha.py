"""Planilha mensal grátis do Comex em Números (versão simples).

Uso: python scripts/planilha.py [saída.xlsx]
Lê os mesmos dados do site (data/) e monta um .xlsx com abas organizadas.
Variações, saldos, participações e preços médios são fórmulas, para quem quiser mexer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gerar_site as g  # noqa: E402

FONTE = "Arial"
AZUL = "0B7A68"
F_TIT = Font(name=FONTE, size=14, bold=True, color=AZUL)
F_CAB = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
F_TXT = Font(name=FONTE, size=10)
F_NEG = Font(name=FONTE, size=10, bold=True)
F_NOTA = Font(name=FONTE, size=9, italic=True, color="666666")
F_LINK = Font(name=FONTE, size=10, color="0563C1", underline="single")
P_CAB = PatternFill("solid", fgColor=AZUL)
P_TOT = PatternFill("solid", fgColor="E8F3F1")
LINHA = Border(bottom=Side(style="thin", color="CCCCCC"))
N0 = '#,##0;-#,##0;"-"'
PCT = '0.0%;-0.0%;"-"'
SITE = "https://comexemnumeros.com.br"


def mes_txt(ym: str) -> str:
    return f"{g.MESES[int(ym[5:]) - 1]} de {ym[:4]}"


def mc(ym: str) -> str:
    return f"{g.MES_CURTO[int(ym[5:]) - 1]}/{ym[2:4]}"


def cabecalho(ws, titulo: str, subtitulo: str, colunas: list[tuple[str, int]], linha: int = 4):
    ws["A1"] = titulo
    ws["A1"].font = F_TIT
    ws["A2"] = subtitulo
    ws["A2"].font = F_NOTA
    for j, (nome, larg) in enumerate(colunas, 1):
        c = ws.cell(row=linha, column=j, value=nome)
        c.font, c.fill = F_CAB, P_CAB
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = larg
    ws.row_dimensions[linha].height = 32
    ws.freeze_panes = ws.cell(row=linha + 1, column=1)
    ws.sheet_view.showGridLines = False


def fmt_linha(ws, r: int, formatos: list[str | None]):
    for j, f in enumerate(formatos, 1):
        c = ws.cell(row=r, column=j)
        c.font = F_TXT
        c.border = LINHA
        if f:
            c.number_format = f


def nota(ws, r: int, texto: str):
    ws.cell(row=r, column=1, value=texto).font = F_NOTA


def aba_ranking(wb, titulo, sub, rotulo, linhas, ref, ant, com_kg=False, codigo=None, extra=None):
    """linhas: dicts com nome, fob, fob_ant (e kg, kg_ant se com_kg). Variação, fatia e preço por fórmula."""
    ws = wb.create_sheet(titulo[:31])
    cols = [("#", 5)] + ([(codigo, 9)] if codigo else []) + ([(extra, 6)] if extra else []) + [(rotulo, 46),
            (f"US$ FOB {mc(ref)}", 16), (f"US$ FOB {mc(ant)}", 16), ("Variação", 10), ("Fatia do total", 10)]
    if com_kg:
        cols += [(f"Peso líquido (kg) {mc(ref)}", 17), (f"Peso líquido (kg) {mc(ant)}", 17), ("Var. do peso", 10),
                 (f"Preço médio US$/t {mc(ref)}", 14), (f"Preço médio US$/t {mc(ant)}", 14)]
    cabecalho(ws, titulo, sub, cols)
    ini = 5
    n = len(linhas)
    fim = ini + n - 1
    k = 1 + (1 if codigo else 0) + (1 if extra else 0)  # colunas antes do nome
    cv, ca = get_column_letter(k + 2), get_column_letter(k + 3)
    for i, r in enumerate(linhas):
        lr = ini + i
        vals = [i + 1] + ([r.get("codigo")] if codigo else []) + ([r.get("extra")] if extra else []) + [r["nome"], round(r["fob"]), round(r["fob_ant"])]
        for j, v in enumerate(vals, 1):
            ws.cell(row=lr, column=j, value=v)
        ws.cell(row=lr, column=k + 4, value=f'=IF({ca}{lr}>0,{cv}{lr}/{ca}{lr}-1,"")')
        ws.cell(row=lr, column=k + 5, value=f"=IF({cv}${fim + 1}>0,{cv}{lr}/{cv}${fim + 1},0)")
        fm = [None] * (k + 1) + [N0, N0, PCT, PCT]
        if com_kg:
            kc, ka = get_column_letter(k + 6), get_column_letter(k + 7)
            ws.cell(row=lr, column=k + 6, value=round(r.get("kg", 0)))
            ws.cell(row=lr, column=k + 7, value=round(r.get("kg_ant", 0)))
            ws.cell(row=lr, column=k + 8, value=f'=IF({ka}{lr}>0,{kc}{lr}/{ka}{lr}-1,"")')
            ws.cell(row=lr, column=k + 9, value=f'=IF({kc}{lr}>=1000,{cv}{lr}/{kc}{lr}*1000,"")')
            ws.cell(row=lr, column=k + 10, value=f'=IF({ka}{lr}>=1000,{ca}{lr}/{ka}{lr}*1000,"")')
            fm += [N0, N0, PCT, N0, N0]
        fmt_linha(ws, lr, fm)
    t = fim + 1
    ws.cell(row=t, column=k + 1, value="Total")
    for col in (k + 2, k + 3) + ((k + 6, k + 7) if com_kg else ()):
        L = get_column_letter(col)
        ws.cell(row=t, column=col, value=f"=SUM({L}{ini}:{L}{fim})")
    ws.cell(row=t, column=k + 4, value=f'=IF({ca}{t}>0,{cv}{t}/{ca}{t}-1,"")')
    ws.cell(row=t, column=k + 5, value=f"=IF({cv}{t}>0,1,0)")
    if com_kg:
        kc, ka = get_column_letter(k + 6), get_column_letter(k + 7)
        ws.cell(row=t, column=k + 8, value=f'=IF({ka}{t}>0,{kc}{t}/{ka}{t}-1,"")')
    for j in range(1, len(cols) + 1):
        c = ws.cell(row=t, column=j)
        c.font, c.fill = F_NEG, P_TOT
    for j, f in enumerate([None] * (k + 1) + [N0, N0, PCT, PCT] + ([N0, N0, PCT] if com_kg else []), 1):
        if f:
            ws.cell(row=t, column=j).number_format = f
    ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{fim}"
    nota(ws, t + 2, "Valores em dólares FOB (sem frete e seguro). Variação contra o mesmo mês do ano anterior. "
                    "Fonte: Comex Stat (Secex/MDIC). Organizado por Comex em Números, licença CC BY 4.0.")
    return ws


def main():
    saida = Path(sys.argv[1]) if len(sys.argv) > 1 else g.RAIZ / "planilha.xlsx"
    d = json.loads((g.RAIZ / "data" / "dados.json").read_text(encoding="utf-8"))
    B = g.Base(d)
    ref, ant = B.ref, B.ant
    wb = Workbook()

    # ---------------- Leia-me
    ws = wb.active
    ws.title = "Leia-me"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 92
    ws["A1"] = f"Comércio exterior do Brasil · {mes_txt(ref)}"
    ws["A1"].font = Font(name=FONTE, size=16, bold=True, color=AZUL)
    ws["A2"] = "Planilha mensal grátis do Comex em Números, com os dados oficiais organizados e prontos para usar."
    ws["A2"].font = F_TXT
    linhas = [
        ("Fonte", "Comex Stat, da Secretaria de Comércio Exterior (Secex/MDIC). Dados públicos."),
        ("Mês de referência", f"{mes_txt(ref)}, comparado com {mes_txt(ant)}."),
        ("Atualização", f"Gerada em {B.d.get('gerado_em', '')[:10]}. Nova edição todo mês, quando a Secex divulga os dados."),
        ("Moeda", "Dólares (US$) FOB: valor da mercadoria no embarque, sem frete e seguro."),
        ("Fórmulas", "Variações, saldos, fatias e preços médios são fórmulas: dá para filtrar, ordenar e reaproveitar."),
        ("Licença", "CC BY 4.0: pode usar e compartilhar, citando \"Comex em Números\" e o Comex Stat."),
        ("Mais detalhes", SITE + " (gráficos, série desde 2015 e páginas por produto, país, estado, município e porto)."),
        ("", ""),
        ("Abas", ""),
        ("Resumo", "Exportação, importação, saldo e corrente de comércio no mês e no acumulado do ano."),
        ("Série mensal", "Totais do Brasil mês a mês desde janeiro de 2015."),
        ("Exportação por produto", "Todos os produtos exportados (SH4), com peso e preço médio."),
        ("Importação por produto", "Todos os produtos importados (SH4), com peso e preço médio."),
        ("Países", "Exportação, importação e saldo com cada país."),
        ("Estados", "Exportação e importação por estado."),
        ("Municípios", "Exportação e importação por município (domicílio fiscal da empresa)."),
        ("Portos", "Por onde as mercadorias saem e entram: portos, aeroportos e fronteiras."),
        ("Transporte", "Valor por meio de transporte (marítimo, aéreo, rodoviário...)."),
        ("", ""),
        ("Atenção", "Município = domicílio fiscal de quem exporta ou importa, nem sempre onde a mercadoria é produzida. "
                    "Porto = unidade da Receita onde a carga foi despachada. Preço médio = valor ÷ peso; mudanças de mix dentro do SH4 também o afetam."),
    ]
    for i, (a, b) in enumerate(linhas, 4):
        ws.cell(row=i, column=1, value=a).font = F_NEG
        c = ws.cell(row=i, column=2, value=b)
        c.font = F_TXT
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws["B10"].hyperlink = SITE
    ws["B10"].font = F_LINK

    # ---------------- Resumo
    ws = wb.create_sheet("Resumo")
    cabecalho(ws, f"Resumo · {mes_txt(ref)}", "US$ FOB. Saldo e corrente são fórmulas sobre exportação e importação.",
              [("Indicador", 30), (mc(ref), 18), (mc(ant), 18), ("Variação", 11)])
    E, E0, I, I0 = B.tot("export", ref), B.tot("export", ant), B.tot("import", ref), B.tot("import", ant)
    ar = int(ref[:4])
    acum = {fl: [sum(x["fob"] for x in d["mensal"][fl] if x["mes"][:4] == str(a) and x["mes"][5:] <= ref[5:]) for a in (ar, ar - 1)]
            for fl in ("export", "import")}
    rows = [("Exportação", E, E0), ("Importação", I, I0), ("Saldo (exportação − importação)", "=B5-B6", "=C5-C6"),
            ("Corrente de comércio (exp. + imp.)", "=B5+B6", "=C5+C6")]
    for i, (a, b, c) in enumerate(rows, 5):
        ws.cell(row=i, column=1, value=a)
        ws.cell(row=i, column=2, value=round(b) if isinstance(b, float) else b)
        ws.cell(row=i, column=3, value=round(c) if isinstance(c, float) else c)
        ws.cell(row=i, column=4, value=f'=IF(C{i}>0,B{i}/C{i}-1,"")')
        fmt_linha(ws, i, [None, N0, N0, PCT])
    ws.cell(row=10, column=1, value=f"Acumulado do ano (jan–{g.MES_CURTO[int(ref[5:]) - 1]})").font = F_NEG
    for j, t in enumerate(["Indicador", str(ar), str(ar - 1), "Variação"], 1):
        c = ws.cell(row=11, column=j, value=t)
        c.font, c.fill = F_CAB, P_CAB
    rows = [("Exportação", acum["export"][0], acum["export"][1]), ("Importação", acum["import"][0], acum["import"][1]),
            ("Saldo", "=B12-B13", "=C12-C13"), ("Corrente de comércio", "=B12+B13", "=C12+C13")]
    for i, (a, b, c) in enumerate(rows, 12):
        ws.cell(row=i, column=1, value=a)
        ws.cell(row=i, column=2, value=round(b) if isinstance(b, float) else b)
        ws.cell(row=i, column=3, value=round(c) if isinstance(c, float) else c)
        ws.cell(row=i, column=4, value=f'=IF(C{i}>0,B{i}/C{i}-1,"")')
        fmt_linha(ws, i, [None, N0, N0, PCT])
    nota(ws, 17, "Fonte: Comex Stat (Secex/MDIC). Organizado por Comex em Números.")

    # ---------------- Série mensal
    ws = wb.create_sheet("Série mensal")
    cabecalho(ws, "Série mensal desde 2015", "US$ FOB e peso líquido. Saldo e corrente são fórmulas.",
              [("Mês", 10), ("Exportação US$", 17), ("Importação US$", 17), ("Saldo US$", 17), ("Corrente US$", 17),
               ("Exportação kg", 18), ("Importação kg", 18)])
    ex = {x["mes"]: x for x in d["mensal"]["export"]}
    im = {x["mes"]: x for x in d["mensal"]["import"]}
    for i, m in enumerate(sorted(set(ex) | set(im)), 5):
        ws.cell(row=i, column=1, value=m)
        ws.cell(row=i, column=2, value=round(ex.get(m, {}).get("fob", 0)))
        ws.cell(row=i, column=3, value=round(im.get(m, {}).get("fob", 0)))
        ws.cell(row=i, column=4, value=f"=B{i}-C{i}")
        ws.cell(row=i, column=5, value=f"=B{i}+C{i}")
        ws.cell(row=i, column=6, value=round(ex.get(m, {}).get("kg", 0)))
        ws.cell(row=i, column=7, value=round(im.get(m, {}).get("kg", 0)))
        fmt_linha(ws, i, [None, N0, N0, N0, N0, N0, N0])
    ws.auto_filter.ref = f"A4:G{i}"

    # ---------------- Produtos
    for fl, tit in (("export", "Exportação por produto"), ("import", "Importação por produto")):
        lst = []
        for r in B.lista("produtos", fl):
            p = B.prod.get(r["codigo"], {})
            lst.append({"codigo": r["codigo"], "nome": (p.get("curto") or r["nome"]).split(" (SH4")[0], "fob": r["fob"],
                        "fob_ant": r["fob_ant"], "kg": r.get("kg", 0), "kg_ant": r.get("kg_ant", 0)})
        lst.sort(key=lambda x: -x["fob"])
        aba_ranking(wb, tit, f"Todos os produtos com movimento em {mc(ref)} ou {mc(ant)}, pela posição SH4 (4 dígitos do Sistema Harmonizado).",
                    "Produto", lst, ref, ant, com_kg=True, codigo="SH4")

    # ---------------- Países (exp e imp lado a lado)
    def lado_a_lado(titulo, sub, rotulo, chave, filtro=lambda n: True, extra=None, linhas_ext=None):
        ws = wb.create_sheet(titulo)
        cols = [(rotulo, 34)] + ([(extra, 6)] if extra else []) + [
            (f"Exportação {mc(ref)}", 16), (f"Exportação {mc(ant)}", 16), ("Var. exp.", 9),
            (f"Importação {mc(ref)}", 16), (f"Importação {mc(ant)}", 16), ("Var. imp.", 9),
            (f"Saldo {mc(ref)}", 16), (f"Corrente {mc(ref)}", 16)]
        cabecalho(ws, titulo, sub, cols)
        if linhas_ext is None:
            reg = {}
            for fl in ("export", "import"):
                for r in B.lista(chave, fl):
                    if filtro(r["nome"]):
                        reg.setdefault(r["nome"], {})[fl] = r
            linhas_ext = [(n, None, v.get("export", {}), v.get("import", {})) for n, v in reg.items()]
        linhas_ext.sort(key=lambda x: -((x[2].get("fob") or 0) + (x[3].get("fob") or 0)))
        o = 1 if extra else 0
        L = lambda c: get_column_letter(c + o)  # noqa: E731
        for i, (nome, ex_, e, im_) in enumerate(linhas_ext, 5):
            ws.cell(row=i, column=1, value=nome)
            if extra:
                ws.cell(row=i, column=2, value=ex_)
            ws.cell(row=i, column=2 + o, value=round(e.get("fob") or 0))
            ws.cell(row=i, column=3 + o, value=round(e.get("fob_ant") or 0))
            ws.cell(row=i, column=4 + o, value=f'=IF({L(3)}{i}>0,{L(2)}{i}/{L(3)}{i}-1,"")')
            ws.cell(row=i, column=5 + o, value=round(im_.get("fob") or 0))
            ws.cell(row=i, column=6 + o, value=round(im_.get("fob_ant") or 0))
            ws.cell(row=i, column=7 + o, value=f'=IF({L(6)}{i}>0,{L(5)}{i}/{L(6)}{i}-1,"")')
            ws.cell(row=i, column=8 + o, value=f"={L(2)}{i}-{L(5)}{i}")
            ws.cell(row=i, column=9 + o, value=f"={L(2)}{i}+{L(5)}{i}")
            fmt_linha(ws, i, [None] * (1 + o) + [N0, N0, PCT, N0, N0, PCT, N0, N0])
        fim = 4 + len(linhas_ext)
        t = fim + 1
        ws.cell(row=t, column=1, value="Total")
        for c in (2, 3, 5, 6, 8, 9):
            ws.cell(row=t, column=c + o, value=f"=SUM({L(c)}5:{L(c)}{fim})")
        ws.cell(row=t, column=4 + o, value=f'=IF({L(3)}{t}>0,{L(2)}{t}/{L(3)}{t}-1,"")')
        ws.cell(row=t, column=7 + o, value=f'=IF({L(6)}{t}>0,{L(5)}{t}/{L(6)}{t}-1,"")')
        for j in range(1, len(cols) + 1):
            c = ws.cell(row=t, column=j)
            c.font, c.fill = F_NEG, P_TOT
        for j, f in enumerate([None] * (1 + o) + [N0, N0, PCT, N0, N0, PCT, N0, N0], 1):
            if f:
                ws.cell(row=t, column=j).number_format = f
        ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{fim}"
        nota(ws, t + 2, "US$ FOB. Variação contra o mesmo mês do ano anterior. Fonte: Comex Stat (Secex/MDIC). Organizado por Comex em Números, CC BY 4.0.")

    lado_a_lado("Países", "Comércio do Brasil com cada país. Saldo positivo = o Brasil vendeu mais do que comprou.", "País", "paises")
    lado_a_lado("Estados", "Estado de origem da exportação e de destino da importação.", "Estado", "estados")
    mun = []
    for r in B.mun.values():
        e, i_ = r.get("export") or {}, r.get("import") or {}
        if (e.get("fob") or 0) + (e.get("fob_ant") or 0) + (i_.get("fob") or 0) + (i_.get("fob_ant") or 0) > 0:
            mun.append((r["cidade"], r["uf"], e, i_))
    lado_a_lado("Municípios", "Domicílio fiscal da empresa que exportou ou importou (nem sempre onde a mercadoria é produzida).",
                "Município", None, extra="UF", linhas_ext=mun)
    lado_a_lado("Portos", "Unidade da Receita Federal onde a carga foi despachada: porto, aeroporto ou posto de fronteira.",
                "Porto ou local", "portos")
    lado_a_lado("Transporte", "Meio de transporte da mercadoria.", "Meio de transporte", "vias")

    for w in wb.worksheets:
        w.sheet_properties.tabColor = AZUL if w.title in ("Leia-me", "Resumo") else None
        w.page_setup.orientation = "landscape"
    wb.properties.creator = "Comex em Números"
    wb.properties.title = f"Comércio exterior do Brasil · {mes_txt(ref)}"
    wb.save(saida)
    print(saida)


if __name__ == "__main__":
    main()
