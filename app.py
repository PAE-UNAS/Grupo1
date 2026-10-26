"""Calor e saúde em Heliópolis — painel interativo.

Rodar:  streamlit run app.py
"""
# ↑ Isto é uma "docstring": um texto entre aspas triplas no topo do arquivo.
#   Não executa nada; serve só para explicar o que o arquivo faz e como rodar.

# =============================================================================
# IMPORTAÇÕES — trazemos ferramentas (bibliotecas) prontas para usar no código
# =============================================================================
import numpy as np                 # NumPy: contas com listas de números (média, regressão…). Apelidado de "np".
import pandas as pd                # Pandas: trabalha com tabelas (DataFrames), como um Excel no Python. Apelido "pd".
import plotly.graph_objects as go  # Plotly: desenha gráficos interativos. "go" tem as peças (barra, linha, ponto…).
import streamlit as st             # Streamlit: transforma este script num site/painel. Apelido "st".

# Importa os NOSSOS módulos, que ficam na pasta meteo/:
#   clima      → baixa e trata a temperatura (Open-Meteo)
#   config     → parâmetros do projeto (CEPs, população, limiares…)
#   cruzamento → junta clima + saúde e faz as análises
#   saude      → baixa e trata as internações (DATASUS)
#   sensores   → lê (ou simula) os sensores de temperatura da UNAS
from meteo import clima, config, cruzamento, saude, sensores

# =============================================================================
# CONSTANTES — valores fixos usados no painel inteiro (nome em MAIÚSCULAS por convenção)
# =============================================================================
# Cor = identidade do lugar (a mesma em todos os gráficos)
# Dicionário: cada chave (lugar) aponta para uma cor em código hexadecimal (#RRGGBB).
COR = {"heliopolis": "#eb6834", "regiao": "#1baf7a", "cidade": "#2a78d6"}  # laranja, verde, azul
# Duas variáveis definidas na mesma linha: CINZA (linhas de apoio) e TINTA (cinza escuro para textos/eixos).
CINZA, TINTA = "#a3a29c", "#52514e"
# Só o botão "baixar como imagem" (PNG em alta resolução), que aparece ao passar o mouse
CONFIG_GRAFICO = {"modeBarButtons": [["toImage"]],   # barra de ferramentas do gráfico: só o botão de imagem
                  "displaylogo": False,              # esconde o logo do Plotly
                  "toImageButtonOptions": {"format": "png",               # a imagem sai em PNG
                                           "scale": 2,                    # 2× a resolução da tela (mais nítida)
                                           "filename": "calor_heliopolis"}}  # nome do arquivo baixado
# Lista com as abreviações dos meses, na ordem; usada como rótulo no mapa de calor.
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Configura a página do Streamlit: título da aba do navegador, ícone e layout largo (usa a tela toda).
# Precisa ser o primeiro comando "st." do script.
st.set_page_config(page_title="Calor e saúde em Heliópolis", page_icon="🌡️", layout="wide")


# ---------------------------------------------------------------- formatação
# Funções pequenas que transformam números em texto no padrão brasileiro.

def f(x, casas=0):                 # "f" = formatar. Recebe um número x e quantas casas decimais mostrar (padrão 0).
    # Se x for vazio (NaN), devolve um traço "–". Senão, formata com "casas" decimais e troca o ponto
    # decimal americano pela vírgula brasileira. Ex.: f(3.14159, 1) → "3,1".
    return "–" if pd.isna(x) else f"{x:.{casas}f}".replace(".", ",")


def milhar(x):                     # Formata números grandes com ponto de milhar. Ex.: 55583 → "55.583".
    # ":,.0f" = separa milhares com vírgula e 0 casas decimais (padrão americano: 55,583);
    # depois troca a vírgula por ponto para ficar no padrão brasileiro.
    return f"{x:,.0f}".replace(",", ".")


def var(x):                        # Formata uma VARIAÇÃO percentual com sinal. Ex.: 12.3 → "+12%".
    if pd.isna(x):                 # Se o valor for vazio…
        return "–"                 # …mostra um traço.
    if abs(x) < 0.5:               # Se a variação for menor que meio por cento (para mais ou para menos)…
        return "0%"                # …mostra "0%" (evita aparecer "+0%" ou "−0%").
    # Escolhe o sinal ("+" se positivo, "−" se negativo), formata o valor absoluto (sem sinal) e põe "%".
    return ("+" if x > 0 else "−") + f(abs(x)) + "%"


def mudou(x):                      # Transforma uma variação em frase. Ex.: −5 → "**caíram 5%**".
    if pd.isna(x) or abs(x) < 0.5: # Se for vazio ou praticamente zero…
        return "ficaram **praticamente iguais**"   # (os ** deixam o texto em negrito no Streamlit)
    # Senão escolhe o verbo pelo sinal e mostra o número sem sinal.
    return f"**{'subiram' if x > 0 else 'caíram'} {f(abs(x))}%**"


# Define estilo_barras(): devolve o "estilo" (cor de preenchimento e contorno) de um conjunto de barras.
def estilo_barras(cores, significativos):
    """Cheia = diferença confiável; vazada (só contorno) = pode ser acaso."""
    # Recebe uma lista de cores e uma lista de True/False (o resultado é estatisticamente confiável?).
    # zip(cores, significativos) anda pelas duas listas ao mesmo tempo, par a par.
    # Para cada barra: se confiável (s=True), pinta com a cor; senão usa "rgba(0,0,0,0)" (transparente).
    return dict(color=[c if s else "rgba(0,0,0,0)" for c, s in zip(cores, significativos)],
                # O contorno (line) é sempre da cor do lugar, com 2,5 px de espessura.
                # Assim a barra "vazada" aparece só como contorno.
                line=dict(color=cores, width=2.5))


def grafico(fig, altura=380):      # Aplica o MESMO visual a todos os gráficos (padroniza o painel).
    fig.update_layout(height=altura,                            # altura do gráfico em pixels
                      margin=dict(l=8, r=8, t=40, b=8),         # margens: esquerda, direita, topo, baixo
                      separators=",.",                          # decimal com vírgula e milhar com ponto (padrão BR)
                      bargap=.3,                                # espaço entre grupos de barras (30%)
                      bargroupgap=.08,                          # espaço entre barras do mesmo grupo (8%)
                      hoverlabel=dict(font_size=14),            # tamanho da letra da caixinha que aparece ao passar o mouse
                      legend=dict(orientation="h",              # legenda na horizontal…
                                  y=1.1, x=0,                   # …posicionada acima do gráfico, à esquerda
                                  font_size=14, title=None))    # letra 14 e sem título na legenda
    fig.update_xaxes(showgrid=False, tickfont_size=13)          # eixo X: sem linhas de grade, rótulos tamanho 13
    fig.update_yaxes(tickfont_size=12,                          # eixo Y: rótulos tamanho 12
                     gridcolor="rgba(128,128,128,.15)",         # linhas de grade cinza bem clarinhas (15% de opacidade)
                     zeroline=False)                            # não desenha a linha do zero automática (desenhamos à mão)
    return fig                                                  # devolve o gráfico já estilizado


def mostrar(fig, altura=380, legenda=True):   # Atalho: estiliza o gráfico e já o coloca na tela.
    # grafico(...) aplica o estilo; .update_layout(showlegend=...) liga/desliga a legenda;
    # st.plotly_chart desenha no painel. width="stretch" = ocupa a largura toda;
    # config=CONFIG_GRAFICO = só o botão de baixar imagem.
    st.plotly_chart(grafico(fig, altura).update_layout(showlegend=legenda), width="stretch",
                    config=CONFIG_GRAFICO)


# ------------------------------------------------------------------ dados
# Funções que carregam os dados. O "@st.cache_data" em cima de cada uma é um DECORADOR:
# ele guarda o resultado na memória. Se a função for chamada de novo com os mesmos argumentos,
# o Streamlit devolve o resultado guardado em vez de recalcular (o painel fica muito mais rápido).

# show_spinner = mensagem mostrada enquanto carrega; ttl="12h" = o resultado guardado vale por 12 horas.
@st.cache_data(show_spinner="Baixando o clima (Open-Meteo)…", ttl="12h")
def dados_clima():
    return clima.carregar()        # Baixa (ou lê do cache em disco) e trata a série diária de clima desde 1991.


@st.cache_data(show_spinner="Consultando o DATASUS…", ttl="24h")   # guarda por 24 horas
def meses_saude():
    return saude.meses_disponiveis()   # Pergunta ao FTP do DATASUS quais arquivos mensais já existem.


@st.cache_data(show_spinner="Contando as internações…")   # sem ttl: guarda até o painel ser reiniciado
def dados_saude(anos: tuple):      # "anos: tuple" é uma dica de tipo: espera uma tupla, ex.: (2022, 2023).
    # O cache exige argumentos "imutáveis" (tupla em vez de lista); aqui convertemos de volta para lista.
    return saude.carregar(list(anos))   # Junta os arquivos e conta as internações por dia.


