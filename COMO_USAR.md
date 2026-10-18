# Como usar o painel "Calor e saúde em Heliópolis"

Guia para quem vai **usar** o painel: equipe do projeto, UNAS e comunidade. Não precisa
saber programar. Para detalhes de código, veja a [documentação técnica](DOCUMENTACAO_TECNICA.md).

---

## Sumário

1. [O que o painel faz](#1-o-que-o-painel-faz)
2. [Instalar (só na primeira vez)](#2-instalar-só-na-primeira-vez)
3. [Abrir o painel](#3-abrir-o-painel)
4. [Conhecendo a tela](#4-conhecendo-a-tela)
5. [Como ler os gráficos](#5-como-ler-os-gráficos)
6. [Roteiros prontos](#6-roteiros-prontos)
7. [Salvar gráficos e dados](#7-salvar-gráficos-e-dados)
8. [Colocar os dados dos sensores](#8-colocar-os-dados-dos-sensores)
9. [Cuidados ao contar os resultados](#9-cuidados-ao-contar-os-resultados)
10. [Problemas comuns](#10-problemas-comuns)

---

## 1. O que o painel faz

O painel junta duas informações públicas:

- **o clima de Heliópolis** desde 1991 (temperatura, sensação térmica e chuva, da Open-Meteo);
- **as internações de urgência no SUS** (DATASUS), separando quem mora em Heliópolis pelo CEP.

Com elas, responde a quatro perguntas:

| Pergunta | Onde ver |
|---|---|
| O calor está aumentando em Heliópolis? | aba **O calor está aumentando?** |
| Nos dias quentes, mais gente é internada? Quantos dias o efeito dura? | aba **Calor × internações** |
| O calor favorece dengue, chikungunya e zika? | aba **Calor × internações**, no final |
| Quanto Heliópolis é mais quente que a estimativa regional? | aba **Sensores da UNAS** |

> **Por que aparece a "Região do Ipiranga"?** Heliópolis tem poucas internações por dia, o que
> deixa os números instáveis. A região do Ipiranga (CEPs que começam com 042) inclui Heliópolis,
> vive o mesmo clima e tem cerca de 10 vezes mais casos. Se algo acontece na região, é um bom
> indício do que acontece em Heliópolis.

---

## 2. Instalar (só na primeira vez)

Você precisa de um computador com internet. Os passos abaixo são para **Windows**.

### 2.1. Instalar o Python
1. Acesse https://www.python.org/downloads/ e baixe a versão mais recente.
2. Na primeira tela do instalador, **marque "Add python.exe to PATH"** e clique em *Install Now*.

### 2.2. Baixar o projeto
1. Baixe o projeto (pelo GitHub em **Code → Download ZIP**, ou o .zip que a equipe enviou).
2. Clique com o botão direito no arquivo e escolha **Extrair tudo**.

### 2.3. Instalar as bibliotecas
1. Abra a pasta extraída até ver o arquivo `app.py`.
2. Clique na barra de endereço da pasta, digite `powershell` e aperte Enter. Abre uma janela
   azul ou preta já dentro da pasta.
3. Digite e aperte Enter:
   ```powershell
   python -m pip install -r requirements.txt
   ```
4. Espere terminar (alguns minutos).

> **Mac ou Linux:** abra o Terminal na pasta e use `python3` no lugar de `python`.

---

## 3. Abrir o painel

1. Abra o PowerShell na pasta do projeto, como no passo 2.3.
2. Digite:
   ```powershell
   python -m streamlit run app.py
   ```
3. O navegador abre sozinho em **http://localhost:8501**. Se não abrir, copie o endereço
   `Local URL` que aparece na janela do PowerShell.
4. **Deixe a janela do PowerShell aberta** enquanto usa o painel. Para fechar o painel, feche a
   janela ou aperte `Ctrl + C` nela.

> ⚠️ **Não** use `python app.py` nem o botão "Run" do VS Code: o painel não abre no navegador.

### Quanto tempo demora
- **Aba de clima:** aparece em segundos.
- **Internações, na primeira vez:** cada ano baixa 15 arquivos do DATASUS, cerca de 15 minutos
  por ano. Uma barra mostra o andamento. Para testar rápido, deixe **só 1 ano** marcado.
- **Depois:** tudo fica salvo na pasta `data/cache` e o painel abre na hora.

### Mostrar para outra pessoa na mesma rede
A janela do PowerShell também mostra um `Network URL` (algo como `http://192.168.0.10:8501`).
Quem estiver no mesmo Wi-Fi pode abrir esse endereço.

---

## 4. Conhecendo a tela

### 4.1. Barra lateral (à esquerda): as escolhas

| Opção | O que muda |
|---|---|
| **O que conta como calor** | **Dia quente**: sensação térmica máxima entre as 10% mais altas dos verões de 1991–2020. **Noite quente**: madrugada entre as 10% mais quentes (o corpo não descansa). **Onda de calor**: 3 ou mais dias quentes seguidos. |
| **Fonte do clima** | **Open-Meteo (regional)**: estimativa para uma área de vários km². **Heliópolis corrigida pelos sensores**: a mesma série, somada à diferença medida pelos sensores. Esta segunda opção só aparece quando há dados de sensores (reais ou simulados). |
| **Tipo de internação** | Todas as urgências, ou um grupo: respiratórias, coração, rins/desidratação, diarreia, idosos (65+), crianças (0–9) ou internações que terminaram em morte. |
| **Anos (internações)** | Quais anos entram na análise. 2020 e 2021 (pandemia) ficam de fora por padrão. |
| **População de Heliópolis** | Usada só na taxa por 100 mil habitantes. O padrão é o Censo 2022 (55.583). |
| **Descontar feriados e fim de ano** | Deixe ligado. Nesses dias os hospitais internam menos, o que confundiria a análise. |

Toda mudança na barra lateral **refaz todas as abas** na hora.

### 4.2. Quadro "O que os dados mostram"
Fica no topo e resume, em frases simples, o resultado para as escolhas atuais. É o melhor
ponto de partida para uma apresentação.

### 4.3. As quatro abas

**🌡️ O calor está aumentando?**
- Números no topo: dias de calor por ano na primeira e na última década, e a tendência.
- **Dias de calor por ano** (barras): a linha tracejada mostra a tendência. A última barra
  vazada é o ano atual, que ainda não terminou.
- **Em que meses o calor aparece** (quadriculado colorido): cada linha é um ano e cada coluna
  um mês. Quanto mais escuro, mais dias de calor.

**🏥 Calor × internações**
- **Quanto mais quente, mais internações?** Barras por faixa de temperatura, nos três lugares.
- **Dia a dia:** cada ponto é um dia de verão. Escolha o lugar logo acima do gráfico.
- **Quando o efeito aparece?** O aumento das internações no dia do calor (0) e nos 7 dias seguintes.
- **Nos dias de calor, Heliópolis sofre mais?** O aumento em cada lugar e a taxa por 100 mil
  habitantes.
- **Dengue, chikungunya e zika × temperatura:** análise por mês, com o clima de até 2 meses antes.

**📡 Sensores da UNAS**
- Enquanto não houver sensores, mostra **dados simulados**, com um aviso amarelo (veja a seção 8).
- Mostra o índice de calor de cada sensor, quanto Heliópolis é mais quente que a Open-Meteo,
  as horas por dia em situação de risco e se a madrugada esfria.

**📄 Como foi feito**
- Fontes, tratamentos, limitações e os botões para baixar os dados.

---

## 5. Como ler os gráficos

| O que você vê | O que significa |
|---|---|
| **Cores dos lugares** | 🟧 laranja = Heliópolis · 🟩 verde = Região do Ipiranga · 🟦 azul = Cidade de SP |
| **"% acima do normal"** | Comparação com o que seria esperado **naquela época do ano e naquele dia da semana**, sem calor. "+10%" = 10% mais internações que o normal. |
| **Barra ou ponto cheio** | Diferença **confiável**: dificilmente é acaso. |
| **Barra ou ponto vazado** (só o contorno) | A diferença **pode ser acaso**. Não afirme nada com base nela sozinha. |
| **Traço cinza sobre a barra** | **Faixa provável** (intervalo de 95%): o valor real deve estar ali dentro. Quanto mais largo, mais incerto. Em Heliópolis costuma ser largo. |
| **ρ (rô) de Spearman** | Mede se duas coisas sobem juntas: 0 = nenhuma relação; +1 = sobem sempre juntas; −1 = uma sobe quando a outra desce. Na saúde, valores de 0,1 a 0,3 já são comuns. |
| **Passar o mouse** | Mostra os números exatos de cada barra ou ponto. |

> **Por que comparar em % e não em número de internados?** Porque a cidade tem 200 vezes mais
> gente que Heliópolis. Em %, cada lugar é comparado com ele mesmo, e o tamanho não importa.

---

## 6. Roteiros prontos

**"O calor está aumentando em Heliópolis?"**
1. Aba *O calor está aumentando?*, critério **Dia quente**.
2. Compare os dois números do topo (primeira × última década) e a linha de tendência.
3. Troque para **Noite quente**: as madrugadas quentes costumam crescer ainda mais.

**"O calor afeta mais os idosos?"**
1. *Tipo de internação* → **Pessoas com 65 anos ou mais**.
2. Aba *Calor × internações* → gráfico *Nos dias de calor, Heliópolis sofre mais?*
3. Compare com **Todas as internações de urgência**.

**"Por quantos dias manter o alerta depois de um dia quente?"**
1. Aba *Calor × internações* → gráfico *Quando o efeito aparece?*
2. Procure até que dia os pontos da região (verde) continuam **cheios e acima de zero**.

**"Ondas de calor são piores que um dia quente isolado?"**
1. Anote o resultado com **Dia quente**.
2. Troque para **Onda de calor** e compare.

**"Mortes aumentam no calor?"**
1. *Tipo de internação* → **Internações que terminaram em morte**.
2. Use **Onda de calor** e vários anos (menos casos exigem mais anos).

**"O calor aumenta a dengue?"**
1. Aba *Calor × internações*, final da página.
2. Veja se a barra vermelha (temperatura) de **1 ou 2 meses antes** é alta e cheia.

---

## 7. Salvar gráficos e dados

- **Gráfico como imagem:** passe o mouse sobre o gráfico e clique no ícone de **câmera** que
  aparece no canto superior direito. Baixa um PNG em alta resolução, bom para slides e relatórios.
- **Dados em planilha:** aba *Como foi feito* → botões **Baixar**. Os arquivos `.csv` abrem
  direto no Excel em português (separador `;`, vírgula decimal).
  - *Tabela diária clima × internações*: um dia por linha, com o clima e as internações de
    cada grupo e lugar, para os anos escolhidos.
  - *Série de clima desde 1991*: um dia por linha.

---

## 8. Colocar os dados dos sensores

Enquanto não há sensores, a aba de sensores e a opção *Heliópolis corrigida* usam **dados
simulados** (inventados), sempre com o aviso amarelo **"DADOS SIMULADOS"**. **Não use esses
números em apresentações como se fossem medições.**

Quando os sensores estiverem funcionando:

1. **Prepare uma planilha** com uma linha por leitura e estas colunas, nesta ordem:

   | sensor_id | timestamp | temperatura | umidade | unidade_temp |
   |---|---|---|---|---|
   | heliopolis_viela_01 | 15/01/2026 14:00 | 33,1 | 58 | C |
   | ipiranga_controle_01 | 15/01/2026 14:00 | 31,0 | 61 | C |

   - **sensor_id:** o nome do sensor. Sensores **dentro de Heliópolis** devem começar com
     `heliopolis`. Outros nomes contam como sensores de comparação.
   - **timestamp:** data e hora da leitura.
   - **unidade_temp:** `C` (Celsius) ou `F` (Fahrenheit). Se não tiver, considera Celsius.
2. No Excel: **Arquivo → Salvar como → CSV (separado por vírgulas)**. No Excel em português, o
   arquivo sai com `;`, e o painel aceita os dois.
3. Coloque o arquivo na pasta **`data/sensores`** do projeto. Pode ter vários arquivos.
4. Recarregue o painel (tecla F5). O aviso de dados simulados some.

> Um modelo pronto pode ser baixado na própria aba de sensores, em *Como trocar pelos dados
> reais → Baixar arquivo-modelo*.

A comparação com a Open-Meteo precisa de pelo menos **14 dias completos** de sensores de
Heliópolis. Quanto mais meses, mais confiável.

---

## 9. Cuidados ao contar os resultados

- **"Associado" não é "causado".** O painel mostra que calor e internações andam juntos, já
  descontando a época do ano, o dia da semana e os feriados. Outros fatores, como a poluição,
  também podem influenciar.
- **O clima é regional.** A Open-Meteo estima uma área de vários km². Dentro das vielas o
  calor costuma ser maior, e é isso que os sensores vão medir.
- **Só internações no SUS.** Quem foi atendido e liberado, ou usou plano de saúde, não aparece.
- **Barra vazada = pode ser acaso.** Não afirme nada só com base nela.
- **Dados simulados** (aviso amarelo) **nunca** devem ser apresentados como resultado.

Uma frase segura para apresentações:
> "Nos dias de calor, as internações de urgência de moradores da região do Ipiranga, que inclui
> Heliópolis, ficaram X% acima do esperado para a época."

---

## 10. Problemas comuns

| Mensagem ou situação | O que fazer |
|---|---|
| A janela mostra vários `missing ScriptRunContext` e nada abre | O painel foi iniciado com `python app.py`. Use `python -m streamlit run app.py`. |
| `No module named streamlit` | Rode `python -m pip install -r requirements.txt` antes. |
| `'python' não é reconhecido` | O Python não foi adicionado ao PATH. Reinstale marcando *Add python.exe to PATH*. |
| `.venv\Scripts\activate` dá erro | O ambiente virtual não foi criado. Pode pular esse passo. |
| "Execução de scripts foi desabilitada" | Rode `Set-ExecutionPolicy -Scope Process Bypass` e tente de novo. |
| Erro ao instalar `pyreaddbc` | Rode `python -m pip install pyreaddbc --only-binary :all:`. |
| Aviso "Os dados do DATASUS não estão disponíveis" | O servidor do DATASUS está fora do ar ou a rede bloqueia FTP (comum em redes de empresa ou faculdade). Tente outra rede. As abas de clima e sensores continuam funcionando. |
| "Não foi possível obter o clima da Open-Meteo" | Sem internet. Se o painel já foi aberto antes, ele usa o último clima salvo. |
| O download parou no meio | Abra o painel de novo: o que já foi baixado fica salvo e ele continua de onde parou. |
| O endereço é 8502, e não 8501 | Outro painel já está aberto. Use o endereço mostrado na janela, ou feche o outro. |
| A página fica cinza ou "Connecting…" | A janela do PowerShell foi fechada. Abra o painel de novo. |
