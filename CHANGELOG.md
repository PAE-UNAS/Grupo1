# Changelog

## [2026-10-19 · 3] Documentação e exportação de gráficos

### Adicionado
- `docs/COMO_USAR.md`: guia para a equipe e a ONG. Cobre instalação no Windows, como abrir o
  painel, a barra lateral e as abas, como ler os gráficos, 6 roteiros prontos, como salvar
  gráficos e dados, como colocar os dados dos sensores (inclusive pelo Excel), cuidados de
  interpretação e uma tabela de problemas comuns.
- `docs/DOCUMENTACAO_TECNICA.md`: arquitetura (diagrama), fluxo de dados, todas as funções de
  `meteo/`, formato das tabelas, métodos estatísticos com fórmulas, parâmetros do `config.py`,
  cache, como estender (novo grupo, recorte, critério, variável, gráfico), testes, Docker e
  limitações.
- README: links para a documentação no topo.

### Corrigido
- **Os gráficos não podiam ser baixados como imagem**: a barra do Plotly estava desligada.
  Agora há um botão de câmera (PNG em alta resolução), o único da barra.
- README: o comando de execução passou a ser `python -m streamlit run app.py`, com o aviso
  para não usar `python app.py`.

## [2026-10-19 · 2] Análises dos sensores (com dados simulados) e arboviroses

### Adicionado

**Sensores da UNAS com dados simulados** (`meteo/sensores.py`, `meteo/config.py`)
- `simular()`: leituras horárias **fictícias** de 3 sensores (`heliopolis_viela_01`,
  `heliopolis_laje_02`, `ipiranga_controle_01`) no último verão, a partir da Open-Meteo. Inclui
  erros de propósito (valores impossíveis, lacunas, um sensor em °F) para exercitar a limpeza.
- `obter()`: ponto único de entrada. Dados reais em `data/sensores/` têm prioridade; sem eles,
  usa a simulação (se `SENSORES_PLACEHOLDER = True`).
- Quadro "COMO TROCAR OS DADOS SIMULADOS PELOS DADOS REAIS" no topo de `meteo/sensores.py` e
  comentários `>>> PARA USAR OS DADOS REAIS <<<` em `meteo/config.py`.
- Novos parâmetros: `SENSORES_PLACEHOLDER`, `PREFIXO_SENSOR_HELIOPOLIS` e `PLACEHOLDER_EXCESSO`.

**Novas análises dos sensores**
- **Calibração** (`calibrar`): diferença média entre os sensores de Heliópolis e a Open-Meteo
  na máxima e na mínima (mínimo de 14 dias).
- **Série "Heliópolis corrigida"** (`corrigir`): Open-Meteo desde 1991 + a diferença medida.
  Os limiares continuam os da Open-Meteo (`clima.marcar_calor(..., lim=...)`).
- **Horas por dia em cada faixa de risco** (`horas_em_risco`), com o intervalo entre leituras
  descoberto sozinho.
- **Perfil de 24 horas** (`perfil_horario`), para ver se a noite esfria.

**Arboviroses** (`meteo/saude.py`, `meteo/cruzamento.py`)
- Grupo **Dengue, chikungunya e zika** (CID A90–A92).
- `arboviroses_mensal()`: internações por mês × temperatura média e chuva de 0, 1 e 2 meses
  antes (Spearman).

**Painel** (`app.py`)
- Barra lateral: **Fonte do clima**, com as opções Open-Meteo e Heliópolis corrigida pelos
  sensores. A segunda refaz todas as análises e é marcada "(SIMULADO)" quando for o caso.
- Aba Clima: com a série corrigida, as barras mostram a série corrigida e uma linha mostra a
  Open-Meteo original.
- Aba Internações: seção **Dengue, chikungunya e zika × temperatura**, com barras de
  correlação por defasagem e um painel duplo mês a mês.
- Aba Sensores reescrita:
  - aviso "DADOS SIMULADOS" e instruções de troca;
  - indicadores de qualidade;
  - índice de calor diário;
  - **calibração** (indicadores e dispersão);
  - **horas em risco**;
  - **"A noite esfria?"**.
- Aviso de dados simulados também no topo da página quando a série corrigida está em uso.

**Testes**: 2 novos testes (simulação + calibração; grupo de arboviroses), 7 no total.

### Alterado
- O grupo de arboviroses não aparece no seletor de "Tipo de internação"
  (`saude.GRUPOS_DIARIOS`), porque a análise diária de dias de calor não se aplica a ele.
- `cruzamento.analisar()` aceita `limiares=` para fixar a régua de calor.
- README: seções de troca dos dados simulados, série corrigida, novos gráficos e limitações.

### Removido
- Nenhum gráfico foi removido.

## [2026-10-19 · 1] Recortes regionais, novos indicadores de calor, sensores e documentação

Branch: `feat-calor-x-internacoes`. 15 arquivos alterados (+1.338 / −346 linhas).

### Adicionado

**Recortes territoriais**
- Novo recorte **Região do Ipiranga** (CEPs que começam com 042, incluindo Heliópolis).
  Ele funciona como indicador indireto de Heliópolis, que tem poucas internações por dia.
- O recorte "Resto de SP" foi substituído por **Cidade de SP** (todos os residentes),
  usada como referência. Os três recortes são aninhados: Heliópolis ⊂ região ⊂ cidade.