# Cache dos sensores, com a mensagem "Lendo os sensores…" enquanto carrega.
@st.cache_data(show_spinner="Lendo os sensores…")
def dados_sensores(assinatura, placeholder):  # recalcula quando um arquivo muda
    # Os dois argumentos NÃO são usados dentro da função. Eles existem só para o cache:
    # se a "assinatura" (nomes + datas de modificação dos arquivos) mudar, o Streamlit
    # entende que é outra chamada e recalcula. Assim, ao salvar um CSV novo, o painel atualiza.
    # Dados reais (data/sensores/*.csv) têm prioridade; sem eles, usa a simulação.
    # Ver o quadro "COMO TROCAR OS DADOS SIMULADOS" no topo de meteo/sensores.py.
    return sensores.obter(dados_clima())   # Lê os sensores (ou gera a simulação a partir do clima).


# ----------------------------------------------------------- carga do clima
try:                                           # "try" = tente executar; se der erro, vá para o "except".
    cl_om = dados_clima()                      # Open-Meteo, como baixada
except Exception as e:  # noqa: BLE001         # Pega QUALQUER erro (ex.: sem internet) e guarda em "e".
    # (o "# noqa: BLE001" só silencia um aviso de estilo do verificador de código)
    st.error(f"Não foi possível obter o clima da Open-Meteo: {e}")   # Mostra uma caixa vermelha de erro.
    st.stop()                                  # Para o script aqui: sem clima não dá para mostrar nada.
# Calcula os "limiares" de calor (o valor a partir do qual um dia conta como quente),
# sempre a partir da Open-Meteo original, para que a régua não mude quando trocamos a fonte.
lim = clima.limiares(cl_om)                    # régua de calor: sempre a da Open-Meteo

# ----------------------------------------------------------- sensores
try:
    # Para cada arquivo de sensor, pega (nome do arquivo, data da última modificação).
    # a.stat().st_mtime = momento em que o arquivo foi alterado pela última vez.
    # tuple(...) transforma em tupla, que o cache aceita como "chave".
    assinatura = tuple((a.name, a.stat().st_mtime) for a in sensores.arquivos())
    # Carrega os sensores. config.SENSORES_PLACEHOLDER também entra na chave do cache,
    # então ligar/desligar a simulação no config também força recalcular.
    sens = dados_sensores(assinatura, config.SENSORES_PLACEHOLDER)
    erro_sensores = None                       # Nenhum erro até aqui.
except Exception as e:  # noqa: BLE001
    sens, erro_sensores = None, str(e)         # Se deu erro: sem dados e guarda a mensagem para mostrar depois.
if sens is not None:                           # Se conseguimos dados dos sensores…
    # "sens" é uma tupla com 3 coisas; aqui "desempacotamos" em 3 variáveis:
    #   df_s     = tabela com todas as leituras (uma linha por leitura)
    #   rel_s    = relatório da limpeza (quantas linhas removidas etc.)
    #   simulado = True se os dados forem simulados (placeholder)
    df_s, rel_s, simulado = sens
    dia_s = sensores.diario(df_s)              # Resume as leituras em uma linha por sensor por dia (máx., mín.…).
    calib = sensores.calibrar(dia_s, cl_om)    # Calcula quanto Heliópolis é mais quente que a Open-Meteo.
else:                                          # Se NÃO há dados dos sensores…
    df_s = rel_s = dia_s = calib = None        # …todas essas variáveis ficam vazias (None)…
    simulado = False                           # …e não é simulação.
# Texto do aviso que aparece sempre que os dados dos sensores forem simulados.
# Strings lado a lado dentro de parênteses são "coladas" automaticamente pelo Python.
AVISO_SIMULADO = ("⚠️ **DADOS SIMULADOS (placeholder).** Ainda não há sensores instalados: estes "
                  "números são fictícios e servem só para mostrar como a análise vai funcionar. "
                  "Não cite estes valores. Para usar os dados reais, veja o topo de "
                  "`meteo/sensores.py`.")

# ----------------------------------------------------------- anos de saúde disponíveis
try:
    # Pega a lista de arquivos mensais do DATASUS e filtra só os anos COMPLETOS
    # (os 12 meses do ano + 3 meses seguintes, por causa do atraso de cobrança dos hospitais).
    anos_ok = saude.anos_completos(meses_saude())
    # Se a lista vier vazia, registramos um "erro" explicando o motivo; senão, nenhum erro (None).
    erro_saude = None if anos_ok else "nenhum ano completo disponível"
except Exception as e:  # noqa: BLE001
    anos_ok, erro_saude = [], str(e)           # Sem acesso ao DATASUS: lista vazia e guarda a mensagem.

# ------------------------------------------------------------------ filtros
# "with st.sidebar:" = tudo o que estiver indentado (recuado) abaixo vai para a BARRA LATERAL.
with st.sidebar:
    st.header("Escolhas")                       # Título da barra lateral.
    # st.radio = botões de opção (só um pode ser escolhido). O valor escolhido vai para "criterio".
    criterio = st.radio(
        "O que conta como calor",                # Texto acima das opções.
        list(config.CRITERIOS),                  # As opções são as CHAVES do dicionário CRITERIOS (ex.: "dia_quente").
        # format_func = como mostrar cada opção na tela. "lambda c: ..." é uma função de uma linha:
        # recebe a chave c e devolve o nome bonito guardado em config.CRITERIOS[c]["nome"].
        format_func=lambda c: config.CRITERIOS[c]["nome"],
        # help = texto do ícone "?" ao lado do título. As strings são coladas umas nas outras.
        help="**Dia quente**: sensação térmica máxima entre os 10% mais altos dos verões de "
             "1991–2020. **Noite quente**: temperatura mínima entre as 10% mais altas (o corpo "
             f"não descansa à noite). **Onda de calor**: {config.DIAS_ONDA} ou mais dias quentes "
             "seguidos.")
    # Lista das fontes de clima possíveis. "corrigida" só entra se existir calibração dos sensores.
    # ["corrigida"] if calib else [] → se calib existir, uma lista com "corrigida"; senão, lista vazia.
    opcoes_fonte = ["openmeteo"] + (["corrigida"] if calib else [])
    fonte = st.radio(
        "Fonte do clima", opcoes_fonte,
        # Aqui o format_func é o método .get de um dicionário: recebe a chave e devolve o texto.
        format_func={"openmeteo": "Open-Meteo (regional)",
                     "corrigida": "Heliópolis corrigida pelos sensores"
                                  # Se for simulação, acrescenta " (SIMULADO)" ao nome da opção.
                                  + (" (SIMULADO)" if simulado else "")}.get,
        help="**Open-Meteo**: estimativa para uma área de vários km². **Heliópolis corrigida**: "
             "a mesma série desde 1991, somada à diferença que os sensores dentro de Heliópolis "
             "medem em relação à Open-Meteo. A régua de calor (limiar) continua a mesma, então "
             "a diferença aparece como mais dias de calor.")
    # st.selectbox = lista suspensa (dropdown). Opções = grupos de internação (todas, respiratórias…).
    # format_func=saude.GRUPOS.get mostra o nome legível de cada grupo.
    grupo = st.selectbox("Tipo de internação", saude.GRUPOS_DIARIOS, format_func=saude.GRUPOS.get)
    # Anos marcados por padrão: os anos disponíveis que NÃO são da pandemia (2020/2021)…
    # …e [-3:] pega só os 3 últimos da lista.
    padrao = [a for a in anos_ok if a not in config.ANOS_PANDEMIA][-3:]
    # st.multiselect = caixa onde dá para escolher VÁRIOS itens. Devolve a lista dos anos escolhidos.
    anos = st.multiselect("Anos (internações)", anos_ok, default=padrao,
                          help="Na primeira vez, cada ano leva alguns minutos para baixar "
                               "(15 arquivos do DATASUS). Depois fica salvo.")
    # st.number_input = campo de número com botões + e −.
    pop_h = st.number_input(
        "População de Heliópolis",
        min_value=10_000, max_value=300_000,     # limites permitidos (o "_" é só para facilitar a leitura do número)
        value=config.POP_HELIOPOLIS,             # valor inicial (55.583, do Censo 2022)
        step=5_000,                              # quanto cada clique em + ou − muda
        help="Usada só no gráfico de internações por 100 mil habitantes. "
             "55.583 = favela de Heliópolis no Censo 2022 (IBGE). A área dos CEPs pode ter "
             "mais gente: o Observatório De Olho na Quebrada estima até 200 mil.")
    # st.toggle = interruptor liga/desliga. value=True → começa ligado. Devolve True ou False.
    sem_feriados = st.toggle(
        "Descontar feriados e fim de ano", value=True,
        help="Tira da comparação feriados, Carnaval e 24/12–01/01. Nesses dias muita gente "
             "viaja e os hospitais internam menos; como eles caem no verão, sem descontar o "
             "calor pareceria diminuir as internações.")
    st.divider()                                 # Linha horizontal separadora.
    # st.caption = texto pequeno e cinza. ', '.join(lista) junta a lista de CEPs separando por vírgula.
    # "  \n" (dois espaços + quebra) = quebra de linha no Markdown.
    st.caption(f"**Heliópolis** = CEP começando com {', '.join(config.CEPS_HELIOPOLIS)}.  \n"
               f"**Região do Ipiranga** = CEP começando com {', '.join(config.CEPS_REGIAO)} "
               "(inclui Heliópolis).  \n"
               "**Clima:** Open-Meteo · **Saúde:** DATASUS/SIH (internações de urgência no SUS)")

