"""Calor e internações: Heliópolis × resto de São Paulo.

Rodar:  streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from meteo import clima, config, cruzamento, saude

COR = {"heliopolis": "#eb6834", "resto_sp": "#2a78d6"}       # identidade dos lugares
CINZA, TINTA = "#a3a29c", "#52514e"
SEM_BARRA = {"displayModeBar": False}

st.set_page_config(page_title="Calor e internações em Heliópolis", page_icon="🌡️",
                   layout="wide")


def f(x, casas=0):
    return "–" if pd.isna(x) else f"{x:.{casas}f}".replace(".", ",")


def milhar(x):
    return f"{x:,.0f}".replace(",", ".")


def var(x):
    if pd.isna(x):
        return "–"
    if abs(x) < 0.5:
        return "0%"
    return ("+" if x > 0 else "−") + f(abs(x)) + "%"


def mudou(x):
    if pd.isna(x) or abs(x) < 0.5:
        return "ficaram **praticamente iguais**"
    return f"**{'subiram' if x > 0 else 'caíram'} {f(abs(x))}%**"


def estilo_barras(cores, significativos):
    """Cheia = diferença confiável; vazada (só contorno) = pode ser acaso."""
    return dict(color=[c if s else "rgba(0,0,0,0)" for c, s in zip(cores, significativos)],
                line=dict(color=cores, width=2.5))


def grafico(fig, altura=380):
    fig.update_layout(height=altura, margin=dict(l=8, r=8, t=40, b=8), separators=",.",
                      bargap=.3, bargroupgap=.08, hoverlabel=dict(font_size=14),
                      legend=dict(orientation="h", y=1.08, x=0, font_size=14, title=None))
    fig.update_xaxes(showgrid=False, tickfont_size=13)
    fig.update_yaxes(tickfont_size=12, gridcolor="rgba(128,128,128,.15)")
    return fig


# ------------------------------------------------------------------ dados
@st.cache_data(show_spinner="Baixando o clima (Open-Meteo)…", ttl="12h")
def dados_clima():
    return clima.carregar()


@st.cache_data(show_spinner="Consultando o DATASUS…", ttl="24h")
def meses_saude():
    return saude.meses_disponiveis()


@st.cache_data(show_spinner="Contando as internações…")
def dados_saude(anos: tuple):
    return saude.carregar(list(anos))


try:
    anos_ok = saude.anos_completos(meses_saude())
except Exception as e:  # noqa: BLE001
    st.error(f"Não foi possível acessar o DATASUS: {e}")
    st.stop()

with st.sidebar:
    st.header("Escolhas")
    grupo = st.selectbox("Tipo de internação", list(saude.GRUPOS), format_func=saude.GRUPOS.get)
    padrao = [a for a in anos_ok if a not in config.ANOS_PANDEMIA][-3:]
    anos = st.multiselect("Anos", anos_ok, default=padrao,
                          help="Na primeira vez, cada ano leva alguns minutos para baixar "
                               "(15 arquivos do DATASUS). Depois fica salvo.")
    pop_h = st.number_input(
        "População de Heliópolis", min_value=10_000, max_value=300_000,
        value=config.POP_HELIOPOLIS, step=5_000,
        help="Usada só no gráfico de internações por 100 mil habitantes. "
             "55.583 = favela de Heliópolis no Censo 2022 (IBGE). A área dos CEPs pode ter "
             "mais gente: o Observatório De Olho na Quebrada estima até 200 mil.")
    sem_feriados = st.toggle(
        "Descontar feriados e fim de ano", value=True,
        help="Tira da comparação feriados, Carnaval e 24/12–01/01. Nesses dias muita gente "
             "viaja e os hospitais internam menos; como eles caem no verão, sem descontar o "
             "calor pareceria diminuir as internações.")
    st.divider()
    st.caption(f"**Heliópolis** = pacientes com CEP começando em "
               f"{', '.join(config.CEPS_HELIOPOLIS)}.  \n"
               "**Clima:** Open-Meteo · **Saúde:** DATASUS/SIH (internações de urgência no SUS)")

if not anos:
    st.info("Escolha pelo menos um ano na barra lateral.")
    st.stop()

faltando = sorted({m for a in anos for m in saude._meses_do_ano(a)
                   if not (config.CACHE / f"internacoes_{m}.parquet").exists()})
if faltando:
    barra = st.progress(0.0)
    for i, m in enumerate(faltando):
        barra.progress(i / len(faltando), f"Baixando internações do DATASUS: arquivo {i + 1} de "
                                          f"{len(faltando)} (20{m[:2]}/{m[2:]}) · ~1 min cada")
        saude.baixar_mes(m)
    barra.empty()

try:
    r = cruzamento.analisar(dados_clima(), dados_saude(tuple(sorted(anos))), grupo, int(pop_h),
                            sem_feriados)
except Exception as e:  # noqa: BLE001
    st.error(f"Erro ao preparar os dados: {e}")
    st.stop()

tab, limiar = r["tabela"], r["limiar"]
tipo = saude.GRUPOS[grupo].lower()

# ------------------------------------------------------------ abertura
st.title("Calor e internações: Heliópolis × resto de São Paulo")
st.markdown(
    f"Comparamos a **sensação térmica** de cada dia (Open-Meteo) com as **internações de "
    f"urgência no SUS** ({tipo}) em {', '.join(map(str, sorted(anos)))}. "
    f"**Dia de calor** = sensação térmica máxima de **{f(limiar, 1)} °C ou mais** "
    f"(os {100 - config.PERCENTIL_DIA_CALOR}% dias mais quentes do período), contando também os "
    f"{config.DIAS_DEPOIS} dias seguintes."
    + (f" Feriados, Carnaval e fim de ano ({r['feriados_removidos']} dias) ficam de fora."
       if sem_feriados else ""))

with st.container(border=True):
    st.markdown("#### O que os dados mostram")
    for item in r["conclusoes"]:
        st.markdown(f"**{item['titulo']}** {item['texto']}")

# ------------------------------------- 1. sensação térmica × internações
st.divider()
st.header("1. Quanto maior a sensação térmica, mais internações?")
st.caption("Dias de novembro a março, agrupados pela sensação térmica máxima. Cada barra mostra "
           "quanto as internações ficaram acima (ou abaixo) do normal para aquela época. "
           "Comparar em % permite colocar Heliópolis e a cidade no mesmo gráfico.")

fx = r["faixas"]
fig = go.Figure()
for rec, nome in saude.RECORTES.items():
    d = fx[fx["recorte"] == rec]
    fig.add_bar(
        x=d["faixa"].astype(str), y=d["variacao"], name=nome,
        marker=estilo_barras([COR[rec]] * len(d), d["significativo"]),
        text=[var(v) for v in d["variacao"]], textposition="outside", textfont_size=14,
        cliponaxis=False,
        hovertext=[f"{nome} · {fa}<br>{dias} dias<br>{f(o, 1)} internações/dia "
                   f"(normal {f(n, 1)})<br>faixa provável: {var(lo)} a {var(hi)}"
                   for fa, dias, o, n, lo, hi in zip(d["faixa"], d["dias"], d["obs_dia"],
                                                     d["normal_dia"], d["ic_inf"], d["ic_sup"])],
        hoverinfo="text")
fig.add_hline(y=0, line=dict(color=TINTA, width=1.5), annotation_text="normal",
              annotation_position="bottom right", annotation_font_color=TINTA)
fig.update_yaxes(title="% de internações acima do normal", ticksuffix="%")
fig.update_xaxes(title="sensação térmica máxima do dia")
st.plotly_chart(grafico(fig, 420), width="stretch", config=SEM_BARRA)
dias_faixa = fx.drop_duplicates("faixa")[["faixa", "dias"]]
st.caption("Barra cheia = diferença confiável · barra vazada = diferença pequena demais para "
           "afirmar (pode ser acaso). "
           "Dias em cada faixa: " + " · ".join(f"{a}: {b}" for a, b in dias_faixa.values))

st.markdown("##### Dia a dia: cada ponto é um dia de verão")
lugar = st.radio("Ver", list(saude.RECORTES), format_func=saude.RECORTES.get, horizontal=True,
                 index=1, label_visibility="collapsed")
v = tab[tab["verao"]].dropna(subset=[f"{cruzamento.col(lugar, grupo)}__var"])
y = v[f"{cruzamento.col(lugar, grupo)}__var"]
fig = go.Figure(go.Scatter(
    x=v[cruzamento.VAR], y=y, mode="markers",
    marker=dict(color=COR[lugar], size=7, opacity=.65, line_width=0),
    customdata=np.c_[v["data"].dt.strftime("%d/%m/%Y"), v[cruzamento.col(lugar, grupo)]],
    hovertemplate="%{customdata[0]}<br>sensação %{x:.1f} °C<br>%{customdata[1]} internações "
                  "(%{y:+.0f}% vs. normal)<extra></extra>"))
if len(v) > 2:
    a, b = np.polyfit(v[cruzamento.VAR], y, 1)
    xs = np.linspace(v[cruzamento.VAR].min(), v[cruzamento.VAR].max(), 30)
    fig.add_scatter(x=xs, y=a * xs + b, mode="lines", line=dict(color=TINTA, dash="dash", width=2),
                    hoverinfo="skip")
fig.add_hline(y=0, line=dict(color=CINZA, width=1))
fig.update_xaxes(title="sensação térmica máxima do dia (°C)")
fig.update_yaxes(title="% acima do normal", ticksuffix="%")
c = r["correlacao"].set_index("recorte").loc[lugar]
st.plotly_chart(grafico(fig, 380).update_layout(showlegend=False), width="stretch",
                config=SEM_BARRA)
st.caption(f"Linha tracejada = tendência. Correlação de Spearman: ρ = {f(c['rho'], 2)} "
           f"({'significativa' if c['p_valor'] < .05 else 'não significativa'}, {c['dias']} dias). "
           "ρ vai de −1 a +1; positivo = quanto mais calor, mais internações. Valores perto de "
           "0,1–0,3 são comuns aqui, porque muita coisa além do calor leva alguém ao hospital.")

# ------------------------------------ 2. Heliópolis × resto em dias de calor
st.divider()
st.header("2. Nos dias de calor, Heliópolis tem mais internados que o resto de SP?")
comp = r["comparacao"]
t, dif = comp["tabela"], comp["diferenca"]

a, b = st.columns(2)
with a:
    st.markdown("##### Quanto as internações mudam nos dias de calor")
    st.caption("Cada lugar comparado com o seu próprio normal. Não depende da população. "
               "Barra vazada = pode ser acaso.")
    fig = go.Figure(go.Bar(
        x=t["lugar"], y=t["variacao"],
        marker=estilo_barras([COR[x] for x in t["recorte"]], t["significativo"]),
        text=[var(x) for x in t["variacao"]], textposition="outside", textfont_size=18,
        cliponaxis=False,
        hovertext=[f"{lu}<br>{f(o, 1)} internações/dia nos dias de calor<br>normal: {f(n, 1)}"
                   f"<br>faixa provável: {var(lo)} a {var(hi)}" for lu, o, n, lo, hi in
                   zip(t["lugar"], t["obs_dia"], t["normal_dia"], t["ic_inf"], t["ic_sup"])],
        hoverinfo="text"))
    fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
    fig.update_yaxes(title="% acima do normal", ticksuffix="%")
    st.plotly_chart(grafico(fig, 360).update_layout(showlegend=False), width="stretch",
                    config=SEM_BARRA)
with b:
    st.markdown("##### Internações por 100 mil habitantes, por dia")
    st.caption(f"Cinza = o normal para aqueles mesmos dias; cor = o que aconteceu nos dias de "
               f"calor. Proporcional à população (Heliópolis: {milhar(pop_h)} hab.; resto de SP: "
               f"{milhar(config.POP_SP - pop_h)} hab.).")
    fig = go.Figure()
    fig.add_bar(x=t["lugar"], y=t["taxa_normal"], name="normal para a época",
                marker=dict(color=CINZA, line_width=0),
                text=[f(x, 1) for x in t["taxa_normal"]], textposition="outside",
                textfont_size=15, cliponaxis=False,
                hovertemplate="%{x}<br>normal para esses dias: %{y:.1f} por 100 mil<extra></extra>")
    fig.add_bar(x=t["lugar"], y=t["taxa_calor"], name="dias de calor",
                marker=dict(color=[COR[x] for x in t["recorte"]], line_width=0),
                text=[f(x, 1) for x in t["taxa_calor"]], textposition="outside",
                textfont_size=15, cliponaxis=False,
                hovertemplate="%{x}<br>dias de calor: %{y:.1f} por 100 mil<extra></extra>")
    fig.update_yaxes(title="internações por 100 mil hab. por dia")
    st.plotly_chart(grafico(fig, 360).update_layout(barmode="group"), width="stretch",
                    config=SEM_BARRA)

h = t.set_index("recorte").loc["heliopolis"]
rs = t.set_index("recorte").loc["resto_sp"]
with st.container(border=True):
    if pd.isna(dif["vezes"]):
        st.markdown("Sem dados suficientes para comparar.")
    else:
        hv, rv = h["variacao"], rs["variacao"]
        if not h["significativo"] and not rs["significativo"]:
            leitura = ("Nos dois lugares a mudança foi pequena demais para descartar o acaso: "
                       "**não apareceu efeito do calor** nas internações.")
        elif hv > 0 and rv > 0 and dif["significativo"]:
            leitura = (f"O aumento em Heliópolis foi **cerca de {f(hv / rv, 1)} vezes** o do resto "
                       "da cidade, e o teste estatístico indica que **não é acaso**."
                       if hv > rv else "O aumento em Heliópolis foi **menor** que o do resto da cidade.")
        elif dif["significativo"]:
            leitura = "Os dois lugares reagiram de forma diferente, e o teste indica que não é acaso."
        else:
            leitura = ("A diferença entre os dois lugares **pode ser acaso**: Heliópolis tem poucas "
                       "internações por dia, então são precisos mais anos de dados para ter certeza.")
        st.markdown(f"**Resultado:** nos dias de calor, as internações {mudou(hv)} em Heliópolis "
                    f"e {mudou(rv)} no resto de SP. {leitura}")

st.caption("A taxa por 100 mil mede quem foi mais internado. Ela também é afetada por quanto "
           "cada população usa o SUS: em Heliópolis quase todos dependem do SUS, no resto da "
           "cidade muitos têm plano de saúde. Por isso o gráfico da esquerda, que compara cada "
           "lugar consigo mesmo, é a comparação mais justa do efeito do calor.")

# ---------------------------------------------------------------- dados
st.divider()
with st.expander("Como a comparação é feita e limitações"):
    st.markdown(
        "- **Sensação térmica** (Open-Meteo): combina temperatura, umidade e vento. É a "
        "temperatura que o corpo sente.\n"
        "- **Internações de urgência pagas pelo SUS** (DATASUS/SIH). Ficam de fora cirurgias "
        "marcadas e quem usa só plano de saúde.\n"
        f"- **Heliópolis** = CEP de residência começando com {', '.join(config.CEPS_HELIOPOLIS)}.\n"
        "- **Normal** = média de internações nos dias sem calor daquele mês e ano, ajustada pelo "
        "dia da semana. Assim o inverno e as segundas-feiras não atrapalham.\n"
        "- **Faixa provável** = intervalo de 95%. Se inclui o zero, a diferença pode ser acaso.\n"
        "- O clima é uma estimativa regional; dentro da favela costuma ser mais quente.")
with st.expander("Baixar os dados"):
    cols = ["data", "tmax", "tmin", cruzamento.VAR, "chuva", "dia_calor"] + \
           [x for x in tab.columns if x.count("__") == 1]
    st.download_button("Tabela diária clima × internações (.csv)",
                       tab[cols].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       "calor_internacoes_diario.csv")
    st.dataframe(tab[cols], hide_index=True)
