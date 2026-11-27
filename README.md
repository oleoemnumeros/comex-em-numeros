# Comex em Números

Exportações e importações do Brasil mês a mês, por produto, país e estado,
com dados oficiais do [Comex Stat](https://comexstat.mdic.gov.br) (Secex/MDIC).

## Como funciona

- `scripts/atualizar.py` — robô que consulta a API do Comex Stat e grava `data/dados.json`.
- `scripts/gerar_site.py` — gera o site estático em `docs/`: uma página por produto (SH4), NCM (8 dígitos), país e estado, mais sitemap.xml e robots.txt. Estilo em `site/estilo.css`, nomes populares dos produtos em `site/nomes_populares.json`.
- `.github/workflows/atualizar.yml` — roda o robô todo dia do dia 1 ao 12 de cada mês
  (só baixa quando sai um mês novo), quando o código muda, ou pelo botão "Run workflow".

Se algo der errado, o robô grava detalhes em `data/debug.json`.

## Páginas de NCM

O robô grava em `data/ncm/` a série mensal por NCM dos últimos 5 anos e os últimos 12 meses por NCM x país e NCM x estado.
Ganham página (`/ncm/<código>/`) as NCMs com pelo menos US$ 5 milhões em 12 meses, somando exportação e importação, até as
2.000 maiores (`NCM_MIN` e `NCM_MAX` em `gerar_site.py`). Cada página tem preço médio por kg, origens, destinos, estados,
série mensal e CSV para baixar. Se a coleta de NCM falhar, o resto do site é gerado normalmente.