# A partir daqui voltamos para a área principal (fora do "with st.sidebar").
crit = config.CRITERIOS[criterio]   # Pega o dicionário com as informações do critério escolhido (nome, variável…).
limiar = lim[crit["var"]]           # O valor de corte (°C) para a variável desse critério (ex.: sensação máxima).
corrigida = fonte == "corrigida"    # True se o usuário escolheu a série corrigida pelos sensores; senão False.
# Clima usado em todas as análises: Open-Meteo ou a série corrigida pelos sensores
# Se "corrigida": soma a diferença dos sensores à Open-Meteo (sensores.corrigir) e marca de novo
# quais dias são de calor usando a MESMA régua (lim). Se não, usa a Open-Meteo original.
cl = clima.marcar_calor(sensores.corrigir(cl_om, calib), lim=lim) if corrigida else cl_om

# ---------------------------------------------------- download das internações
r = None                            # "r" vai guardar o resultado das análises. Começa vazio.
if anos and not erro_saude:         # Só continua se algum ano foi escolhido E o DATASUS está acessível.
    # Monta a lista de meses (formato "AAMM") que ainda NÃO estão salvos no cache em disco.
    # saude._meses_do_ano(a) devolve os 15 arquivos necessários para o ano a.
    # O "{... for ...}" com chaves cria um CONJUNTO (sem repetidos); sorted(...) põe em ordem.
    # ".exists()" verifica se o arquivo .parquet daquele mês já existe na pasta de cache.
    faltando = sorted({m for a in anos for m in saude._meses_do_ano(a)
                       if not (config.CACHE / f"internacoes_{m}.parquet").exists()})
    if faltando:                    # Se falta baixar algum mês…
        barra = st.progress(0.0)    # …cria uma barra de progresso começando em 0%.
        for i, m in enumerate(faltando):   # enumerate dá o número da volta (i = 0, 1, 2…) e o mês (m).
            # Atualiza a barra: fração concluída (i/total) e um texto explicando o que está baixando.
            # m[:2] = os 2 primeiros caracteres (ano, ex.: "23"); m[2:] = o resto (mês, ex.: "01").
            barra.progress(i / len(faltando), f"Baixando internações do DATASUS: arquivo "
                                              f"{i + 1} de {len(faltando)} (20{m[:2]}/{m[2:]}) "
                                              "· ~1 min cada")
            saude.baixar_mes(m)     # Baixa o arquivo do mês, filtra e salva no cache.
        barra.empty()               # Remove a barra de progresso da tela quando terminar.
    try:
        # Carrega as internações por dia (do cache). tuple(sorted(anos)) = tupla ordenada (exigência do cache).
        internacoes = dados_saude(tuple(sorted(anos)))
        # Faz TODAS as análises de uma vez e guarda o resultado (um dicionário) em "r".
        # Recebe: clima, internações, grupo, critério de calor, população de Heliópolis (como número
        # inteiro), se desconta feriados e a régua de calor.
        r = cruzamento.analisar(cl, internacoes, grupo, criterio, int(pop_h), sem_feriados,
                                limiares=lim)
    except Exception as e:  # noqa: BLE001
        st.error(f"Erro ao preparar os dados de saúde: {e}")   # Mostra o erro, mas o painel continua.

# ------------------------------------------------------------------ abertura
st.title("Calor e saúde em Heliópolis")   # Título grande da página.
# st.markdown = texto com formatação Markdown (**negrito** etc.). Strings coladas formam um parágrafo só.
st.markdown(
    f"Este painel cruza o **clima** de Heliópolis desde 1991 (Open-Meteo) com as **internações "
    f"de urgência no SUS** (DATASUS). **{crit['nome']}** = "
    # cruzamento.descricao(...) escreve em palavras o critério, ex.: "sensação térmica máxima ≥ 33,5 °C".
    f"**{cruzamento.descricao(criterio, limiar)}**. O limiar é o valor que só os 10% mais quentes "
    # config.CLIMATOLOGIA é uma tupla (1991, 2020); [0] é o primeiro ano e [1] o segundo.
    f"dos verões de {config.CLIMATOLOGIA[0]}–{config.CLIMATOLOGIA[1]} alcançavam. Como Heliópolis "
    "tem poucas "
    "internações por dia, mostramos também a **região do Ipiranga**, que inclui Heliópolis e vive "
    "o mesmo clima, e a **cidade** como referência.")

if corrigida:                       # Se estamos usando a série corrigida pelos sensores…
    # …mostra uma caixa azul (st.info) dizendo quanto foi somado à máxima e à mínima.
    # O "'+' if ... >= 0 else ''" coloca o sinal + na frente de números positivos.
    st.info(f"**Fonte do clima: Heliópolis corrigida pelos sensores.** A série da Open-Meteo foi "
            f"somada a {'+' if calib['delta_tmax'] >= 0 else ''}{f(calib['delta_tmax'], 1)} °C na "
            f"máxima e {'+' if calib['delta_tmin'] >= 0 else ''}{f(calib['delta_tmin'], 1)} °C na "
            f"mínima, a diferença medida pelos sensores em {calib['dias']} dias.")
    if simulado:                    # E se os sensores forem simulados…
        st.warning(AVISO_SIMULADO)  # …mostra o aviso amarelo de dados fictícios.
if erro_saude:                      # Se o DATASUS não está disponível…
    st.warning(f"Os dados do DATASUS não estão disponíveis agora ({erro_saude}). "
               "As abas de clima e sensores continuam funcionando.")
elif not anos:                      # Senão, se nenhum ano foi escolhido…
    st.info("Escolha pelo menos um ano na barra lateral para ver as internações.")
elif r is not None:                 # Senão, se a análise deu certo…
    with st.container(border=True): # …cria uma caixa com borda…
        st.markdown("#### O que os dados mostram")   # (#### = subtítulo pequeno)
        for item in r["conclusoes"]:                # …e escreve cada conclusão (título em negrito + texto).
            st.markdown(f"**{item['titulo']}** {item['texto']}")

# Cria 4 ABAS. st.tabs devolve 4 "recipientes", que guardamos em 4 variáveis (desempacotamento).
# Tudo o que for escrito dentro de "with aba_x:" aparece naquela aba.
aba_clima, aba_saude, aba_sensores, aba_metodo = st.tabs(
    ["🌡️ O calor está aumentando?", "🏥 Calor × internações", "📡 Sensores da UNAS",
     "📄 Como foi feito"])

