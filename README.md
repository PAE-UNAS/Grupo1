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
Testes: `python -m pytest`. ETL sem o painel: `python -m meteo.pipeline`.

## Abas do painel
- **Estresse térmico**: índice de calor, WBGT e faixas de risco hora a hora (INMET), com poluição.
- **O calor está aumentando?**: dias de calor por ano desde 1991 (Open-Meteo).
- **População exposta**: moradores, densidade e idade (Censo 2022).
- **Calor e internações**: internações de urgência em Heliópolis, região do Ipiranga e cidade.

## Dados e métodos

### Fontes
- [INMET](https://portal.inmet.gov.br/dadoshistoricos): temperatura e umidade por hora
- [Open-Meteo](https://open-meteo.com): clima diário desde 1991 e poluição por modelo
- [IBGE Censo 2022](https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/): população de Heliópolis
- [DATASUS](https://datasus.saude.gov.br/transferencia-de-arquivos/): internações (SIH)
- [CETESB](https://qualar.cetesb.sp.gov.br/qualar/home.do): poluição medida

### Recortes
- **Heliópolis**: CEP de residência 04229, 04230, 04231, 04233, 04235, 04236 ou 04239.
- **Região do Ipiranga**: CEP começando com 042 (inclui Heliópolis).
- **Cidade de SP**: todos os residentes.

### Limpeza (`meteo/limpeza.py`)
- Timestamps padronizados; °F convertido para °C.
- Fora de -5 a 50 °C ou 0 a 100% de umidade vira ausente.
- Lacunas de até 3 h interpoladas por sensor; duplicatas removidas.
- Horas sem medição do INMET preenchidas com Open-Meteo, marcadas em `preenchido_modelo`.
- `python -m meteo.pipeline` grava `data/processed/relatorio_qualidade.json`.

### Índices e critérios
- **Índice de calor**: NOAA (Rothfusz). Alerta a partir de 27 °C, cautela extrema a partir de 32 °C.
- **WBGT aproximado**: bulbo úmido de Stull (2011), sem sensor de globo.
- **Dia de calor**: sensação térmica máxima entre os 10% mais altos dos verões de 1991–2020.
  Também noite quente (mínima) e onda de calor (3+ dias seguidos).
- **Internações**: cada dia comparado ao normal do mesmo mês (dias sem calor, peso do dia da
  semana), sem feriados. Intervalo de 95%.

Parâmetros em `meteo/config.py`.

### Sensores da UNAS
Colocar CSVs em `data/sensores/` com `sensor_id, timestamp, temperatura, umidade, unidade_temp`.
Com eles, a aba de estresse térmico usa os sensores no lugar do INMET.

### Limitações
- Estações do INMET a 13–15 km, não dentro de Heliópolis.
- Open-Meteo é modelo, não medição.
- WBGT sem globo é estimativa.
- Heliópolis tem poucas internações por dia; a região do Ipiranga dá uma estimativa mais estável.
