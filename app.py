"""O calor está mandando mais gente de Heliópolis para o hospital?

Rodar:  streamlit run app.py
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from meteo import clima, config, cruzamento, saude

LARANJA, CINZA, AZUL, CINZA_CLARO = "#eb6834", "#a3a29c", "#2a78d6", "#d9d8d2"

st.set_page_config(page_title="Calor e internações em Heliópolis", page_icon="🌡️",
                   layout="wide")


def f(x, casas=0):
    return f"{x:.{casas}f}".replace(".", ",")


def var(x):
    return "–" if pd.isna(x) else ("+" if x >= 0 else "−") + f(abs(x)) + "%"


def grafico(fig, altura=360):
    fig.update_layout(height=altura, margin=dict(l=8, r=8, t=16, b=8), showlegend=False,
                      separators=",.", bargap=.35, hoverlabel=dict(font_size=14))
    fig.update_xaxes(showgrid=False, tickfont_size=13)
    fig.update_yaxes(tickfont_size=12, gridcolor="rgba(128,128,128,.15)")
    return fig


def barras_variacao(rotulos, df, horizontal=False):
    """Barras de '% acima do normal'. Laranja = aumento confiável; cinza = pode ser acaso."""
    cores = [LARANJA if s and v > 0 else AZUL if s else CINZA_CLARO
             for s, v in zip(df["significativo"], df["variacao"].fillna(0))]
    texto = [var(v) for v in df["variacao"]]
    dica = [f"{d} dias<br>{f(o, 1)} internações/dia (normal: {f(n, 1)})<br>"
            f"faixa provável: {var(lo)} a {var(hi)}"
            for d, o, n, lo, hi in zip(df["dias"], df["obs_dia"], df["normal_dia"],
                                       df["ic_inf"], df["ic_sup"])]
    eixo = dict(x=df["variacao"], y=rotulos, orientation="h") if horizontal else \
        dict(x=rotulos, y=df["variacao"])
    fig = go.Figure(go.Bar(**eixo, marker=dict(color=cores, line_width=0), text=texto,
                           textposition="outside", textfont_size=15, cliponaxis=False,
                           hovertext=dica, hoverinfo="text"))
    linha = dict(color="#52514e", width=1.5)
    if horizontal:
        fig.add_vline(x=0, line=linha)
        fig.update_xaxes(title="% a mais (ou a menos) que num dia normal", ticksuffix="%")
    else:
        fig.add_hline(y=0, line=linha, annotation_text="dia normal",
                      annotation_position="bottom right", annotation_font_color="#52514e")
        fig.update_yaxes(title="% a mais que num dia normal", ticksuffix="%")
    return fig


SEM_BARRA = {"displayModeBar": False}
LEGENDA_CORES = ("🟧 **laranja** = aumento confiável · ⬜ **cinza** = diferença pequena demais "
                 "para afirmar (pode ser acaso). Passe o mouse para ver os números.")


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
    recorte = st.radio("Moradores de", list(saude.RECORTES), format_func=saude.RECORTES.get)
    grupo = st.selectbox("Tipo de internação", list(saude.GRUPOS), format_func=saude.GRUPOS.get)
    padrao = [a for a in anos_ok if a not in config.ANOS_PANDEMIA][-3:]
    anos = st.multiselect("Anos", anos_ok, default=padrao,
                          help="Na primeira vez, cada ano leva alguns minutos para baixar "
                               "(15 arquivos do DATASUS). Depois fica salvo.")
    st.divider()
    st.caption(f"**Heliópolis** = pacientes com CEP começando em "
               f"{', '.join(config.CEPS_HELIOPOLIS)}.  \n"
               f"**Dia de calor** = máxima ≥ {f(config.DIA_MUITO_QUENTE)} °C, "
               f"mais os {config.DIAS_DEPOIS} dias seguintes.  \n"
               "**Clima:** Open-Meteo · **Saúde:** DATASUS/SIH")

if not anos:
    st.info("Escolha pelo menos um ano na barra lateral.")
    st.stop()

# Baixa o que falta mostrando o progresso (a 1ª vez é demorada)
faltando = [m for a in anos for m in saude._meses_do_ano(a)
            if not (config.CACHE / f"internacoes_{m}.parquet").exists()]
if faltando:
    barra = st.progress(0.0, "Baixando internações do DATASUS…")
    for i, m in enumerate(sorted(set(faltando))):
        barra.progress(i / len(set(faltando)), f"Baixando arquivo {i + 1} de {len(set(faltando))} "
                                                 f"(20{m[:2]}/{m[2:]})… cada um leva ~1 min")
        saude.baixar_mes(m)
    barra.empty()

try:
    r = cruzamento.analisar(dados_clima(), dados_saude(tuple(sorted(anos))), recorte, grupo)
except Exception as e:  # noqa: BLE001
    st.error(f"Erro ao preparar os dados: {e}")
    st.stop()

tab, g = r["tabela"], r["geral"]
quem = saude.RECORTES[recorte]
de_quem = {"heliopolis": "de Heliópolis", "resto_sp": "do resto da cidade de SP"}[recorte]
tipo = saude.GRUPOS[grupo].lower()
c = cruzamento.col(recorte, grupo)

# ------------------------------------------------------------ abertura
st.title("O calor está mandando mais gente para o hospital?")
st.markdown(
    f"Contamos as **internações de urgência no SUS** de moradores **{de_quem}** "
    f"({tipo}) em {', '.join(map(str, sorted(anos)))} e comparamos os **dias de calor** "
    f"(máxima de {f(config.DIA_MUITO_QUENTE)} °C ou mais) com **dias normais da mesma época "
    "do ano**.")

k1, k2, k3 = st.columns(3)
k1.metric("Num dia normal", f"{f(g['normal_dia'], 1)} internações", border=True,
          help="O esperado para aquele mês e dia da semana")
k2.metric("Num dia de calor", f"{f(g['obs_dia'], 1)} internações", border=True,
          help=f"Média dos dias com máxima ≥ {f(config.DIA_MUITO_QUENTE)} °C e dos "
               f"{config.DIAS_DEPOIS} dias seguintes")
k3.metric("Diferença", var(g["variacao"]), border=True,
          delta="confiável" if g["significativo"] else "pode ser acaso",
          delta_color="inverse" if g["significativo"] else "off",
          help=f"Faixa provável: {var(g['ic_inf'])} a {var(g['ic_sup'])}")

with st.container(border=True):
    st.markdown("#### O que os dados mostram")
    for item in r["conclusoes"]:
        fim = "" if item["titulo"].endswith("?") else "."
        st.markdown(f"**{item['titulo']}{fim}** {item['texto']}")

# ------------------------------------------------- 1. faixas de temperatura
st.divider()
st.subheader("1. Quanto mais quente o dia, mais internações?")
st.caption("Só dias de novembro a março, agrupados pela temperatura máxima. Cada barra mostra "
           "quanto as internações ficaram acima (ou abaixo) de um dia normal.")
fx = r["faixas"]
st.plotly_chart(grafico(barras_variacao(fx["faixa"] + "<br><sub>" + fx["dias"].astype(str)
                                        + " dias</sub>", fx)), width="stretch", config=SEM_BARRA)
st.caption(LEGENDA_CORES)

# ------------------------------------------------------------- 2. grupos
st.divider()
st.subheader("2. Que tipo de problema mais aumenta nos dias de calor?")
st.caption(f"Moradores {de_quem}. Variação nos dias de calor em relação ao normal.")
gr = r["grupos"].sort_values("variacao")
st.plotly_chart(grafico(barras_variacao(gr["nome"], gr, horizontal=True), 320),
                width="stretch", config=SEM_BARRA)
st.caption("Rins, desidratação e insolação são os efeitos mais diretos do calor no corpo. "
           + LEGENDA_CORES)

# ------------------------------------------------- 3. Heliópolis × cidade
st.divider()
st.subheader("3. Heliópolis sofre mais com o calor que o resto da cidade?")
st.caption(f"{saude.GRUPOS[grupo]}: variação nos dias de calor em cada lugar.")
cid = r["cidade"]
fig = barras_variacao(cid["nome"], cid)
st.plotly_chart(grafico(fig, 320), width="stretch", config=SEM_BARRA)
n_h = tab[cruzamento.col("heliopolis", grupo)].mean()
st.caption(f"Heliópolis tem em média {f(n_h, 1)} internações deste tipo por dia; a cidade, "
           "milhares. Com poucos casos, a incerteza de Heliópolis é maior. " + LEGENDA_CORES)

# ------------------------------------------------------- 4. dias depois
st.divider()
st.subheader("4. Quanto tempo o efeito do calor dura?")
st.caption(f"Começando no dia de máxima ≥ {f(config.DIA_MUITO_QUENTE)} °C, como ficam as "
           "internações nos dias seguintes.")
dd = r["depois"]
rot = ["no dia"] + [f"{d} dia{'s' if d > 1 else ''}<br>depois" for d in dd["dias_depois"][1:]]
st.plotly_chart(grafico(barras_variacao(rot, dd)), width="stretch", config=SEM_BARRA)
st.caption("Se as barras ficam abaixo de zero depois do pico, parte das internações foi apenas "
           "antecipada pelo calor. " + LEGENDA_CORES)

# ------------------------------------------------------- 5. ondas de calor
st.divider()
st.subheader("5. O que aconteceu em cada onda de calor")
ondas = r["ondas"]
if ondas.empty:
    st.info("Nenhuma onda de calor nos anos escolhidos.")
else:
    st.caption(f"Onda de calor = {config.ONDA_DIAS} ou mais dias seguidos com máxima acima do "
               "normal para o mês (os 10% mais quentes de 1991–2020).")
    meses_pt = "jan fev mar abr mai jun jul ago set out nov dez".split()
    nomes = [f"{w.inicio.day} {meses_pt[w.inicio.month - 1]}/{w.inicio.year} · {w.dias} dias · "
             f"pico de {f(w.tmax_pico, 1)} °C"
             for w in ondas.itertuples()]
    escolha = st.selectbox("Escolha uma onda (começa pela mais quente)", nomes,
                           index=int(ondas["tmax_pico"].idxmax()))
    w = ondas.iloc[nomes.index(escolha)]
    jan = tab[(tab["data"] >= w["inicio"] - pd.Timedelta(days=7)) &
              (tab["data"] <= w["fim"] + pd.Timedelta(days=7))]
    na_onda = jan["data"].between(w["inicio"], w["fim"])

    a, b = st.columns(2)
    with a:
        st.markdown("**Temperatura máxima de cada dia**")
        fig = go.Figure(go.Bar(x=jan["data"], y=jan["tmax"],
                               marker=dict(color=[LARANJA if x else CINZA_CLARO for x in na_onda],
                                           line_width=0),
                               text=[f(x, 0) for x in jan["tmax"]], textposition="outside",
                               hovertemplate="%{x|%d/%m}: %{y:.1f} °C<extra></extra>"))
        fig.update_yaxes(title="°C", range=[jan["tmax"].min() - 4, jan["tmax"].max() + 3])
        st.plotly_chart(grafico(fig, 300).update_xaxes(tickformat="%d/%m"), width="stretch", config=SEM_BARRA)
    with b:
        st.markdown(f"**Internações por dia ({quem})**")
        fig = go.Figure()
        fig.add_bar(x=jan["data"], y=jan[c], marker=dict(color=AZUL, line_width=0),
                    hovertemplate="%{x|%d/%m}: %{y} internações<extra></extra>")
        fig.add_scatter(x=jan["data"], y=jan[f"{c}__normal"], mode="lines",
                        line=dict(color="#52514e", dash="dash", width=2),
                        hovertemplate="normal: %{y:.1f}<extra></extra>")
        fig.add_vrect(x0=w["inicio"] - pd.Timedelta(hours=12), x1=w["fim"] + pd.Timedelta(hours=12),
                      fillcolor=LARANJA, opacity=.12, line_width=0,
                      annotation_text="onda de calor", annotation_position="top left")
        fig.update_yaxes(title="internações")
        st.plotly_chart(grafico(fig, 300).update_xaxes(tickformat="%d/%m"), width="stretch", config=SEM_BARRA)
    st.caption("Barras laranja = dias da onda. A linha tracejada é o número normal de internações "
               "para aquele dia. Barras azuis acima da linha = mais internações que o normal.")

    with st.expander("Todas as ondas de calor"):
        st.dataframe(ondas, hide_index=True, column_config={
            "inicio": st.column_config.DateColumn("início", format="DD/MM/YYYY"),
            "fim": st.column_config.DateColumn("fim", format="DD/MM/YYYY"),
            "tmax_pico": st.column_config.NumberColumn("máxima no pico (°C)", format="%.1f"),
            "a_mais": st.column_config.NumberColumn("internações a mais", format="%.0f"),
            "variacao": st.column_config.NumberColumn("variação (%)", format="%+.0f%%")})

# ---------------------------------------------------------------- dados
st.divider()
with st.expander("Como a comparação é feita e limitações"):
    st.markdown(
        "- **Internações de urgência pagas pelo SUS** (DATASUS/SIH). Ficam de fora cirurgias "
        "marcadas e quem usa só plano de saúde.\n"
        f"- **Heliópolis** = pacientes cujo CEP de residência começa com "
        f"{', '.join(config.CEPS_HELIOPOLIS)}. Alguns desses CEPs incluem ruas vizinhas.\n"
        "- **Dia normal** = média de internações por dia naquele mês e ano, ajustada pelo dia da "
        "semana. Assim o inverno (mais doenças respiratórias) não atrapalha a comparação.\n"
        "- **Clima** = Open-Meteo, estimativa para a região. Dentro da favela costuma ser mais "
        "quente, então o efeito real pode ser maior.\n"
        "- **Laranja/cinza:** usamos um intervalo de 95%. Se ele inclui o zero, a diferença pode "
        "ser acaso e a barra fica cinza.")
with st.expander("Baixar os dados"):
    cols = ["data", "tmax", "tmin", "chuva"] + [x for x in tab.columns if "__" in x and
                                                 not x.endswith("__normal")]
    st.download_button("Tabela diária clima × internações (.csv)",
                       tab[cols].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       "calor_internacoes_diario.csv")
    st.dataframe(tab[cols], hide_index=True)