- Os municípios lidos do SIH agora são configuráveis (`MUNICIPIOS`), o que permite
  incluir São Caetano do Sul no futuro.

**Indicadores de calor** (`meteo/clima.py`)
- Três critérios de calor, escolhidos na barra lateral:
  - **dia quente**: sensação térmica máxima;
  - **noite quente**: temperatura mínima;
  - **onda de calor**: 3 ou mais dias quentes seguidos.
- O limiar passa a vir do **período de referência 1991–2020** (percentil 90 dos verões,
  padrão da OMM). Antes ele era calculado sobre os anos escolhidos. Assim, "dia de calor"
  significa a mesma coisa em qualquer ano.
- Novas funções de tendência: `resumo_anual`, `tendencia`, `por_decada` e `mapa_ano_mes`.
- Se a Open-Meteo estiver fora do ar, o app usa o último download salvo.

**Grupos de internação** (`meteo/saude.py`)
- Três grupos novos:
  - **Diarreia e gastroenterite** (CID A00–A09);
  - **Crianças de 0 a 9 anos**;
  - **Internações que terminaram em morte** (coluna `MORTE`, que já era baixada mas não
    era usada).
- A escolha dos grupos se baseia no estudo Fiocruz/UFBA (2026) sobre ondas de calor no Brasil.

**Análises** (`meteo/cruzamento.py`)
- **Defasagem**: variação das internações de 0 a 7 dias depois de um dia de calor.
- Comparação **região × cidade** e **Heliópolis × cidade**, com intervalo de 95%.
- Faixas de temperatura próprias para a temperatura mínima (critério "noite quente").
- Conclusões automáticas reescritas para os três recortes. Quando Heliópolis sozinha não é
  conclusiva, o texto usa a região como evidência.

**Sensores da UNAS** (`meteo/limpeza.py`, `meteo/sensores.py`)
- A limpeza da branch `feature-limpeza-dados` foi integrada ao app (lógica preservada).
- O app lê CSVs em `data/sensores/` (separador `;` ou `,`, vírgula ou ponto decimal).
- **Índice de calor da NOAA** (Rothfusz, com os ajustes oficiais) e faixas de risco.
- Resumo diário por sensor e comparação sensor × Open-Meteo.
- Arquivo-modelo para download quando ainda não há dados.

**Painel** (`app.py`), reorganizado em 4 abas
- **O calor está aumentando?**
  - indicadores por década;
  - dias de calor por ano desde 1991, com linha de tendência;
  - mapa de calor ano × mês.
  - Funciona mesmo sem o DATASUS.
- **Calor × internações**: os três recortes em todos os gráficos, mais o novo gráfico
  "Quando o efeito aparece?" e barras de erro (faixa provável) na comparação.
- **Sensores da UNAS**: relatório de qualidade da limpeza, gráfico do índice de calor e
  tabela sensor × Open-Meteo.
- **Como foi feito**: fontes, tratamentos, limitações e exportação da série de clima e da
  tabela diária em CSV.

**Infraestrutura**
- `README.md` completo, cobrindo:
  - recorte territorial, fontes e tratamentos;
  - critérios de calor e método de comparação;
  - como ler cada gráfico e como rodar o projeto;
  - estrutura de pastas, formato dos sensores e limitações;
  - status de cada requisito RF/RNF.
- `Dockerfile` e `.dockerignore`.
- `tests/test_tratamentos.py` com 5 testes:
  - limpeza dos sensores;
  - índice de calor contra a tabela da NOAA;
  - detecção de ondas de calor;
  - calendário de feriados;
  - recortes e grupos das internações.

### Alterado
- `meteo/config.py` reúne todos os parâmetros novos, comentados: recortes, critérios,
  período de referência, defasagem máxima e pasta dos sensores.
- O SIH agora guarda também `MUNIC_RES`. Caches antigos, sem essa coluna, continuam
  funcionando.
- As marcas de calor e as defasagens são calculadas na série diária contínua do clima,
  antes da junção com as internações. Isso corrige a contagem de "dias seguintes" quando os
  anos escolhidos não são consecutivos (ex.: 2019 e 2022).
- Se o DATASUS estiver indisponível, o app mostra um aviso e mantém as abas de clima e
  sensores, em vez de parar.
- A legenda do gráfico por faixa de temperatura sempre mostra a cor cheia, inclusive quando a barra é vazada.
- `requirements.txt`: versão mínima do `streamlit` e `python-dateutil` explícito.
- `.gitignore`: os dados dos sensores ficam fora do Git por padrão.

### Corrigido
- A docstring de `meteo/__init__.py` dizia "óbitos (DATASUS/SIM)", mas o projeto usa
  internações do SIH.
- O parâmetro `CLIMATOLOGIA` estava definido no `config.py` mas não era usado.
- Fragmentação do DataFrame (`PerformanceWarning`) no cálculo do normal esperado.

### Observações
- O app foi testado aqui com **dados simulados**, porque o ambiente de desenvolvimento não
  acessava a Open-Meteo nem o FTP do DATASUS. Antes da entrega, ele precisa ser rodado uma
  vez com os dados reais.
- O `Dockerfile` não foi testado.