# ============================================================ 1. clima
with aba_clima:                     # Tudo o que estiver recuado aqui dentro aparece na aba "O calor está aumentando?".
    anual = clima.resumo_anual(cl)  # Tabela com 1 linha por ano: nº de dias de calor em cada critério.
    tend = clima.tendencia(anual, criterio)   # Reta de tendência (quantos dias a mais por década).
    dec = clima.por_decada(anual, criterio)   # Média de dias de calor por ano em cada década.
    completos = anual[anual["completo"]]      # Só os anos completos (o ano atual ainda não terminou).

    a, b, c = st.columns(3)         # Divide a linha em 3 colunas lado a lado (a, b, c).
    if len(dec) >= 2:               # Só compara décadas se houver pelo menos duas.
        # st.metric = "cartão" com um número grande. Aqui: média da PRIMEIRA década (.iloc[0]).
        a.metric(f"{crit['plural']} por ano · {dec['rotulo'].iloc[0]}", f(dec["mean"].iloc[0]))
        # Média da ÚLTIMA década (.iloc[-1]) e, embaixo (delta), a diferença em relação à primeira.
        # delta_color="inverse" → aumento aparece em VERMELHO (mais calor é ruim).
        b.metric(f"{crit['plural']} por ano · {dec['rotulo'].iloc[-1]}", f(dec["mean"].iloc[-1]),
                 delta=f"{f(dec['mean'].iloc[-1] - dec['mean'].iloc[0])} dias",
                 delta_color="inverse")
    # Terceiro cartão: tendência em dias por década. Se não der para calcular, mostra "–";
    # senão, mostra o número com 1 casa e o sinal "+" quando positivo.
    c.metric("Tendência (dias a mais por década)",
             "–" if pd.isna(tend["por_decada"])
             else f"{'+' if tend['por_decada'] > 0 else ''}{f(tend['por_decada'], 1)}")

    st.markdown(f"##### {crit['plural']} por ano")   # Subtítulo (##### = título pequeno).
    st.caption(f"Cada barra conta os dias do ano com {cruzamento.descricao(criterio, limiar)}. "
               "A linha tracejada é a tendência. O ano atual (barra vazada) ainda não terminou.")
    fig = go.Figure()               # Cria um gráfico vazio.
    # Adiciona barras: x = anos, y = nº de dias de calor no ano.
    fig.add_bar(x=anual["ano"], y=anual[criterio],
                # Nome da série na legenda (depende da fonte escolhida).
                name="Heliópolis corrigida" if corrigida else "dias de calor",
                # Barras laranja; o ano incompleto ("completo" = False) fica vazado.
                # [COR["heliopolis"]] * len(anual) = lista repetindo a mesma cor para cada ano.
                marker=estilo_barras([COR["heliopolis"]] * len(anual), anual["completo"]),
                # Texto ao passar o mouse. %{x} e %{y} são substituídos pelos valores da barra;
                # <extra></extra> esconde a caixinha extra com o nome da série.
                hovertemplate="%{x}: %{y} dias<extra></extra>")
    if corrigida:   # mostra quanto a correção muda em relação à Open-Meteo
        anual_om = clima.resumo_anual(cl_om)   # Mesmo resumo, mas da Open-Meteo original.
        # Linha azul com pontos (mode="lines+markers") para comparar com as barras corrigidas.
        fig.add_scatter(x=anual_om["ano"], y=anual_om[criterio], name="Open-Meteo (regional)",
                        mode="lines+markers", line=dict(color=COR["cidade"], width=2),
                        marker=dict(size=6), hovertemplate="%{x}: %{y} dias (Open-Meteo)"
                                                           "<extra></extra>")
    if len(tend["x"]):              # Se existe reta de tendência (lista não vazia)…
        # …desenha a reta tracejada (dash="dash"). hoverinfo="skip" = não mostra nada ao passar o mouse.
        fig.add_scatter(x=tend["x"], y=tend["y"], mode="lines", name="tendência",
                        line=dict(color=TINTA, dash="dash", width=2), hoverinfo="skip")
    fig.update_yaxes(title="dias no ano")      # Título do eixo vertical.
    mostrar(fig, 360, legenda=corrigida)       # Desenha com 360 px; a legenda só aparece na série corrigida.
    if corrigida:
        # Explicação extra quando a série corrigida está em uso (e aviso se for simulação).
        st.caption("Barras = série corrigida pelos sensores; linha azul = Open-Meteo original. "
                   "A distância entre as duas mostra quantos dias de calor a estimativa regional "
                   "deixa de ver em Heliópolis." + (" **Valores simulados.**" if simulado else ""))

    # Subtítulo e explicação do mapa de calor.
    st.markdown("##### Em que meses o calor aparece")
    st.caption(f"Número de dias de calor em cada mês. Quanto mais escuro, mais dias. Mostra se o "
               "calor está chegando mais cedo, indo até mais tarde ou ficando mais forte no "
               "auge do verão.")
    mapa = clima.mapa_ano_mes(cl, criterio)    # Tabela ano × mês com o nº de dias de calor.
    # go.Heatmap = "mapa de calor": uma grade de quadradinhos coloridos conforme o valor.
    fig = go.Figure(go.Heatmap(
        z=mapa.values,              # Os valores (cores) da grade.
        x=MESES,                    # Rótulos das colunas: jan, fev, mar…
        y=mapa.index,               # Rótulos das linhas: os anos.
        colorscale="Oranges",       # Escala de cores: do laranja claro ao escuro.
        xgap=2, ygap=2,             # Espaço de 2 px entre os quadradinhos.
        colorbar=dict(title="dias", thickness=12),   # Barra de legenda das cores.
        hovertemplate="%{x}/%{y}: %{z} dias<extra></extra>"))   # Ao passar o mouse: "jan/2024: 5 dias".
    # autorange="reversed" inverte o eixo (anos antigos em cima); dtick=5 mostra um rótulo a cada 5 anos.
    fig.update_yaxes(autorange="reversed", dtick=5)
    # Desenha direto (sem a função mostrar), com 620 px de altura.
    st.plotly_chart(grafico(fig, 620), width="stretch", config=CONFIG_GRAFICO)
    # Legenda da fonte. O começo do texto muda conforme a série corrigida/simulada está em uso.
    st.caption(("Série corrigida pelos sensores (simulados). " if corrigida and simulado else
                "Série corrigida pelos sensores. " if corrigida else "") +
               "Fonte: Open-Meteo (reanálise ERA5) para o ponto central de Heliópolis. É uma "
               "estimativa para uma área de vários km²; dentro da favela, com casas coladas, laje e "
               "pouca árvore, o calor costuma ser maior.")

