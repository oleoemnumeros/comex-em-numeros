"""Imagem do mês (1200x627) para compartilhar no LinkedIn e no WhatsApp."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTES = Path(__file__).resolve().parent.parent / "site" / "fontes"
EXP, IMP, INK, BG, MUT = (11, 122, 104), (185, 102, 15), (15, 29, 43), (238, 242, 244), (86, 104, 121)
UP, DOWN = (23, 128, 58), (180, 35, 24)


def _f(bold: bool, n: int):
    return ImageFont.truetype(str(FONTES / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), n)


def gera_card(destino: Path, titulo: str, numeros: list[tuple[str, str, str, bool | None]],
              barras: list[tuple[str, float, float]], rodape: str) -> None:
    """numeros: [(rótulo, valor, variação, subiu?)]; barras: [(mês, exp, imp)]."""
    W, H = 1200, 627
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 12], fill=EXP)
    d.text((60, 40), "Comex ", font=_f(True, 34), fill=INK)
    d.text((60 + d.textlength("Comex ", font=_f(True, 34)), 40), "em Números", font=_f(True, 34), fill=EXP)
    d.text((60, 95), titulo, font=_f(True, 46), fill=INK)
    # números
    x = 60
    larg = (W - 120) / len(numeros)
    for rot, val, var, subiu in numeros:
        d.text((x, 175), rot, font=_f(False, 26), fill=MUT)
        d.text((x, 210), val, font=_f(True, 44), fill=INK)
        if var:
            cor = MUT if subiu is None else (UP if subiu else DOWN)
            d.text((x, 268), var, font=_f(True, 24), fill=cor)
        x += larg
    # barras dos últimos meses
    if barras:
        topo, base = 340, H - 70
        mx = max(max(e, i) for _, e, i in barras) or 1
        n = len(barras)
        passo = (W - 120) / n
        bw = passo * 0.34
        for k, (mes, e, i) in enumerate(barras):
            x0 = 60 + k * passo + passo / 2
            for v, cor, dx in ((e, EXP, -bw - 2), (i, IMP, 2)):
                h = (v / mx) * (base - topo)
                d.rounded_rectangle([x0 + dx, base - h, x0 + dx + bw, base], radius=3, fill=cor)
            d.text((x0, base + 8), mes, font=_f(k == n - 1, 18), fill=INK if k == n - 1 else MUT, anchor="mt")
    d.text((60, H - 30), rodape, font=_f(False, 20), fill=MUT, anchor="lm")
    destino.parent.mkdir(parents=True, exist_ok=True)
    im.save(destino, optimize=True)
