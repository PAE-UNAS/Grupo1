# UNAS: Pesquisa sobre Estresse Térmico em Heliópolis

Painel interativo que cruza o **clima** de Heliópolis (São Paulo) desde 1991 com as
**internações de urgência no SUS**, para responder a três perguntas:

1. **O calor está aumentando em Heliópolis?**
2. **Quanto mais quente, mais internações?** E quantos dias depois do calor o efeito aparece?
3. **Nos dias de calor, Heliópolis sofre mais que o resto da cidade?**

> 📘 **Documentação**
> - [**Como usar**](docs/COMO_USAR.md): instalar, abrir, ler os gráficos, roteiros prontos e problemas comuns (para a equipe e a ONG).
> - [**Documentação técnica**](docs/DOCUMENTACAO_TECNICA.md): arquitetura, funções, métodos estatísticos, configuração e como estender o código.
> - [**CHANGELOG**](CHANGELOG.md): histórico de mudanças.

O projeto é feito em parceria com a **UNAS** (União de Núcleos, Associações dos Moradores
de Heliópolis e Região). Os resultados são apresentados em linguagem simples, para uso da
comunidade.

---

## Sumário

- [Recorte territorial](#recorte-territorial)
- [Fontes de dados](#fontes-de-dados)
- [Tratamento dos dados](#tratamento-dos-dados)
- [O que conta como calor](#o-que-conta-como-calor)
- [Como a comparação é feita](#como-a-comparação-é-feita)
- [O painel: gráficos e como lê-los](#o-painel-gráficos-e-como-lê-los)
- [Como rodar](#como-rodar)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Sensores da UNAS](#sensores-da-unas)
- [Como mudar os critérios](#como-mudar-os-critérios)
- [Limitações](#limitações)
- [Requisitos do projeto](#requisitos-do-projeto)
- [Próximos passos](#próximos-passos)
- [Referências](#referências)

---

## Recorte territorial

O foco é a **favela de Heliópolis**. Como há poucos dados oficiais sobre ela, a análise usa
três recortes, um dentro do outro:

| Recorte | Como é definido | Para que serve |
|---|---|---|
| **Heliópolis** | CEP de residência começando com 04229, 04230, 04231, 04233, 04235, 04236 ou 04239 | O alvo da pesquisa. Tem poucas internações por dia, então os resultados oscilam muito. |
| **Região do Ipiranga** | CEP de residência começando com 042 (inclui Heliópolis) | **Indicador indireto de Heliópolis**: vive o mesmo clima, inclui os próprios moradores de Heliópolis e tem ~10× mais casos. Se as internações sobem na região nos dias de calor, é provável que subam também em Heliópolis. |
| **Cidade de SP** | Todos os residentes do município | Referência para comparação. |

> **São Caetano do Sul** pode ser incluído se for preciso ampliar a vizinhança: basta
> acrescentar o código `354880` em `MUNICIPIOS` e criar um recorte em `RECORTES`
> (ambos em `meteo/config.py`). Atenção: São Caetano tem muita gente com plano de saúde,
> então internações no SUS lá não são comparáveis diretamente às de Heliópolis.

## Fontes de dados

| Fonte | O que usamos | Acesso | Período |
|---|---|---|---|
| **Open-Meteo** (reanálise ERA5) | Temperatura máxima, mínima e média, sensação térmica máxima e chuva, por dia, no ponto central de Heliópolis (−23,6105; −46,5925) | API REST pública, sem chave | 1991 até ~6 dias atrás |
| **DATASUS — SIH/SUS** (Sistema de Informações Hospitalares) | Internações de urgência: data, diagnóstico (CID-10), idade, desfecho (alta ou morte) e **CEP de residência** | FTP público (`ftp.datasus.gov.br`), arquivos `RDSPaamm.dbc` | anos completos disponíveis |
| **IBGE — Censo 2022** | População de Heliópolis (55.583) e de São Paulo (11.451.245) | valores fixos em `config.py` | 2022 |
| **Sensores da UNAS** | Temperatura e umidade dentro de Heliópolis | CSV em `data/sensores/` | ainda não instalados: o painel usa **dados simulados**, sempre marcados (ver [Sensores da UNAS](#sensores-da-unas)) |

Os downloads ficam salvos em `data/cache/`, então só a primeira execução é demorada.

## Tratamento dos dados

### Clima (`meteo/clima.py`)
- Datas convertidas e ordenadas; dias repetidos removidos.
- Valores impossíveis para São Paulo (abaixo de −5 °C ou acima de 50 °C) viram vazio.
- Dias com mínima maior que a máxima têm as temperaturas anuladas.
- Chuva negativa vira zero.
- **Dias faltando aparecem como linhas vazias**, em vez de sumirem em silêncio.
- Se a API estiver fora do ar, o app usa o último download salvo.

### Internações (`meteo/saude.py`)
- Só **urgências** (`CAR_INT = 02`): cirurgias marcadas não têm relação com o calor.
- Só a **AIH principal** (`IDENT = 1`), para não contar a mesma pessoa duas vezes.
- AIHs repetidas são removidas.
- Usamos a **data da internação** (`DT_INTER`), e não o mês do arquivo. O arquivo é organizado
  pelo mês em que o hospital *cobrou*, que pode ser até 3 meses depois. Por isso cada ano
  baixa 15 arquivos (os 12 meses + 3 de atraso).
- Idade convertida para anos (bebês com idade em horas, dias ou meses contam como 0).
- CEP padronizado (só dígitos, 8 posições) e classificado nos três recortes.
- Diagnósticos agrupados pela CID-10:

| Grupo | Critério | Por que |
|---|---|---|
| Todas as urgências | todas | visão geral |
| Doenças respiratórias | CID J | grupo mais sensível ao calor no Brasil (Fiocruz/UFBA, 2026) |
| Coração e circulação | CID I | o calor sobrecarrega o coração |
| Rins, desidratação e insolação | N17–N19, E86–E87, T67, X30 | efeitos mais diretos do calor |
| Diarreia e gastroenterite | A00–A09 | principal causa de internação de crianças em ondas de calor |
| Pessoas com 65 anos ou mais | idade ≥ 65 | grupo mais vulnerável |
| Crianças de 0 a 9 anos | idade ≤ 9 | grupo vulnerável |
| Internações que terminaram em morte | `MORTE = 1` | o efeito do calor costuma aparecer mais nas mortes |
| Dengue, chikungunya e zika | A90–A92 | doenças ligadas ao clima pelo mosquito; têm **análise mensal própria** e não aparecem no seletor de grupos |

### Sensores (`meteo/limpeza.py`, vindo da branch `feature-limpeza-dados`)
Datas em vários formatos padronizadas, Fahrenheit → Celsius, valores impossíveis
removidos, lacunas curtas (até 3 leituras) interpoladas dentro da série de cada sensor,
leituras repetidas removidas. A função `limpar()` devolve também um **relatório de
qualidade**, mostrado no painel.

## O que conta como calor

O usuário escolhe na barra lateral:

| Critério | Definição |
|---|---|
| **Dia quente** | sensação térmica máxima acima do percentil 90 dos verões (nov–mar) de 1991–2020 |
| **Noite quente** | temperatura mínima acima do percentil 90 dos verões de 1991–2020. À noite o corpo deveria se recuperar; em casas pequenas e pouco ventiladas isso não acontece. |
| **Onda de calor** | 3 ou mais dias quentes seguidos |

O limiar vem de um **período fixo de referência (1991–2020, padrão da OMM)**. Assim "dia de
calor" significa a mesma coisa em qualquer ano: se hoje há mais dias acima do limiar, é
porque esquentou, e não porque a régua mudou.

## Como a comparação é feita

O número de internações muda com a estação (inverno tem mais doença respiratória) e com o
dia da semana. Por isso não comparamos números brutos. Para cada dia calculamos o
**normal esperado**:

```
normal = média de internações nos dias SEM calor do mesmo mês e ano
         × peso do dia da semana
```

e comparamos com o que aconteceu ("+15%" = 15% acima do normal).

- **Feriados, Carnaval e 24/12–01/01** ficam de fora (opção na barra lateral): nesses dias os
  hospitais internam menos e, como caem no verão, fariam o calor parecer *diminuir* as
  internações.
- **Faixa provável (intervalo de 95%)**: considera a variação natural dos casos (Poisson) e a
  incerteza do próprio normal. Se a faixa inclui o zero, a diferença pode ser acaso. Nos
  gráficos, **barra cheia = diferença confiável; barra vazada = pode ser acaso**.
- **Correlação de Spearman** entre a temperatura do dia e o % acima do normal (dias de verão).
- **Comparação entre lugares**: razão entre os aumentos de cada lugar (ex.: região ÷ cidade),
  com intervalo de 95%.
- **Taxa por 100 mil habitantes** só para Heliópolis e a cidade (a população exata dos CEPs
  042 não é publicada).

## O painel: gráficos e como lê-los

O topo do painel traz um quadro **"O que os dados mostram"** com as conclusões em texto
simples, geradas automaticamente a partir dos filtros escolhidos.

**Filtros (barra lateral):** critério de calor · **fonte do clima** (Open-Meteo ou Heliópolis
corrigida pelos sensores) · tipo de internação · anos · população de Heliópolis · descontar
feriados.

### Aba 1 — O calor está aumentando?
Só usa dados de clima, então funciona mesmo sem o DATASUS.

| Gráfico | O que mostra |
|---|---|
| Indicadores | dias de calor por ano na primeira e na última década, e a tendência em dias por década |
| **Dias de calor por ano** (barras + tendência) | se o calor extremo está ficando mais frequente desde 1991 |
| **Mapa de calor ano × mês** | em que meses o calor aparece e se a estação quente está ficando mais longa |

### Aba 2 — Calor × internações
| Gráfico | O que mostra |
|---|---|
| **Internações por faixa de temperatura** (barras, 3 recortes) | se as internações sobem conforme esquenta |
| **Dia a dia** (dispersão + tendência) | cada dia de verão; a correlação de Spearman |
| **Quando o efeito aparece** (linhas, 0 a 7 dias) | quantos dias depois do calor as internações sobem, ou seja, por quanto tempo manter o alerta |
| **Variação nos dias de calor** (barras com faixa provável) | o aumento em Heliópolis, na região e na cidade, cada um contra o próprio normal |
| **Internações por 100 mil habitantes** | quem é proporcionalmente mais internado, com e sem calor |
| **Arboviroses: correlação com o clima anterior** (barras) | se a temperatura média e a chuva de 0, 1 e 2 meses antes acompanham as internações por dengue, chikungunya e zika |
| **Arboviroses mês a mês** (dois painéis) | internações por mês em cima e temperatura média embaixo, para ver o atraso entre calor e casos |

### Aba 3 — Sensores da UNAS
Enquanto não há sensores, todos os gráficos desta aba usam **dados simulados** e mostram um
aviso amarelo "DADOS SIMULADOS". Com dados reais, o aviso some.

| Gráfico | O que mostra |
|---|---|
| Indicadores de qualidade | o que a limpeza automática corrigiu (impossíveis, lacunas, °F) |
| **Índice de calor máximo do dia, por sensor** | o calor sentido em cada ponto, comparado à sensação térmica da Open-Meteo, com as faixas de risco da NOAA |
| **Quanto Heliópolis é mais quente que a Open-Meteo?** (indicadores + dispersão) | a diferença média na máxima e na mínima. Ela alimenta a série **Heliópolis corrigida** |
| **Horas por dia em cada faixa de risco** (barras empilhadas) | quanto tempo cada ponto passa em cautela, perigo etc.; mostra os pontos mais quentes |
| **A noite esfria?** (perfil de 24 horas) | se a madrugada continua quente, impedindo o corpo de se recuperar |

### Série "Heliópolis corrigida pelos sensores"
Os sensores vão ter poucos meses de dados, e a análise de internações precisa de vários
anos. Por isso os sensores são usados para **calibrar** a Open-Meteo:

1. Para cada dia com sensores, calcula-se a diferença entre a média dos sensores **dentro de
   Heliópolis** e a Open-Meteo (máxima e mínima). Os sensores de controle ficam de fora.
2. A média dessas diferenças é somada a toda a série desde 1991 (a sensação térmica recebe a
   mesma correção da máxima).
3. A **régua de calor não muda**: os limiares continuam os da Open-Meteo. A correção aparece
   como **mais dias acima do limiar**, ou seja, quantos dias de calor a estimativa regional
   não vê em Heliópolis.

Escolhendo essa fonte na barra lateral, **todas** as abas são refeitas com a série corrigida,
e o gráfico de dias de calor por ano mostra as duas séries juntas.

### Aba 4 — Como foi feito
Fontes, tratamentos, limitações e **exportação** das tabelas em CSV (abre no Excel em
português: separador `;` e vírgula decimal).

**Salvar um gráfico como imagem:** passe o mouse sobre ele e clique no ícone de câmera (PNG em
alta resolução).

## Como rodar

Passo a passo detalhado para Windows, com solução dos erros mais comuns, em
[docs/COMO_USAR.md](docs/COMO_USAR.md). Resumo:

Requisitos: Python 3.10+ e internet (Open-Meteo e FTP do DATASUS).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m streamlit run app.py
```

> Use sempre `streamlit run` (e não `python app.py`), senão o painel não abre no navegador.

O painel abre em http://localhost:8501. **Na primeira vez**, cada ano de internações baixa
15 arquivos do DATASUS (~1 minuto cada). Depois tudo fica salvo em `data/cache/`.

### Com Docker

```bash
docker build -t calor-heliopolis .
docker run -p 8501:8501 -v "$(pwd)/data:/app/data" calor-heliopolis
```

O volume `data/` guarda o cache e os CSVs dos sensores entre execuções.

### Testes

```bash
pip install pytest
python -m pytest
```

Os testes conferem a limpeza dos sensores, o índice de calor (contra a tabela da NOAA), a
detecção de ondas de calor, o calendário de feriados, a classificação das internações
(incluindo arboviroses), a simulação dos sensores e a calibração.

## Estrutura do projeto

```
app.py                  painel Streamlit (gráficos e textos)
meteo/
  config.py             TODOS os parâmetros e critérios (comece por aqui)
  clima.py              Open-Meteo: download, tratamento, critérios de calor, tendência
  saude.py              DATASUS/SIH: download, tratamento, recortes e grupos
  cruzamento.py         clima × internações: normal, comparações, conclusões
  limpeza.py            limpeza de séries de sensores (temperatura e umidade)
  sensores.py           sensores da UNAS: leitura, simulação, índice de calor, calibração
tests/                  testes automáticos dos tratamentos
docs/                   guia de uso e documentação técnica
data/cache/             downloads salvos (fora do Git)
data/sensores/          CSVs dos sensores (fora do Git)
Dockerfile              ambiente reprodutível
```

## Sensores da UNAS

### Trocando os dados simulados pelos reais

Enquanto não há sensores, `meteo/sensores.py` (função `simular`) gera leituras **fictícias**
a partir da Open-Meteo do último verão, com um excesso de calor inventado por sensor
(`PLACEHOLDER_EXCESSO` em `meteo/config.py`). Elas servem só para mostrar como as análises
funcionam e **não devem ser citadas**. O topo de `meteo/sensores.py` tem um quadro com o passo
a passo; em resumo:

1. Exporte as leituras para arquivos `.csv` no formato abaixo.
2. Dê aos sensores **dentro de Heliópolis** um nome começando com `heliopolis`
   (ex.: `heliopolis_viela_01`). Só eles entram na calibração; outros nomes
   (ex.: `ipiranga_controle_01`) servem de controle. O prefixo fica em
   `PREFIXO_SENSOR_HELIOPOLIS` (`meteo/config.py`).
3. Coloque os arquivos em `data/sensores/` e recarregue o painel.

Havendo **qualquer** `.csv` na pasta, a simulação é desligada automaticamente e os avisos
somem. Para desligá-la de vez (por exemplo, na versão final para a ONG), mude
`SENSORES_PLACEHOLDER = False` em `meteo/config.py`. A calibração precisa de pelo menos 14
dias completos (18 horas ou mais de leituras) de sensores de Heliópolis.

### Formato dos arquivos

Uma linha por leitura; separador `;` ou `,`; vírgula ou ponto decimal.

| coluna | descrição |
|---|---|
| `sensor_id` | nome do sensor (ex.: `heliopolis_01`) |
| `timestamp` | data e hora (ex.: `15/01/2026 14:00` ou `2026-01-15 14:00`) |
| `temperatura` | temperatura do ar |
| `umidade` | umidade relativa (%) |
| `unidade_temp` | `C` ou `F` (opcional; padrão `C`) |

Sugestão de instalação: pelo menos um sensor dentro de Heliópolis e um de controle no
Ipiranga, para medir quanto a favela é mais quente que o entorno.

## Como mudar os critérios

Tudo que é escolha da equipe está em `meteo/config.py`, com a justificativa ao lado:
CEPs dos recortes, municípios, período de referência, percentil do limiar, meses de verão,
duração mínima da onda de calor, dias de efeito após o calor, populações e anos da pandemia
(2020–2021, fora por padrão).

## Limitações

- **O clima é uma estimativa regional** (área de vários km²). Dentro da favela, com casas
  coladas, laje e pouca árvore, o calor tende a ser maior. Os sensores da UNAS resolvem isso.
- **Só internações no SUS**: quem é atendido no pronto-socorro e liberado, ou usa plano de
  saúde, não aparece.
- **CEP como endereço**: alguns prefixos de Heliópolis são compartilhados com ruas vizinhas
  do Sacomã; o prefixo 042 é uma aproximação da região do Ipiranga.
- **A região é um indicador indireto**: inclui Heliópolis e o mesmo clima, mas também bairros
  com outras condições de vida.
- **Associação não é causa**: os resultados mostram que internações e calor andam juntos,
  descontadas estação, dia da semana e feriados, mas outros fatores (como poluição) podem
  contribuir.
- Anos da pandemia (2020–2021) ficam fora por padrão, porque o padrão de internações mudou.
- **Sensores**: os gráficos atuais usam dados simulados. Com dados reais, a correção da série
  é medida no verão em que os sensores funcionaram e aplicada a todos os anos e meses; é uma
  aproximação, que melhora com mais meses de medição.
- **Arboviroses**: só casos graves internam; as notificações (SINAN) mostrariam muito mais casos.

## Requisitos do projeto

| Requisito | Situação |
|---|---|
| RF — Extrair dados das APIs públicas via REST | ✅ Open-Meteo (REST) e DATASUS (FTP) |
| RF — Limpar as bases (ausentes, outliers, unidades, timestamps) | ✅ clima, internações e sensores |
| RF — Cruzar variáveis | ✅ clima × internações por dia e recorte |
| RF — Calcular índices de estresse térmico a partir de variáveis brutas | ✅ índice de calor (NOAA) e horas em risco para sensores; dia/noite quente e onda de calor |
| RF — Análises exploratórias (correlações, séries temporais, distribuições) | ✅ Spearman, série anual, mapa ano × mês, faixas, defasagem |
| RF — Dashboards interativos com filtros por período e recorte territorial | ✅ anos, critério, grupo, recorte |
| RF — Exportação dos resultados | ✅ CSVs na aba "Como foi feito"; gráficos exportáveis como imagem pelo Plotly |
| RNF — Compartilhamento de conhecimento com a ONG | ✅ conclusões em texto simples |
| RNF — Acessibilidade | ✅ linguagem clara, rótulos diretos, cor + preenchimento para confiabilidade |
| RNF — Reprodutibilidade (Docker e Git) | ✅ `Dockerfile` |
| RNF — Manutenibilidade | ✅ código comentado, parâmetros centralizados, testes |
| RNF — Confiabilidade dos dados | ✅ fontes documentadas, relatório de qualidade dos sensores, intervalos de confiança |
| RNF — Escalabilidade (novos sensores e fontes) | ✅ sensores por arquivo (qualquer número, detectados sozinhos); novos recortes e municípios pelo `config.py` |
| RNF — Sustentabilidade | ✅ este README e o `config.py` comentado |

## Próximos passos

- Instalar os sensores da UNAS e trocar os dados simulados pelos reais (ver acima).
- Notificações de dengue, chikungunya e zika (SINAN), que têm muito mais casos que as internações.
- Óbitos do SIM (TabNet da Prefeitura de SP/PRO-AIM) para o distrito do Sacomã.
- Poluição (ozônio, CETESB/QUALAR) como fator de confusão das internações respiratórias.
- Dados do Censo 2022 por setor censitário (idosos, crianças, densidade) para mostrar a
  vulnerabilidade de Heliópolis.

## Referências

- Open-Meteo — Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
- DATASUS — SIH/SUS, arquivos de dados: `ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados`
- NOAA/National Weather Service — Heat Index equation (Rothfusz): https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
- Fiocruz e UFBA (2026). *Saúde e ondas de calor no Brasil: evidências sobre mortalidade, morbidade hospitalar e implicações para o SUS* (2000–2019, 5.566 municípios).
- IBGE — Censo Demográfico 2022.