# ============================================================ 2. saúde
with aba_saude:                     # Aba "Calor × internações".
    if r is None:                   # Se não há resultado das análises (sem anos, sem DATASUS ou erro)…
        st.info("Sem dados de internações para os filtros escolhidos.")
    else:
        # Três variáveis de uma vez: a tabela diária, o nome do grupo em minúsculas e a variável de clima.
        tab, tipo, vcl = r["tabela"], saude.GRUPOS[grupo].lower(), r["var"]
        nome_var = cruzamento.TEXTO_VAR[vcl]   # Nome legível da variável, ex.: "sensação térmica máxima".

        # ---- 2.1 por faixa
        st.header("Quanto mais quente, mais internações?")   # Título de seção.
        st.caption(f"Dias de novembro a março, agrupados pela {nome_var}. Cada barra mostra quanto "
                   f"as internações ({tipo}) ficaram acima (ou abaixo) do normal para aquela época. "
                   "Em % dá para pôr lugares de tamanhos diferentes no mesmo gráfico.")
        fx = r["faixas"]            # Tabela: variação (%) por faixa de temperatura e por lugar.
        fig = go.Figure()
        for rec, nome in saude.RECORTES.items():   # Para cada lugar (código, nome)…
            d = fx[fx["recorte"] == rec]           # …só as linhas daquele lugar.
            fig.add_bar(
                x=d["faixa"].astype(str), y=d["variacao"], name=nome,   # x = faixa; y = % acima do normal.
                # Barra cheia se confiável; vazada se pode ser acaso.
                marker=estilo_barras([COR[rec]] * len(d), d["significativo"]),
                # Texto em cima de cada barra, ex.: "+12%". textposition="outside" = fora da barra.
                text=[var(v) for v in d["variacao"]], textposition="outside", textfont_size=13,
                cliponaxis=False,   # Não corta o texto se ele passar da borda do gráfico.
                # Texto ao passar o mouse, montado para cada barra com zip (anda por várias listas juntas).
                # "<br>" = quebra de linha dentro da caixinha.
                hovertext=[f"{nome} · {fa}<br>{dias} dias<br>{f(o, 1)} internações/dia "
                           f"(normal {f(n, 1)})<br>faixa provável: {var(lo)} a {var(hi)}"
                           for fa, dias, o, n, lo, hi in zip(d["faixa"], d["dias"], d["obs_dia"],
                                                             d["normal_dia"], d["ic_inf"],
                                                             d["ic_sup"])],
                hoverinfo="text")   # Usa exatamente o hovertext acima.
        fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))   # Linha horizontal no zero (= "normal").
        # Esconde as barras da legenda (barras vazadas apareceriam vazadas lá também).
        fig.update_traces(selector=dict(type="bar"), showlegend=False)
        for rec, nome in saude.RECORTES.items():   # legenda sempre com a cor cheia
            # Truque: um "ponto invisível" (x e y = None) só para aparecer na legenda com um quadrado cheio.
            fig.add_scatter(x=[None], y=[None], name=nome, mode="markers",
                            marker=dict(symbol="square", size=13, color=COR[rec]))
        fig.update_yaxes(title="% acima do normal", ticksuffix="%")   # ticksuffix põe "%" nos números do eixo.
        fig.update_xaxes(title=nome_var)
        mostrar(fig, 420)
        # Tabela com 1 linha por faixa (drop_duplicates tira as repetidas dos 3 lugares) e o nº de dias.
        dias_faixa = fx.drop_duplicates("faixa")[["faixa", "dias"]]
        # Escreve "até 27 °C: 12 · 27–30 °C: 40 · …". .values devolve as linhas como pares (faixa, dias).
        st.caption("Barra cheia = diferença confiável · barra vazada = pode ser acaso. "
                   "Dias em cada faixa: " + " · ".join(f"{a}: {b}" for a, b in dias_faixa.values))

        # Subtítulo do gráfico de pontos.
        st.markdown("##### Dia a dia: cada ponto é um dia de verão")
        # Botões para escolher o lugar do gráfico de pontos. horizontal=True = lado a lado;
        # index=1 = começa no 2º item (a região); label_visibility="collapsed" esconde o rótulo "Ver".
        lugar = st.radio("Ver", list(saude.RECORTES), format_func=saude.RECORTES.get,
                         horizontal=True, index=1, label_visibility="collapsed")
        cv = f"{cruzamento.col(lugar, grupo)}__var"   # Nome da coluna com a variação % daquele lugar/grupo.
        v = tab[tab["verao"]].dropna(subset=[cv])     # Só dias de verão com variação calculada.
        # go.Scatter com mode="markers" = gráfico de pontos (dispersão).
        fig = go.Figure(go.Scatter(
            x=v[vcl], y=v[cv], mode="markers",        # x = temperatura do dia; y = % acima do normal.
            marker=dict(color=COR[lugar], size=8, opacity=.6, line_width=0),   # pontos semitransparentes
            # customdata = dados extras para a caixinha do mouse: a data (dd/mm/aaaa) e o nº de internações.
            # np.c_[a, b] junta as duas colunas lado a lado.
            customdata=np.c_[v["data"].dt.strftime("%d/%m/%Y"), v[cruzamento.col(lugar, grupo)]],
            # %{customdata[0]} = data; %{x:.1f} = temperatura com 1 casa; %{y:+.0f} = variação com sinal.
            hovertemplate="%{customdata[0]}<br>%{x:.1f} °C<br>%{customdata[1]} internações "
                          "(%{y:+.0f}% vs. normal)<extra></extra>"))
        if len(v) > 2:              # Com pelo menos 3 pontos dá para traçar uma reta de tendência.
            a_, b_ = np.polyfit(v[vcl], v[cv], 1)     # Ajusta a reta y = a_·x + b_.
            # 30 valores de x igualmente espaçados entre a menor e a maior temperatura.
            xs = np.linspace(v[vcl].min(), v[vcl].max(), 30)
            fig.add_scatter(x=xs, y=a_ * xs + b_, mode="lines",   # Desenha a reta tracejada.
                            line=dict(color=TINTA, dash="dash", width=2), hoverinfo="skip")
        fig.add_hline(y=0, line=dict(color=CINZA, width=1))       # Linha do "normal" (0%).
        fig.update_xaxes(title=f"{nome_var} do dia (°C)")
        fig.update_yaxes(title="% acima do normal", ticksuffix="%")
        mostrar(fig, 380, legenda=False)
        # Pega a linha da correlação do lugar escolhido (rho, p-valor, nº de dias).
        c = r["correlacao"].set_index("recorte").loc[lugar]
        # Explica a correlação. p_valor < 0,05 → "significativa" (pouca chance de ser acaso).
        st.caption(f"Linha tracejada = tendência. Correlação de Spearman: ρ = {f(c['rho'], 2)} "
                   f"({'significativa' if c['p_valor'] < .05 else 'não significativa'}, "
                   f"{c['dias']} dias). ρ vai de −1 a +1; positivo = quanto mais calor, mais "
                   "internações. Valores de 0,1 a 0,3 já são comuns aqui, porque muita coisa além "
                   "do calor leva alguém ao hospital. Em Heliópolis os pontos espalham muito porque "
                   "há poucos casos por dia.")

        # ---- 2.2 defasagem
        st.divider()                # Linha separadora.
        st.header("Quando o efeito aparece?")
        st.caption(f"Internações ({tipo}) no dia de calor (0) e nos dias seguintes, comparadas ao "
                   "normal. Mostra por quantos dias o calor continua pesando e, portanto, por quanto "
                   "tempo vale manter o alerta. Ponto cheio = confiável; ponto vazado = pode ser "
                   "acaso.")
        lg = r["defasagem"]         # Tabela: variação % em cada "dias depois" (0 a 7), por lugar.
        fig = go.Figure()
        for rec, nome in saude.RECORTES.items():   # Uma linha para cada lugar.
            d = lg[lg["recorte"] == rec]
            fig.add_scatter(
                x=d["dias_depois"], y=d["variacao"], name=nome, mode="lines+markers",
                line=dict(color=COR[rec], width=2),
                # Ponto cheio (cor do lugar) se confiável; ponto branco (vazado) se pode ser acaso.
                # O contorno (line) é sempre da cor do lugar.
                marker=dict(size=10, color=[COR[rec] if s else "white" for s in d["significativo"]],
                            line=dict(color=COR[rec], width=2)),
                # Dados extras para o mouse: limites inferior e superior do intervalo de 95%.
                customdata=np.c_[d["ic_inf"], d["ic_sup"]],
                # As chaves duplas {{ }} dentro de uma f-string viram chaves simples no texto final
                # (necessárias porque o Plotly usa %{x}, e a f-string também usa { }).
                hovertemplate=f"{nome}<br>%{{x}} dia(s) depois: %{{y:+.0f}}%<br>faixa provável: "
                              "%{customdata[0]:+.0f}% a %{customdata[1]:+.0f}%<extra></extra>")
        fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))   # Linha do normal.
        fig.update_xaxes(title="dias depois do dia de calor", dtick=1)   # dtick=1 → um rótulo por dia.
        fig.update_yaxes(title="% acima do normal", ticksuffix="%")
        mostrar(fig, 380)

        # ---- 2.3 comparação
        st.divider()
        st.header("Nos dias de calor, Heliópolis sofre mais?")
        comp = r["comparacao"]      # Resultado da comparação entre os lugares.
        t = comp["tabela"]          # Tabela com 1 linha por lugar.
        a, b = st.columns(2)        # Duas colunas lado a lado.
        with a:                     # Coluna da esquerda.
            st.markdown("##### Quanto as internações mudam nos dias de calor")
            st.caption(f"Dias de calor e os {config.DIAS_DEPOIS} seguintes. Cada lugar é comparado "
                       "com o seu próprio normal, então o tamanho da população não importa. "
                       "Barra vazada = pode ser acaso.")
            fig = go.Figure(go.Bar(
                x=t["lugar"], y=t["variacao"],        # Uma barra por lugar.
                # [COR[x] for x in t["recorte"]] = a cor de cada lugar, na ordem da tabela.
                marker=estilo_barras([COR[x] for x in t["recorte"]], t["significativo"]),
                # Texto dentro da barra (textposition="inside"), encostado na base (insidetextanchor="start").
                text=[var(x) for x in t["variacao"]], textposition="inside",
                insidetextanchor="start", textfont=dict(
                    # Texto branco nas barras cheias; cinza escuro nas vazadas (para ser legível).
                    size=17, color=["white" if s_ else TINTA for s_ in t["significativo"]]),
                # error_y = "bigodes" de erro: mostram o intervalo de 95% de cada barra.
                # symmetric=False → o tamanho para cima e para baixo pode ser diferente.
                error_y=dict(type="data", symmetric=False, color=CINZA, thickness=1.5, width=6,
                             array=t["ic_sup"] - t["variacao"],        # quanto sobe a partir do topo da barra
                             arrayminus=t["variacao"] - t["ic_inf"]),  # quanto desce
                hovertext=[f"{lu}<br>{f(o, 1)} internações/dia nos dias de calor<br>normal: "
                           f"{f(n, 1)}<br>faixa provável: {var(lo)} a {var(hi)}"
                           for lu, o, n, lo, hi in zip(t["lugar"], t["obs_dia"], t["normal_dia"],
                                                       t["ic_inf"], t["ic_sup"])],
                hoverinfo="text"))
            fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
            # Título do eixo vertical, desenha o gráfico (sem legenda) e explica o traço de erro.
            fig.update_yaxes(title="% acima do normal", ticksuffix="%")
            mostrar(fig, 380, legenda=False)
            st.caption("O traço cinza em cada barra é a faixa provável (intervalo de 95%). "
                       "Em Heliópolis ela é larga porque há poucos casos.")
        with b:                     # Coluna da direita.
            st.markdown("##### Internações por 100 mil habitantes, por dia")
            tx = t.dropna(subset=["taxa_normal"])  # Só lugares com taxa (a região não tem população conhecida).
            st.caption(f"Cinza = o normal para aqueles mesmos dias; cor = o que aconteceu nos dias "
                       f"de calor. Heliópolis: {milhar(pop_h)} hab.; cidade: "
                       f"{milhar(config.POP_SP)} hab. A região não aparece porque a população "
                       "exata dos CEPs não é publicada.")
            fig = go.Figure()
            # 1ª série de barras: a taxa NORMAL (cinza).
            fig.add_bar(x=tx["lugar"], y=tx["taxa_normal"], name="normal para a época",
                        marker=dict(color=CINZA, line_width=0),
                        text=[f(x, 1) for x in tx["taxa_normal"]], textposition="outside",
                        textfont_size=15, cliponaxis=False,
                        hovertemplate="%{x}<br>normal: %{y:.1f} por 100 mil<extra></extra>")
            # 2ª série: a taxa nos DIAS DE CALOR (cor de cada lugar).
            fig.add_bar(x=tx["lugar"], y=tx["taxa_calor"], name="dias de calor",
                        marker=dict(color=[COR[x] for x in tx["recorte"]], line_width=0),
                        text=[f(x, 1) for x in tx["taxa_calor"]], textposition="outside",
                        textfont_size=15, cliponaxis=False,
                        hovertemplate="%{x}<br>dias de calor: %{y:.1f} por 100 mil<extra></extra>")
            fig.update_yaxes(title="internações por 100 mil hab. por dia")
            # barmode="group" → as duas barras de cada lugar ficam lado a lado (e não empilhadas).
            mostrar(fig.update_layout(barmode="group"), 380)

        ts = t.set_index("recorte")   # Tabela indexada pelo lugar, para pegar cada linha pelo nome.
        # Uma linha (Series) para cada lugar: h = Heliópolis, rg = região, ci = cidade.
        h, rg, ci = ts.loc["heliopolis"], ts.loc["regiao"], ts.loc["cidade"]
        with st.container(border=True):   # Caixa com borda para o resultado.
            if pd.isna(ci["variacao"]):   # Sem resultado para a cidade → sem dados.
                st.markdown("Sem dados suficientes para comparar.")
            else:
                # Escolhe a frase de leitura conforme o que foi confiável.
                if h["significativo"]:
                    leitura = "Em Heliópolis o aumento já é grande o bastante para **não ser acaso**."
                elif rg["significativo"]:
                    leitura = ("Heliópolis sozinha tem poucos casos para afirmar, mas **na região do "
                               "Ipiranga a mudança não é acaso**. Como a região inclui Heliópolis e "
                               "vive o mesmo clima, é o melhor indício do que acontece lá.")
                # Se nenhum dos dois foi confiável:
                else:
                    leitura = ("Nem em Heliópolis nem na região a mudança foi grande o bastante para "
                               "descartar o acaso.")
                dr = comp["diferenca"]["regiao"]   # Teste "a região reagiu diferente da cidade?".
                if dr["significativo"]:
                    # Acrescenta (+=) quantas vezes a região reagiu em relação à cidade.
                    leitura += (f" A região reagiu **{f(dr['vezes'], 2)} vezes** o que a cidade "
                                "reagiu, e a diferença não é acaso.")
                # Frase final: o que aconteceu em cada lugar + a leitura.
                st.markdown(f"**Resultado:** nos dias de calor as internações {mudou(h['variacao'])} "
                            f"em Heliópolis, {mudou(rg['variacao'])} na região do Ipiranga e "
                            f"{mudou(ci['variacao'])} na cidade. {leitura}")
        st.caption("A taxa por 100 mil também depende de quanto cada população usa o SUS: em "
                   "Heliópolis quase todos dependem do SUS, na cidade muitos têm plano de saúde. Por "
                   "isso a comparação de cada lugar consigo mesmo (gráfico da esquerda) é a mais "
                   "justa para medir o efeito do calor.")

        # ---- 2.4 arboviroses (análise mensal, à parte)
        st.divider()
        st.header("Dengue, chikungunya e zika × temperatura")
        st.caption("Estas doenças dependem do mosquito Aedes, que se reproduz mais rápido com calor e "
                   "água parada. O efeito aparece semanas depois, por isso a comparação é **por mês**: "
                   "internações por arboviroses (CID A90–A92) no mês × temperatura média e chuva do "
                   "mesmo mês e dos meses anteriores. Só os casos graves internam; é a ponta do "
                   "problema.")
        # Escolha do lugar. key="lugar_arbo" dá um nome único ao botão, porque já existe outro st.radio
        # parecido nesta aba (o Streamlit exige nomes diferentes para widgets diferentes).
        rec_arbo = st.radio("Lugar", ["cidade", "regiao", "heliopolis"],
                            format_func=saude.RECORTES.get, horizontal=True,
                            key="lugar_arbo", label_visibility="collapsed")
        # Faz a análise mensal das arboviroses para o lugar escolhido.
        arbo = cruzamento.arboviroses_mensal(cl, internacoes, rec_arbo)
        # Cores das duas variáveis de clima (vermelho para temperatura, roxo para chuva).
        cor_arbo = {"Temperatura média": "#e34948", "Chuva acumulada": "#6250d6"}
        if arbo["mensal"]["internacoes"].sum() == 0:   # Nenhum caso no período?
            st.info("Não houve internações por arboviroses neste lugar e período.")
        else:
            a, b = st.columns([2, 3])   # Duas colunas: a da esquerda com peso 2, a da direita com peso 3.
            with a:
                st.markdown("##### Quanto o clima anterior explica os casos")
                ca = arbo["correlacao"]  # Tabela: rho por variável e por meses de antecedência.
                fig = go.Figure()
                # Agrupa por variável (temperatura, chuva). sort=False mantém a ordem original.
                for var_nome, g in ca.groupby("variavel", sort=False):
                    sig = g["p_valor"] < .05   # True/False: cada correlação é significativa?
                    fig.add_bar(
                        # Rótulos do eixo x; [:len(g)] pega só quantos forem necessários.
                        x=["no mesmo mês", "1 mês antes", "2 meses antes"][:len(g)], y=g["rho"],
                        name=var_nome, marker=estilo_barras([cor_arbo[var_nome]] * len(g), sig),
                        text=[f(x, 2) for x in g["rho"]], textposition="outside",
                        cliponaxis=False,
                        hovertemplate=f"{var_nome}<br>%{{x}}: ρ = %{{y:.2f}}<extra></extra>")
                fig.update_traces(selector=dict(type="bar"), showlegend=False)   # Barras fora da legenda…
                for var_nome, cor_v in cor_arbo.items():     # legenda sempre com a cor cheia
                    # …e quadradinhos invisíveis no gráfico, só para a legenda (mesmo truque de antes).
                    fig.add_scatter(x=[None], y=[None], name=var_nome, mode="markers",
                                    marker=dict(symbol="square", size=13, color=cor_v))
                fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
                # range=[-1, 1.15] fixa o eixo de −1 a pouco acima de +1 (espaço para os rótulos).
                fig.update_yaxes(title="correlação (ρ de Spearman)", range=[-1, 1.15])
                mostrar(fig, 360)
                st.caption("ρ perto de +1 = meses mais quentes (ou chuvosos) vêm antes de mais "
                           "casos. Barra vazada = pode ser acaso.")
            with b:
                st.markdown("##### Mês a mês")
                # Importa a função que cria vários gráficos empilhados numa mesma figura.
                from plotly.subplots import make_subplots
                m = arbo["mensal"]       # Tabela mês a mês (internações, temperatura, chuva).
                # 2 linhas × 1 coluna; shared_xaxes=True → os dois gráficos usam o mesmo eixo de datas;
                # vertical_spacing = espaço entre eles; row_heights = o de cima ocupa 55% da altura.
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.08,
                                    row_heights=[.55, .45])
                # Gráfico de cima (row=1): barras com as internações por mês.
                fig.add_bar(x=m["mes"], y=m["internacoes"], name="internações",
                            marker_color=COR[rec_arbo], row=1, col=1,
                            hovertemplate="%{x|%m/%Y}: %{y} internações<extra></extra>")
                # %{x|%m/%Y} formata a data como "mês/ano".
                # Gráfico de baixo (row=2): linha da temperatura média do mês.
                fig.add_scatter(x=m["mes"], y=m["temp_media"], name="temperatura média",
                                mode="lines+markers", line=dict(color=cor_arbo["Temperatura média"],
                                                                width=2), row=2, col=1,
                                hovertemplate="%{x|%m/%Y}: %{y:.1f} °C<extra></extra>")
                fig.update_yaxes(title_text="internações", row=1, col=1)   # Título do eixo de cima.
                fig.update_yaxes(title_text="°C", row=2, col=1)            # Título do eixo de baixo.
                mostrar(fig, 360, legenda=False)
                st.caption("Em cima, internações por mês; embaixo, a temperatura média do mês. "
                           "Repare se os picos de casos vêm um ou dois meses depois dos meses quentes.")

