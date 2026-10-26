"""Calor e saúde em Heliópolis — painel interativo.

Rodar:  streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from meteo import censo, clima, config, cruzamento, estacoes, poluicao, saude

# Cor = identidade do lugar (a mesma em todos os gráficos)
COR = {"heliopolis": "#eb6834", "regiao": "#1baf7a", "cidade": "#2a78d6"}
CINZA, TINTA = "#a3a29c", "#52514e"
# Sem botão de baixar imagem
CONFIG_GRAFICO = {"displaylogo": False, "modeBarButtonsToRemove": ["toImage"]}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
CORES_ESTACAO = ["#6250d6", "#e87ba4", "#008300", "#eda100", "#e34948", "#1baf7a"]
CORES_RISCO = {"Sem alerta": "#d6d5cf", "Atenção": "#f5c46b", "Cautela extrema": "#eb6834",
               "Perigo": "#c4322f", "Perigo extremo": "#7a1b1a"}
CORES_POLUENTE = {"pm10": "#6250d6", "pm2_5": "#e87ba4", "ozone": "#008300",
                  "nitrogen_dioxide": "#eda100"}
NOME_POLUENTE = {"pm10": "MP10", "pm2_5": "MP2,5", "ozone": "Ozônio",
                 "nitrogen_dioxide": "NO₂"}

st.set_page_config(page_title="Calor e saúde em Heliópolis", page_icon="🌡️", layout="wide")


# ---------------------------------------------------------------- formatação
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
                      legend=dict(orientation="h", y=1.1, x=0, font_size=14, title=None))
    fig.update_xaxes(showgrid=False, tickfont_size=13)
    fig.update_yaxes(tickfont_size=12, gridcolor="rgba(128,128,128,.15)", zeroline=False)
    return fig


def mostrar(fig, altura=380, legenda=True):
    st.plotly_chart(grafico(fig, altura).update_layout(showlegend=legenda), width="stretch",
                    config=CONFIG_GRAFICO)


def correlacoes(tabela, nomes):
    """Mapa de correlação de Pearson entre as colunas da tabela."""
    c = tabela.corr().round(2)
    rot = [nomes.get(x, x) for x in c.columns]
    fig = go.Figure(go.Heatmap(z=c.values, x=rot, y=rot, zmin=-1, zmax=1, colorscale="RdBu_r",
                               text=[[f(v, 2) for v in linha] for linha in c.values],
                               texttemplate="%{text}", textfont_size=13, xgap=2, ygap=2,
                               colorbar=dict(thickness=12),
                               hovertemplate="%{x} × %{y}: %{z:.2f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    return fig


# ------------------------------------------------------------------ dados
@st.cache_data(show_spinner="Baixando o clima (Open-Meteo)…", ttl="12h")
def dados_clima():
    return clima.carregar()


@st.cache_data(show_spinner="Baixando as medições horárias do INMET…")
def dados_horarios():
    return estacoes.carregar()


@st.cache_data(show_spinner="Baixando o Censo 2022 (IBGE)…")
def dados_censo():
    return censo.baixar_censo()


@st.cache_data(show_spinner="Baixando a poluição…")
def dados_poluicao(inicio, fim):
    return poluicao.diaria(inicio, fim)


@st.cache_data(show_spinner="Consultando o DATASUS…", ttl="24h")
def meses_saude():
    return saude.meses_disponiveis()


@st.cache_data(show_spinner="Contando as internações…")
def dados_saude(anos: tuple):
    return saude.carregar(list(anos))


try:
    cl = dados_clima()
except Exception as e:  # noqa: BLE001
    st.error(f"Não foi possível obter o clima da Open-Meteo: {e}")
    st.stop()
lim = clima.limiares(cl)

try:
    hor, rel_h = dados_horarios()
    erro_horario = None
except Exception as e:  # noqa: BLE001
    hor = rel_h = None
    erro_horario = str(e)

try:
    anos_ok = saude.anos_completos(meses_saude())
    erro_saude = None if anos_ok else "nenhum ano completo disponível"
except Exception as e:  # noqa: BLE001
    anos_ok, erro_saude = [], str(e)

# ------------------------------------------------------------------ filtros
with st.sidebar:
    st.header("Escolhas")
    criterio = st.radio(
        "O que conta como calor", list(config.CRITERIOS),
        format_func=lambda c: config.CRITERIOS[c]["nome"],
        help="**Dia quente**: sensação térmica máxima entre os 10% mais altos dos verões de "
             "1991–2020. **Noite quente**: temperatura mínima entre as 10% mais altas (o corpo "
             f"não descansa à noite). **Onda de calor**: {config.DIAS_ONDA} ou mais dias quentes "
             "seguidos.")
    grupo = st.selectbox("Tipo de internação", list(saude.GRUPOS), format_func=saude.GRUPOS.get)
    padrao = [a for a in anos_ok if a not in config.ANOS_PANDEMIA][-2:]
    anos = st.multiselect("Anos (internações)", anos_ok, default=padrao,
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
    if hor is not None:
        st.divider()
        ini, fim = hor["timestamp"].min().date(), hor["timestamp"].max().date()
        periodo = st.date_input("Período (estresse térmico)", (ini, fim), min_value=ini,
                                max_value=fim, format="DD/MM/YYYY")
        locais = sorted(hor["zona"].unique())
        zonas = st.multiselect("Local de medição", locais, default=locais)
    st.divider()
    st.caption(f"**Heliópolis** = CEP começando com {', '.join(config.CEPS_HELIOPOLIS)}.  \n"
               f"**Região do Ipiranga** = CEP começando com {', '.join(config.CEPS_REGIAO)} "
               "(inclui Heliópolis).  \n"
               "**Clima:** Open-Meteo e INMET · **Saúde:** DATASUS/SIH (internações de urgência "
               "no SUS) · **População:** IBGE, Censo 2022")

crit = config.CRITERIOS[criterio]
limiar = lim[crit["var"]]

# ---------------------------------------------------- download das internações
r = None
if anos and not erro_saude:
    faltando = sorted({m for a in anos for m in saude._meses_do_ano(a)
                       if not (config.CACHE / f"internacoes_{m}.parquet").exists()})
    if faltando:
        barra = st.progress(0.0)
        for i, m in enumerate(faltando):
            barra.progress(i / len(faltando), f"Baixando internações do DATASUS: arquivo "
                                              f"{i + 1} de {len(faltando)} (20{m[:2]}/{m[2:]}) "
                                              "· ~1 min cada")
            saude.baixar_mes(m)
        barra.empty()
    try:
        internacoes = dados_saude(tuple(sorted(anos)))
        r = cruzamento.analisar(cl, internacoes, grupo, criterio, int(pop_h), sem_feriados,
                                limiares=lim)
    except Exception as e:  # noqa: BLE001
        st.error(f"Erro ao preparar os dados de saúde: {e}")

# ------------------------------------------------------------------ abertura
st.title("Calor e saúde em Heliópolis")
st.markdown(
    f"Este painel cruza o **clima** de Heliópolis desde 1991 (Open-Meteo) com as **internações "
    f"de urgência no SUS** (DATASUS), mede o **estresse térmico** hora a hora (INMET) e mostra "
    f"**quem mora** lá (Censo 2022). **{crit['nome']}** = "
    f"**{cruzamento.descricao(criterio, limiar)}**. O limiar é o valor que só os 10% mais quentes "
    f"dos verões de {config.CLIMATOLOGIA[0]}–{config.CLIMATOLOGIA[1]} alcançavam. Como Heliópolis "
    "tem poucas "
    "internações por dia, mostramos também a **região do Ipiranga**, que inclui Heliópolis e vive "
    "o mesmo clima, e a **cidade** como referência.")

if erro_saude:
    st.warning(f"Os dados do DATASUS não estão disponíveis agora ({erro_saude}). "
               "As outras abas continuam funcionando.")
elif not anos:
    st.info("Escolha pelo menos um ano na barra lateral para ver as internações.")
elif r is not None:
    with st.container(border=True):
        st.markdown("#### O que os dados mostram")
        for item in r["conclusoes"]:
            st.markdown(f"**{item['titulo']}** {item['texto']}")

aba_clima, aba_saude, aba_estresse, aba_pop = st.tabs(
    ["🌡️ O calor está aumentando?", "🏥 Calor × internações", "📡 Estresse térmico",
     "👥 População exposta"])

# ============================================================ 1. clima
with aba_clima:
    anual = clima.resumo_anual(cl)
    tend = clima.tendencia(anual, criterio)
    dec = clima.por_decada(anual, criterio)

    a, b, c = st.columns(3)
    if len(dec) >= 2:
        a.metric(f"{crit['plural']} por ano · {dec['rotulo'].iloc[0]}", f(dec["mean"].iloc[0]))
        b.metric(f"{crit['plural']} por ano · {dec['rotulo'].iloc[-1]}", f(dec["mean"].iloc[-1]),
                 delta=f"{f(dec['mean'].iloc[-1] - dec['mean'].iloc[0])} dias",
                 delta_color="inverse")
    c.metric("Tendência (dias a mais por década)",
             "–" if pd.isna(tend["por_decada"])
             else f"{'+' if tend['por_decada'] > 0 else ''}{f(tend['por_decada'], 1)}")

    st.markdown(f"##### {crit['plural']} por ano")
    st.caption(f"Cada barra conta os dias do ano com {cruzamento.descricao(criterio, limiar)}. "
               "A linha tracejada é a tendência. O ano atual (barra vazada) ainda não terminou.")
    fig = go.Figure()
    fig.add_bar(x=anual["ano"], y=anual[criterio], name="dias de calor",
                marker=estilo_barras([COR["heliopolis"]] * len(anual), anual["completo"]),
                hovertemplate="%{x}: %{y} dias<extra></extra>")
    if len(tend["x"]):
        fig.add_scatter(x=tend["x"], y=tend["y"], mode="lines", name="tendência",
                        line=dict(color=TINTA, dash="dash", width=2), hoverinfo="skip")
    fig.update_yaxes(title="dias no ano")
    mostrar(fig, 360, legenda=False)

    st.markdown("##### Em que meses o calor aparece")
    st.caption(f"Número de dias de calor em cada mês. Quanto mais escuro, mais dias. Mostra se o "
               "calor está chegando mais cedo, indo até mais tarde ou ficando mais forte no "
               "auge do verão.")
    mapa = clima.mapa_ano_mes(cl, criterio)
    fig = go.Figure(go.Heatmap(
        z=mapa.values, x=MESES, y=mapa.index, colorscale="Oranges", xgap=2, ygap=2,
        colorbar=dict(title="dias", thickness=12),
        hovertemplate="%{x}/%{y}: %{z} dias<extra></extra>"))
    fig.update_yaxes(autorange="reversed", dtick=5)
    st.plotly_chart(grafico(fig, 620), width="stretch", config=CONFIG_GRAFICO)
    st.caption("Fonte: Open-Meteo (reanálise ERA5) para o ponto central de Heliópolis. É uma "
               "estimativa para uma área de vários km²; dentro da favela, com casas coladas, laje e "
               "pouca árvore, o calor costuma ser maior.")

# ============================================================ 2. saúde
with aba_saude:
    if r is None:
        st.info("Sem dados de internações para os filtros escolhidos.")
    else:
        tab, tipo, vcl = r["tabela"], saude.GRUPOS[grupo].lower(), r["var"]
        nome_var = cruzamento.TEXTO_VAR[vcl]

        # ---- 2.1 por faixa
        st.header("Quanto mais quente, mais internações?")
        st.caption(f"Dias de novembro a março, agrupados pela {nome_var}. Cada barra mostra quanto "
                   f"as internações ({tipo}) ficaram acima (ou abaixo) do normal para aquela época. "
                   "Em % dá para pôr lugares de tamanhos diferentes no mesmo gráfico.")
        fx = r["faixas"]
        fig = go.Figure()
        for rec, nome in saude.RECORTES.items():
            d = fx[fx["recorte"] == rec]
            fig.add_bar(
                x=d["faixa"].astype(str), y=d["variacao"], name=nome,
                marker=estilo_barras([COR[rec]] * len(d), d["significativo"]),
                text=[var(v) for v in d["variacao"]], textposition="outside", textfont_size=13,
                cliponaxis=False,
                hovertext=[f"{nome} · {fa}<br>{dias} dias<br>{f(o, 1)} internações/dia "
                           f"(normal {f(n, 1)})<br>faixa provável: {var(lo)} a {var(hi)}"
                           for fa, dias, o, n, lo, hi in zip(d["faixa"], d["dias"], d["obs_dia"],
                                                             d["normal_dia"], d["ic_inf"],
                                                             d["ic_sup"])],
                hoverinfo="text")
        fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
        fig.update_traces(selector=dict(type="bar"), showlegend=False)
        for rec, nome in saude.RECORTES.items():   # legenda sempre com a cor cheia
            fig.add_scatter(x=[None], y=[None], name=nome, mode="markers",
                            marker=dict(symbol="square", size=13, color=COR[rec]))
        fig.update_yaxes(title="% acima do normal", ticksuffix="%")
        fig.update_xaxes(title=nome_var)
        mostrar(fig, 420)
        dias_faixa = fx.drop_duplicates("faixa")[["faixa", "dias"]]
        st.caption("Barra cheia = diferença confiável · barra vazada = pode ser acaso. "
                   "Dias em cada faixa: " + " · ".join(f"{a}: {b}" for a, b in dias_faixa.values))

        st.markdown("##### Dia a dia: cada ponto é um dia de verão")
        lugar = st.radio("Ver", list(saude.RECORTES), format_func=saude.RECORTES.get,
                         horizontal=True, index=1, label_visibility="collapsed")
        cv = f"{cruzamento.col(lugar, grupo)}__var"
        v = tab[tab["verao"]].dropna(subset=[cv])
        fig = go.Figure(go.Scatter(
            x=v[vcl], y=v[cv], mode="markers",
            marker=dict(color=COR[lugar], size=8, opacity=.6, line_width=0),
            customdata=np.c_[v["data"].dt.strftime("%d/%m/%Y"), v[cruzamento.col(lugar, grupo)]],
            hovertemplate="%{customdata[0]}<br>%{x:.1f} °C<br>%{customdata[1]} internações "
                          "(%{y:+.0f}% vs. normal)<extra></extra>"))
        if len(v) > 2:
            a_, b_ = np.polyfit(v[vcl], v[cv], 1)
            xs = np.linspace(v[vcl].min(), v[vcl].max(), 30)
            fig.add_scatter(x=xs, y=a_ * xs + b_, mode="lines",
                            line=dict(color=TINTA, dash="dash", width=2), hoverinfo="skip")
        fig.add_hline(y=0, line=dict(color=CINZA, width=1))
        fig.update_xaxes(title=f"{nome_var} do dia (°C)")
        fig.update_yaxes(title="% acima do normal", ticksuffix="%")
        mostrar(fig, 380, legenda=False)
        c = r["correlacao"].set_index("recorte").loc[lugar]
        st.caption(f"Linha tracejada = tendência. Correlação de Spearman: ρ = {f(c['rho'], 2)} "
                   f"({'significativa' if c['p_valor'] < .05 else 'não significativa'}, "
                   f"{c['dias']} dias). ρ vai de −1 a +1; positivo = quanto mais calor, mais "
                   "internações. Valores de 0,1 a 0,3 já são comuns aqui, porque muita coisa além "
                   "do calor leva alguém ao hospital. Em Heliópolis os pontos espalham muito porque "
                   "há poucos casos por dia.")

        # ---- 2.2 defasagem
        st.divider()
        st.header("Quando o efeito aparece?")
        st.caption(f"Internações ({tipo}) no dia de calor (0) e nos dias seguintes, comparadas ao "
                   "normal. Mostra por quantos dias o calor continua pesando e, portanto, por quanto "
                   "tempo vale manter o alerta. Ponto cheio = confiável; ponto vazado = pode ser "
                   "acaso.")
        lg = r["defasagem"]
        fig = go.Figure()
        for rec, nome in saude.RECORTES.items():
            d = lg[lg["recorte"] == rec]
            fig.add_scatter(
                x=d["dias_depois"], y=d["variacao"], name=nome, mode="lines+markers",
                line=dict(color=COR[rec], width=2),
                marker=dict(size=10, color=[COR[rec] if s else "white" for s in d["significativo"]],
                            line=dict(color=COR[rec], width=2)),
                customdata=np.c_[d["ic_inf"], d["ic_sup"]],
                hovertemplate=f"{nome}<br>%{{x}} dia(s) depois: %{{y:+.0f}}%<br>faixa provável: "
                              "%{customdata[0]:+.0f}% a %{customdata[1]:+.0f}%<extra></extra>")
        fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
        fig.update_xaxes(title="dias depois do dia de calor", dtick=1)
        fig.update_yaxes(title="% acima do normal", ticksuffix="%")
        mostrar(fig, 380)

        # ---- 2.3 comparação
        st.divider()
        st.header("Nos dias de calor, Heliópolis sofre mais?")
        comp = r["comparacao"]
        t = comp["tabela"]
        a, b = st.columns(2)
        with a:
            st.markdown("##### Quanto as internações mudam nos dias de calor")
            st.caption(f"Dias de calor e os {config.DIAS_DEPOIS} seguintes. Cada lugar é comparado "
                       "com o seu próprio normal, então o tamanho da população não importa. "
                       "Barra vazada = pode ser acaso.")
            fig = go.Figure(go.Bar(
                x=t["lugar"], y=t["variacao"],
                marker=estilo_barras([COR[x] for x in t["recorte"]], t["significativo"]),
                text=[var(x) for x in t["variacao"]], textposition="inside",
                insidetextanchor="start", textfont=dict(
                    size=17, color=["white" if s_ else TINTA for s_ in t["significativo"]]),
                error_y=dict(type="data", symmetric=False, color=CINZA, thickness=1.5, width=6,
                             array=t["ic_sup"] - t["variacao"],
                             arrayminus=t["variacao"] - t["ic_inf"]),
                hovertext=[f"{lu}<br>{f(o, 1)} internações/dia nos dias de calor<br>normal: "
                           f"{f(n, 1)}<br>faixa provável: {var(lo)} a {var(hi)}"
                           for lu, o, n, lo, hi in zip(t["lugar"], t["obs_dia"], t["normal_dia"],
                                                       t["ic_inf"], t["ic_sup"])],
                hoverinfo="text"))
            fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
            fig.update_yaxes(title="% acima do normal", ticksuffix="%")
            mostrar(fig, 380, legenda=False)
            st.caption("O traço cinza em cada barra é a faixa provável (intervalo de 95%). "
                       "Em Heliópolis ela é larga porque há poucos casos.")
        with b:
            st.markdown("##### Internações por 100 mil habitantes, por dia")
            tx = t.dropna(subset=["taxa_normal"])
            st.caption(f"Cinza = o normal para aqueles mesmos dias; cor = o que aconteceu nos dias "
                       f"de calor. Heliópolis: {milhar(pop_h)} hab.; cidade: "
                       f"{milhar(config.POP_SP)} hab. A região não aparece porque a população "
                       "exata dos CEPs não é publicada.")
            fig = go.Figure()
            fig.add_bar(x=tx["lugar"], y=tx["taxa_normal"], name="normal para a época",
                        marker=dict(color=CINZA, line_width=0),
                        text=[f(x, 1) for x in tx["taxa_normal"]], textposition="outside",
                        textfont_size=15, cliponaxis=False,
                        hovertemplate="%{x}<br>normal: %{y:.1f} por 100 mil<extra></extra>")
            fig.add_bar(x=tx["lugar"], y=tx["taxa_calor"], name="dias de calor",
                        marker=dict(color=[COR[x] for x in tx["recorte"]], line_width=0),
                        text=[f(x, 1) for x in tx["taxa_calor"]], textposition="outside",
                        textfont_size=15, cliponaxis=False,
                        hovertemplate="%{x}<br>dias de calor: %{y:.1f} por 100 mil<extra></extra>")
            fig.update_yaxes(title="internações por 100 mil hab. por dia")
            mostrar(fig.update_layout(barmode="group"), 380)

        ts = t.set_index("recorte")
        h, rg, ci = ts.loc["heliopolis"], ts.loc["regiao"], ts.loc["cidade"]
        with st.container(border=True):
            if pd.isna(ci["variacao"]):
                st.markdown("Sem dados suficientes para comparar.")
            else:
                if h["significativo"]:
                    leitura = "Em Heliópolis o aumento já é grande o bastante para **não ser acaso**."
                elif rg["significativo"]:
                    leitura = ("Heliópolis sozinha tem poucos casos para afirmar, mas **na região do "
                               "Ipiranga a mudança não é acaso**. Como a região inclui Heliópolis e "
                               "vive o mesmo clima, é o melhor indício do que acontece lá.")
                else:
                    leitura = ("Nem em Heliópolis nem na região a mudança foi grande o bastante para "
                               "descartar o acaso.")
                dr = comp["diferenca"]["regiao"]
                if dr["significativo"]:
                    leitura += (f" A região reagiu **{f(dr['vezes'], 2)} vezes** o que a cidade "
                                "reagiu, e a diferença não é acaso.")
                st.markdown(f"**Resultado:** nos dias de calor as internações {mudou(h['variacao'])} "
                            f"em Heliópolis, {mudou(rg['variacao'])} na região do Ipiranga e "
                            f"{mudou(ci['variacao'])} na cidade. {leitura}")
        st.caption("A taxa por 100 mil também depende de quanto cada população usa o SUS: em "
                   "Heliópolis quase todos dependem do SUS, na cidade muitos têm plano de saúde. Por "
                   "isso a comparação de cada lugar consigo mesmo (gráfico da esquerda) é a mais "
                   "justa para medir o efeito do calor.")

# ============================================================ 3. estresse térmico
with aba_estresse:
    st.header("Quanto calor o corpo sente, hora a hora?")
    if erro_horario:
        st.error(f"Não foi possível baixar as medições do INMET: {erro_horario}")
    elif len(periodo) != 2:
        st.info("Escolha a data inicial e a final na barra lateral.")
    elif (df_h := hor[hor["zona"].isin(zonas)
                      & hor["timestamp"].dt.date.between(*periodo)]).empty:
        st.info("Nenhuma medição para o período e os locais escolhidos.")
    else:
        cor_de = {z: CORES_ESTACAO[i % len(CORES_ESTACAO)] for i, z in enumerate(locais)}
        n_locais = df_h["zona"].nunique()
        dia_h = (df_h.set_index("timestamp").groupby("zona")[["indice_calor", "wbgt"]]
                 .resample("D").max().reset_index())
        dias_max = dia_h.groupby("timestamp")["indice_calor"].max()

        a, b, c, d = st.columns(4)
        a.metric("Índice de calor máximo", f"{f(df_h['indice_calor'].max(), 1)} °C")
        b.metric("WBGT máximo", f"{f(df_h['wbgt'].max(), 1)} °C")
        c.metric("Dias com alerta (≥ 27 °C)", f"{(dias_max >= 27).sum()} de {len(dias_max)}")
        d.metric("Horas em cautela extrema ou pior",
                 milhar(df_h["risco"].isin(["Cautela extrema", "Perigo", "Perigo extremo"]).sum()
                        / n_locais))
        st.caption(f"Limpeza automática (meteo/limpeza.py): {milhar(rel_h['linhas_limpas'])} "
                   f"leituras válidas, {milhar(rel_h['outliers_removidos'])} valores impossíveis "
                   f"removidos, {milhar(df_h['preenchido_modelo'].sum())} horas sem medição "
                   "preenchidas pela Open-Meteo.")

        # ---- 3.1 índice de calor diário
        st.markdown("##### Índice de calor máximo do dia, por estação")
        st.caption("O índice de calor junta temperatura e umidade (NOAA). Faixas: 27–32 °C "
                   "atenção · 32–41 °C cautela extrema · 41–54 °C perigo.")
        fig = go.Figure()
        for z, g in dia_h.groupby("zona"):
            fig.add_scatter(x=g["timestamp"], y=g["indice_calor"], name=z, mode="lines",
                            line=dict(width=2, color=cor_de[z]),
                            hovertemplate=f"{z}<br>%{{x|%d/%m}}: %{{y:.1f}} °C<extra></extra>")
        om = cl[cl["data"].between(pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1]))]
        fig.add_scatter(x=om["data"], y=om["sensacao_max"], name="Open-Meteo (sensação máx.)",
                        mode="lines", line=dict(color=CINZA, dash="dash", width=2))
        for y0, y1, cor in [(27, 32, "rgba(237,161,0,.08)"), (32, 41, "rgba(235,104,52,.10)"),
                            (41, 54, "rgba(227,73,72,.12)")]:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=cor, line_width=0)
        fig.update_yaxes(title="°C")
        mostrar(fig, 380)

        # ---- 3.2 horas em risco e perfil do dia
        st.divider()
        a, b = st.columns(2)
        with a:
            st.markdown("##### Horas por dia em cada faixa de risco")
            n_dias = df_h.groupby("zona")["timestamp"].apply(lambda s: s.dt.date.nunique())
            hr = (df_h.groupby(["zona", "risco"], observed=False).size()
                  .div(n_dias, level="zona").rename("horas_dia").reset_index())
            ordem = (hr[hr["risco"] != "Sem alerta"].groupby("zona")["horas_dia"].sum()
                     .sort_values().index.tolist())
            fig = go.Figure()
            for faixa_r in CORES_RISCO:
                g = hr[hr["risco"] == faixa_r].set_index("zona").reindex(ordem)
                fig.add_bar(y=ordem, x=g["horas_dia"], name=faixa_r, orientation="h",
                            marker=dict(color=CORES_RISCO[faixa_r], line=dict(color="white",
                                                                               width=1)),
                            hovertemplate=f"%{{y}}<br>{faixa_r}: %{{x:.1f}} h/dia<extra></extra>")
            fig.update_layout(barmode="stack", bargap=.35)
            fig.update_xaxes(title="horas por dia (média)", range=[0, 24], dtick=6)
            st.plotly_chart(grafico(fig, 400).update_layout(
                legend=dict(y=-0.28, yanchor="top", traceorder="normal"),
                margin=dict(b=90)), width="stretch", config=CONFIG_GRAFICO)
            st.caption("Pelo índice de calor de cada hora. Estações mais acima passam mais "
                       "horas em risco.")
        with b:
            st.markdown("##### A noite esfria?")
            pf = (df_h.groupby(["zona", df_h["timestamp"].dt.hour.rename("hora")])
                  [["temperatura", "indice_calor"]].mean().reset_index())
            fig = go.Figure()
            for z, g in pf.groupby("zona"):
                fig.add_scatter(x=g["hora"], y=g["indice_calor"], name=z, mode="lines",
                                line=dict(width=2, color=cor_de[z]),
                                hovertemplate=f"{z}<br>%{{x}}h: %{{y:.1f}} °C<extra></extra>")
            fig.add_vrect(x0=0, x1=6, fillcolor="rgba(98,80,214,.07)", line_width=0,
                          annotation_text="madrugada", annotation_position="bottom left")
            fig.update_xaxes(title="hora do dia", dtick=3, range=[0, 23])
            fig.update_yaxes(title="índice de calor médio (°C)")
            st.plotly_chart(grafico(fig, 400).update_layout(
                legend=dict(y=-0.28, yanchor="top"), margin=dict(b=90)),
                width="stretch", config=CONFIG_GRAFICO)
            st.caption("Média de cada hora. Se a madrugada continua quente, o corpo não se "
                       "recupera do calor do dia, e isso pesa mais para idosos e crianças.")

        # ---- 3.3 distribuição e correlações
        st.divider()
        a, b = st.columns(2)
        with a:
            st.markdown("##### Como o índice de calor se distribui")
            fig = go.Figure()
            for z, g in df_h.groupby("zona"):
                fig.add_box(y=g["indice_calor"], name=z, marker_color=cor_de[z],
                            boxpoints=False, line_width=2)
            fig.update_yaxes(title="índice de calor (°C)")
            mostrar(fig, 380, legenda=False)
            st.caption("A caixa vai do 1º ao 3º quartil; a linha do meio é a mediana.")
        with b:
            st.markdown("##### O que anda junto")
            nomes = {"temperatura": "temperatura", "umidade": "umidade",
                     "indice_calor": "índice de calor", "wbgt": "WBGT"}
            mostrar(correlacoes(df_h[list(nomes)], nomes), 380, legenda=False)
            st.caption("Correlação de Pearson, de −1 a +1. Perto de +1 = sobem juntos.")

        # ---- 3.4 poluição
        st.divider()
        st.markdown("##### Poluição no mesmo período")
        try:
            pol, fonte_pol = dados_poluicao(str(periodo[0]), str(periodo[1]))
        except Exception:  # noqa: BLE001
            pol = None
        if pol is None:
            st.info("Não foi possível baixar a poluição agora.")
        else:
            a, b = st.columns([3, 2])
            with a:
                fig = go.Figure()
                for p in pol.columns:
                    fig.add_scatter(x=pol.index, y=pol[p], name=NOME_POLUENTE.get(p, p),
                                    mode="lines", line=dict(width=2, color=CORES_POLUENTE.get(p)))
                fig.update_yaxes(title="µg/m³ (média do dia)")
                mostrar(fig, 380)
            with b:
                calor_dia = df_h.set_index("timestamp")["indice_calor"].resample("D").mean()
                junto = pol.join(calor_dia.rename("indice_calor"))
                mostrar(correlacoes(junto, NOME_POLUENTE | {"indice_calor": "índice de calor"}),
                        380, legenda=False)
            st.caption(f"Fonte: {fonte_pol}. Calor e sol aumentam o ozônio.")

        st.caption("Estações automáticas do INMET a 13 e 15 km de Heliópolis. Dentro da favela o "
                   "calor tende a ser maior. Quando houver sensores da UNAS em `data/sensores/`, "
                   "eles entram no lugar do INMET.")

# ============================================================ 4. população
with aba_pop:
    st.header("Quem vive o calor em Heliópolis?")
    try:
        pop = dados_censo()
    except Exception as e:  # noqa: BLE001
        pop = None
        st.error(f"Não foi possível baixar o Censo do IBGE: {e}")
    if pop is not None:
        h, cid = pop.loc["Heliópolis"], pop.loc["Município de São Paulo"]
        dens_h, dens_c = h["pessoas"] / h["area_km2"], cid["pessoas"] / cid["area_km2"]
        a, b, c, d = st.columns(4)
        a.metric("Moradores", milhar(h["pessoas"]))
        b.metric("Domicílios", milhar(h["domicilios"]))
        c.metric("Moradores por km²", milhar(dens_h), f"{f(dens_h / dens_c)}× a cidade",
                 delta_color="off")
        d.metric("Crianças 0–4 e idosos 60+", milhar(h["0 a 4"] + h["60 a 69"] + h["70 ou mais"]))

        st.markdown("##### Idade dos moradores")
        st.caption("Crianças pequenas e idosos sentem mais o calor: o corpo regula pior a "
                   "temperatura.")
        faixas = list(censo.FAIXAS_IDADE.values())
        fig = go.Figure()
        for nome, linha, cor in [("Heliópolis", h, COR["heliopolis"]),
                                 ("Cidade de SP", cid, COR["cidade"])]:
            p = linha[faixas] / linha["pessoas"] * 100
            fig.add_bar(x=[f"{x} anos" for x in faixas], y=p, name=nome,
                        marker=dict(color=cor, line_width=0),
                        hovertemplate=f"{nome}<br>%{{x}}: %{{y:.1f}}%<extra></extra>")
        fig.update_yaxes(title="% dos moradores", ticksuffix="%")
        mostrar(fig.update_layout(barmode="group"), 380)

        tabela = pop[["pessoas", "domicilios", "area_km2"]].copy()
        tabela["moradores/km²"] = tabela["pessoas"] / tabela["area_km2"]
        st.dataframe(tabela.style.format({"pessoas": milhar, "domicilios": milhar,
                                          "area_km2": "{:.2f}", "moradores/km²": milhar}),
                     use_container_width=True)
        st.caption(f"IBGE, Censo 2022: {h['setores']:.0f} setores da favela de Heliópolis. "
                   "A estimativa de ~200 mil da UNAS inclui o entorno.")
