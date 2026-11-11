# Comex em Números

Exportações e importações do Brasil mês a mês, por produto, país e estado,
com dados oficiais do [Comex Stat](https://comexstat.mdic.gov.br) (Secex/MDIC).

## Como funciona

- `scripts/atualizar.py` — robô que consulta a API do Comex Stat e grava `data/dados.json`.
- `scripts/gerar_site.py` — gera o site estático em `docs/`: uma página por produto (SH4), país e estado, mais sitemap.xml e robots.txt. Estilo em `site/estilo.css`, nomes populares dos produtos em `site/nomes_populares.json`.
- `.github/workflows/atualizar.yml` — roda o robô todo dia do dia 1 ao 12 de cada mês
  (só baixa quando sai um mês novo), quando o código muda, ou pelo botão "Run workflow".

Se algo der errado, o robô grava detalhes em `data/debug.json`.