# ============================================================ 3. sensores
# Paleta de cores para diferenciar os sensores (um sensor = uma cor).
CORES_SENSOR = ["#6250d6", "#e87ba4", "#008300", "#eda100", "#e34948", "#1baf7a"]
# Cor de cada faixa de risco do índice de calor, do cinza (sem risco) ao vinho (perigo extremo).
CORES_RISCO = {"sem risco": "#d6d5cf", "cautela": "#f5c46b", "cautela extrema": "#eb6834",
               "perigo": "#c4322f", "perigo extremo": "#7a1b1a"}


def instrucoes_sensores():          # Mostra na tela o passo a passo para usar os dados reais dos sensores.
    st.markdown(
        "**Como usar os dados reais dos sensores**\n\n"            # "\n\n" = linha em branco (novo parágrafo)
        "1. Exporte as leituras para arquivos `.csv` no formato abaixo.\n"
        "2. Dê aos sensores instalados **dentro de Heliópolis** um nome começando com "
        f"`{config.PREFIXO_SENSOR_HELIOPOLIS}` (ex.: `heliopolis_viela_01`). Só eles entram na "
        "calibração; os outros servem de controle.\n"
        "3. Salve os arquivos na pasta `data/sensores/` e recarregue a página. A simulação é "
        "desligada sozinha.\n\n"
        "**Formato** (uma linha por leitura; separador `;` ou `,`):")
    # st.table desenha uma tabela fixa. Aqui montamos uma tabela de 2 colunas: o nome de cada
    # coluna do CSV e o que ela significa.
    st.table(pd.DataFrame({
        "coluna": sensores.COLUNAS,
        "o que é": ["nome do sensor (ex.: heliopolis_viela_01)", "data e hora da leitura",
                    "temperatura do ar", "umidade relativa do ar (%)",
                    "C ou F (opcional; padrão C)"]}))
    # Botão que baixa um CSV de exemplo. .encode("utf-8-sig") converte o texto em bytes com
    # uma marca que faz o Excel abrir os acentos corretamente.
    st.download_button("Baixar arquivo-modelo (.csv)", sensores.modelo_csv().encode("utf-8-sig"),
                       "modelo_sensores.csv")


