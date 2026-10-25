# UNAS: Pesquisa sobre Estresse Térmico em Heliópolis
## Requisitos
RF
- Extrair dados das APIs públicas via REST
- Limpar as bases (valores ausentes, outliers, padronização de unidades e timestamps)
- Cruzar variáveis
- Calcular índices de estresse térmico a partir de variáveis brutas
- Gerar análises exploratórias (correlações, séries temporais, distribuições)
- Disponibilizar dashboards interativos com filtros por período e recorte territorial
- Permitir exportação dos resultados (relatórios/gráficos) para uso comunitário
  
RNF
- Compartilhamento de conhecimento com a ONG
- Acessibilidade (resultados apresentados em linguagem clara e visual)
- Reprodutibilidade (ambiente virtualizado em Docker e versionamento em Git)
- Manutenibilidade(código comentado e documentado)
- Confiabilidade dos dados (rastreabilidade da origem e validação de qualidade das bases)
- Escalabilidade (arquitetura que comporte novos sensores e novas fontes de dados)
- Sustentabilidade (documentação de operação e garantia de continuidade sem
dependência da equipe original)

## Como rodar
```
pip install -r requirements.txt
streamlit run app.py
```

## Dados e métodos

### Fontes
- [INMET](https://portal.inmet.gov.br/dadoshistoricos): temperatura e umidade
- [IBGE Censo 2022](https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/): população de Heliópolis
- [DATASUS](https://datasus.saude.gov.br/transferencia-de-arquivos/): óbitos e internações
- [CETESB](https://qualar.cetesb.sp.gov.br/qualar/home.do): poluição
- [Open-Meteo](https://open-meteo.com): clima e poluição por modelo

Período: 01/12/2025 a 31/03/2026 (`PERIODO` em `src/etl_api.py`).

### Limpeza (`src/limpeza.py`)
- Timestamps padronizados; °F convertido para °C.
- Fora de -5 a 50 °C ou 0 a 100% de umidade vira ausente.
- Lacunas de até 3 h interpoladas por sensor; duplicatas removidas.
- Horas sem medição do INMET (34 no período) preenchidas com Open-Meteo, marcadas em `preenchido_modelo`.
- Cada execução de `python -m src.pipeline` grava `data/processed/relatorio_qualidade.json`.

### Índices (`src/indices.py`)
- **Índice de calor**: NWS (Rothfusz, 1990). Alerta a partir de 27 °C, cautela extrema a partir de 32 °C.
- **WBGT aproximado**: bulbo úmido de Stull (2011), sem sensor de globo.

### Limitações
- Estações a 13–15 km, não dentro de Heliópolis.
- WBGT sem globo é estimativa.
- Saúde no nível do município.