with aba_sensores:                  # Aba "Sensores da UNAS".
    st.header("Sensores da UNAS")
    if erro_sensores:               # Deu erro ao ler os sensores?
        st.error(f"Não foi possível ler os sensores: {erro_sensores}")
    elif df_s is None:              # Não há dados (nem reais nem simulados)?
        st.markdown("Ainda **não há dados dos sensores**. A Open-Meteo estima o clima de uma área "
                    "de vários km² e não enxerga o calor dentro das vielas de Heliópolis.")
        instrucoes_sensores()       # Mostra como colocar os dados.
    else:                           # Há dados.
        if simulado:                # Se forem simulados…
            st.warning(AVISO_SIMULADO)   # …aviso amarelo…
            # …e uma seção recolhível (expander) com as instruções para trocar pelos reais.
            with st.expander("Como trocar pelos dados reais"):
                instrucoes_sensores()
        # Dicionário {sensor: cor}. enumerate numera os sensores (i = 0, 1, 2…);
        # i % len(CORES_SENSOR) = resto da divisão: se houver mais sensores que cores, as cores recomeçam.
        cor_de = {sid: CORES_SENSOR[i % len(CORES_SENSOR)]
                  for i, sid in enumerate(sorted(df_s["sensor_id"].unique()))}

        a, b, c, d = st.columns(4)  # 4 cartões lado a lado com o resumo da limpeza.
        a.metric("Leituras válidas", milhar(rel_s["linhas_limpas"]))
        b.metric("Valores impossíveis removidos", milhar(rel_s["outliers_removidos"]))
        # Lacunas preenchidas = vazios que existiam (antes + os criados ao remover impossíveis)
        # menos os que continuaram vazios. max(..., 0) evita mostrar número negativo.
        c.metric("Lacunas preenchidas",
                 milhar(max(rel_s["ausentes_antes"] + rel_s["outliers_removidos"]
                            - rel_s["ausentes_depois"], 0)))
        d.metric("Sensores em °F convertidos", rel_s["sensores_em_fahrenheit"])
        st.caption("Resultado da limpeza automática (meteo/limpeza.py).")

        # ---- 3.1 índice de calor diário
        st.markdown("##### Índice de calor máximo do dia, por sensor")
        st.caption("O índice de calor junta temperatura e umidade (NOAA). Faixas: 27–32 °C "
                   "cautela · 32–41 °C cautela extrema · 41–54 °C perigo.")
        fig = go.Figure()
        for sid, g in dia_s.groupby("sensor_id"):   # Uma linha para cada sensor (sid = nome; g = seus dias).
            fig.add_scatter(x=g["data"], y=g["indice_calor_max"], name=str(sid),
                            mode="lines", line=dict(width=2, color=cor_de[sid]))
        # Pega a Open-Meteo só no mesmo período dos sensores (.between = entre a primeira e a última data).
        om = cl_om[cl_om["data"].between(dia_s["data"].min(), dia_s["data"].max())]
        # Linha cinza tracejada da sensação térmica máxima da Open-Meteo, para comparar.
        fig.add_scatter(x=om["data"], y=om["sensacao_max"], name="Open-Meteo (sensação máx.)",
                        mode="lines", line=dict(color=CINZA, dash="dash", width=2))
        # Pinta faixas horizontais de fundo (add_hrect) para cada nível de risco.
        # rgba(vermelho, verde, azul, opacidade): cores bem transparentes (8% a 12%).
        for y0, y1, cor in [(27, 32, "rgba(237,161,0,.08)"), (32, 41, "rgba(235,104,52,.10)"),
                            (41, 54, "rgba(227,73,72,.12)")]:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=cor, line_width=0)
        fig.update_yaxes(title="°C")
        mostrar(fig, 380)

        # ---- 3.2 calibração
        st.divider()
        st.markdown("##### Quanto Heliópolis é mais quente que a Open-Meteo?")
        if calib is None:           # Sem calibração (dados insuficientes)?
            st.info(f"Para calcular a correção são precisos pelo menos "
                    f"{sensores.MINIMO_DIAS_CALIBRACAO} dias completos de sensores com nome "
                    f"começando por `{config.PREFIXO_SENSOR_HELIOPOLIS}`.")
        else:
            a, b, c = st.columns(3)
            # Cartão: diferença média na máxima, com sinal. O "help" (ícone ?) mostra o nº de dias
            # e o quanto a diferença varia (desvio-padrão).
            a.metric("Máxima: Heliópolis − Open-Meteo",
                     f"{'+' if calib['delta_tmax'] >= 0 else ''}{f(calib['delta_tmax'], 1)} °C",
                     help=f"Média de {calib['dias']} dias; varia ±{f(calib['dp_tmax'], 1)} °C "
                          "de um dia para outro.")
            # Mesmo cartão para a mínima.
            b.metric("Mínima: Heliópolis − Open-Meteo",
                     f"{'+' if calib['delta_tmin'] >= 0 else ''}{f(calib['delta_tmin'], 1)} °C",
                     help=f"Média de {calib['dias']} dias; varia ±{f(calib['dp_tmin'], 1)} °C.")
            c.metric("Dias usados", calib["dias"])
            pares = calib["pares"]   # Tabela dia a dia: valores dos sensores e da Open-Meteo.
            fig = go.Figure()
            # Pontos laranja: máxima da Open-Meteo (x) × máxima medida em Heliópolis (y).
            fig.add_scatter(x=pares["tmax_om"], y=pares["tmax"], mode="markers",
                            name="máxima do dia", marker=dict(color=COR["heliopolis"], size=8,
                                                              opacity=.7),
                            hovertemplate="Open-Meteo %{x:.1f} °C<br>Heliópolis %{y:.1f} °C"
                                          "<extra></extra>")
            # Pontos azuis: o mesmo para a mínima.
            fig.add_scatter(x=pares["tmin_om"], y=pares["tmin"], mode="markers",
                            name="mínima do dia", marker=dict(color=COR["cidade"], size=8,
                                                              opacity=.7),
                            hovertemplate="Open-Meteo %{x:.1f} °C<br>Heliópolis %{y:.1f} °C"
                                          "<extra></extra>")
            # Limites da linha diagonal: do menor ao maior valor de todo o gráfico, com 1 °C de folga.
            lo = float(min(pares["tmin_om"].min(), pares["tmin"].min())) - 1
            hi = float(max(pares["tmax_om"].max(), pares["tmax"].max())) + 1
            # Linha diagonal y = x ("sem diferença"): pontos acima dela = Heliópolis mais quente.
            fig.add_scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="sem diferença",
                            line=dict(color=CINZA, dash="dash", width=1.5), hoverinfo="skip")
            fig.update_xaxes(title="Open-Meteo (°C)")
            fig.update_yaxes(title="sensores em Heliópolis (°C)")
            mostrar(fig, 400)
            st.caption("Cada ponto é um dia. Pontos acima da linha tracejada = Heliópolis mais "
                       "quente que a estimativa regional. Esta diferença alimenta a opção "
                       "**\"Heliópolis corrigida pelos sensores\"** em *Fonte do clima*, na barra "
                       "lateral, que refaz todas as análises com a série corrigida desde 1991.")

        # ---- 3.3 horas em risco e perfil do dia
        st.divider()
        a, b = st.columns(2)
        with a:                     # Coluna da esquerda: horas por dia em cada faixa de risco.
            st.markdown("##### Horas por dia em cada faixa de risco")
            hr = sensores.horas_em_risco(df_s)   # Tabela: sensor × faixa × horas por dia.
            # Ordem dos sensores no gráfico: do que passa MENOS horas em risco ao que passa MAIS
            # (soma das faixas diferentes de "sem risco", ordenada; .index.tolist() = lista de nomes).
            ordem = (hr[hr["faixa"] != "sem risco"].groupby("sensor_id")["horas_dia"].sum()
                     .sort_values().index.tolist())
            fig = go.Figure()
            for faixa_r in sensores.FAIXAS_RISCO[1]:   # Para cada faixa ("sem risco", "cautela"…)…
                # …pega as horas daquela faixa, com os sensores na ordem definida acima.
                g = hr[hr["faixa"] == faixa_r].set_index("sensor_id").reindex(ordem)
                # Barras horizontais (orientation="h"): y = sensores, x = horas.
                # A borda branca (line) separa visualmente os pedaços empilhados.
                fig.add_bar(y=ordem, x=g["horas_dia"], name=faixa_r, orientation="h",
                            marker=dict(color=CORES_RISCO[faixa_r], line=dict(color="white",
                                                                               width=1)),
                            hovertemplate=f"%{{y}}<br>{faixa_r}: %{{x:.1f}} h/dia<extra></extra>")
            # barmode="stack" empilha as faixas numa barra só por sensor (o total dá 24 h).
            fig.update_layout(barmode="stack", bargap=.35)
            fig.update_xaxes(title="horas por dia (média)", range=[0, 24], dtick=6)   # eixo de 0 a 24 h
            # Desenha com a legenda embaixo do gráfico (y negativo) e uma margem inferior maior para caber.
            # traceorder="normal" mantém as faixas na legenda na mesma ordem em que foram adicionadas.
            st.plotly_chart(grafico(fig, 400).update_layout(
                legend=dict(y=-0.28, yanchor="top", traceorder="normal"),
                margin=dict(b=90)), width="stretch", config=CONFIG_GRAFICO)
            st.caption("Pelo índice de calor de cada leitura. Sensores mais acima passam mais "
                       "horas em risco: são os pontos mais quentes.")
        with b:                     # Coluna da direita: perfil de temperatura ao longo do dia.
            st.markdown("##### A noite esfria?")
            pf = sensores.perfil_horario(df_s)   # Temperatura média em cada hora (0–23), por sensor.
            fig = go.Figure()
            for sid, g in pf.groupby("sensor_id"):   # Uma linha por sensor.
                fig.add_scatter(x=g["hora"], y=g["temperatura"], name=str(sid), mode="lines",
                                line=dict(width=2, color=cor_de[sid]),
                                hovertemplate=f"{sid}<br>%{{x}}h: %{{y:.1f}} °C<extra></extra>")
            # Faixa vertical roxa clarinha (add_vrect) destacando a madrugada (0h às 6h).
            fig.add_vrect(x0=0, x1=6, fillcolor="rgba(98,80,214,.07)", line_width=0,
                          annotation_text="madrugada", annotation_position="bottom left")
            fig.update_xaxes(title="hora do dia", dtick=3, range=[0, 23])   # rótulo a cada 3 horas
            fig.update_yaxes(title="temperatura média (°C)")
            st.plotly_chart(grafico(fig, 400).update_layout(
                legend=dict(y=-0.28, yanchor="top"), margin=dict(b=90)),
                width="stretch", config=CONFIG_GRAFICO)
            st.caption("Temperatura média em cada hora. Se a madrugada continua quente, o corpo não "
                       "se recupera do calor do dia, e isso pesa mais para idosos e crianças.")

        # Diferença dia a dia de cada sensor em relação à Open-Meteo.
        comp_s = sensores.comparar_com_openmeteo(dia_s, cl_om)
        with st.expander("Diferença de cada sensor para a Open-Meteo e dados diários"):   # Seção recolhível.
            if len(comp_s):         # Se houver dados…
                # …média das diferenças por sensor, arredondada para 1 casa.
                resumo = comp_s.groupby("sensor_id")[["dif_tmax", "dif_tmin"]].mean().round(1)
                # Renomeia as colunas para nomes legíveis.
                resumo.columns = ["máxima: sensor − Open-Meteo (°C)",
                                  "mínima: sensor − Open-Meteo (°C)"]
                st.dataframe(resumo)   # Tabela interativa (dá para ordenar clicando no título).
            st.dataframe(dia_s, hide_index=True)   # Tabela com o resumo diário de cada sensor (sem numeração).

# ============================================================ 4. método
with aba_metodo:                    # Aba "Como foi feito".
    # Texto longo em Markdown: "###" = título, "-" = item de lista, "**" = negrito, "\n" = quebra de linha.
    st.markdown(
        "### De onde vêm os dados\n"
        "- **Clima — Open-Meteo** (reanálise ERA5): temperatura máxima, mínima, sensação térmica e "
        "chuva, por dia, desde 1991, no ponto central de Heliópolis.\n"
        "- **Saúde — DATASUS/SIH**: internações de **urgência** pagas pelo SUS. Usamos a data da "
        "internação, o diagnóstico (CID-10), a idade, o desfecho (alta ou morte) e o **CEP de "
        "residência**, que permite separar Heliópolis e a região.\n"
        "- **Sensores da UNAS**: ainda não instalados. O painel já está pronto para recebê-los e, "
        "enquanto isso, mostra **dados simulados**, sempre marcados como tal. Com dados reais, a "
        "diferença medida entre Heliópolis e a Open-Meteo gera a série **Heliópolis corrigida**.\n"
        "- **Arboviroses**: internações por dengue, chikungunya e zika (CID A90–A92) do mesmo "
        "SIH, comparadas por mês com a temperatura média e a chuva.\n\n"
        "### Como os dados são tratados\n"
        "- Clima: datas padronizadas, dias repetidos removidos, valores impossíveis para SP "
        "(abaixo de −5 °C ou acima de 50 °C, mínima maior que a máxima) viram vazio, dias faltando "
        "aparecem como vazios (não somem).\n"
        "- Internações: só urgência e só a AIH principal (sem contar a mesma pessoa duas vezes), "
        "AIHs repetidas removidas, data da internação (e não a do pagamento), idade convertida para "
        "anos.\n"
        "- **Normal** = média de internações nos dias sem calor do mesmo mês e ano, ajustada pelo "
        "dia da semana. Assim o inverno e as segundas-feiras não atrapalham.\n"
        "- **Faixa provável** = intervalo de 95%. Se inclui o zero, a diferença pode ser acaso.\n\n"
        "### Limitações\n"
        "- O clima é uma estimativa regional; dentro da favela costuma ser mais quente.\n"
        "- Só entram **internações** no SUS: quem é atendido no pronto-socorro e liberado, ou usa "
        "plano de saúde, não aparece.\n"
        "- A região do Ipiranga é um **indicador indireto** de Heliópolis: inclui Heliópolis e o "
        "mesmo clima, mas também bairros com outras condições de vida.\n"
        "- Os resultados mostram **associação**, não provam causa.")
    if r is not None:               # Se há resultado das análises de saúde…
        tab = r["tabela"]           # …pega a tabela diária.
        # Colunas a exportar: as de clima e de calor + todas as colunas de contagem "<lugar>__<grupo>".
        # x.count("__") == 1 → nomes com exatamente um "__" (ex.: "regiao__todas"), deixando de fora
        # as colunas auxiliares como "regiao__todas__normal" (que têm dois "__").
        # A "\" no fim da linha continua o comando na linha de baixo.
        cols = ["data", "tmax", "tmin", "sensacao_max", "chuva", "dia_calor", "janela_calor"] + \
               [x for x in tab.columns if x.count("__") == 1]
        # Botão de download. to_csv com sep=";" e decimal="," → abre direto no Excel em português.
        # index=False → não exporta a numeração das linhas. utf-8-sig → acentos corretos no Excel.
        st.download_button("Baixar tabela diária clima × internações (.csv)",
                           tab[cols].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "calor_internacoes_diario.csv")
    st.caption("Para salvar um gráfico como imagem, passe o mouse sobre ele e clique no ícone de "
               "câmera no canto superior direito. Guia completo: docs/COMO_USAR.md.")
    # Botão para baixar a série de clima inteira (desde 1991) no mesmo formato.
    st.download_button("Baixar série de clima desde 1991 (.csv)",
                       cl.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       "clima_heliopolis_diario.csv")
