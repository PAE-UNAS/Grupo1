"""Calor e saúde em Heliópolis — painel interativo.

Rodar:  streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from meteo import clima, config, cruzamento, saude, sensores

# Cor = identidade do lugar (a mesma em todos os gráficos)
COR = {"heliopolis": "#eb6834", "regiao": "#1baf7a", "cidade": "#2a78d6"}
CINZA, TINTA = "#a3a29c", "#52514e"
# Só o botão "baixar como imagem" (PNG em alta resolução), que aparece ao passar o mouse
CONFIG_GRAFICO = {"modeBarButtons": [["toImage"]], "displaylogo": False,
                  "toImageButtonOptions": {"format": "png", "scale": 2,
                                           "filename": "calor_heliopolis"}}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

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


@st.cache_data(show_spinner="Lendo os sensores…")
def dados_sensores(assinatura, placeholder):  # recalcula quando um arquivo muda
    # Dados reais (data/sensores/*.csv) têm prioridade; sem eles, usa a simulação.
    # Ver o quadro "COMO TROCAR OS DADOS SIMULADOS" no topo de meteo/sensores.py.
    return sensores.obter(dados_clima())


try:
    cl_om = dados_clima()                      # Open-Meteo, como baixada
except Exception as e:  # noqa: BLE001
    st.error(f"Não foi possível obter o clima da Open-Meteo: {e}")
    st.stop()
lim = clima.limiares(cl_om)                    # régua de calor: sempre a da Open-Meteo

# ----------------------------------------------------------- sensores
try:
    assinatura = tuple((a.name, a.stat().st_mtime) for a in sensores.arquivos())
    sens = dados_sensores(assinatura, config.SENSORES_PLACEHOLDER)
    erro_sensores = None
except Exception as e:  # noqa: BLE001
    sens, erro_sensores = None, str(e)
if sens is not None:
    df_s, rel_s, simulado = sens
    dia_s = sensores.diario(df_s)
    calib = sensores.calibrar(dia_s, cl_om)
else:
    df_s = rel_s = dia_s = calib = None
    simulado = False
AVISO_SIMULADO = ("⚠️ **DADOS SIMULADOS (placeholder).** Ainda não há sensores instalados: estes "
                  "números são fictícios e servem só para mostrar como a análise vai funcionar. "
                  "Não cite estes valores. Para usar os dados reais, veja o topo de "
                  "`meteo/sensores.py`.")

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
    opcoes_fonte = ["openmeteo"] + (["corrigida"] if calib else [])
    fonte = st.radio(
        "Fonte do clima", opcoes_fonte,
        format_func={"openmeteo": "Open-Meteo (regional)",
                     "corrigida": "Heliópolis corrigida pelos sensores"
                                  + (" (SIMULADO)" if simulado else "")}.get,
        help="**Open-Meteo**: estimativa para uma área de vários km². **Heliópolis corrigida**: "
             "a mesma série desde 1991, somada à diferença que os sensores dentro de Heliópolis "
             "medem em relação à Open-Meteo. A régua de calor (limiar) continua a mesma, então "
             "a diferença aparece como mais dias de calor.")
    grupo = st.selectbox("Tipo de internação", saude.GRUPOS_DIARIOS, format_func=saude.GRUPOS.get)
    padrao = [a for a in anos_ok if a not in config.ANOS_PANDEMIA][-3:]
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
    st.divider()
    st.caption(f"**Heliópolis** = CEP começando com {', '.join(config.CEPS_HELIOPOLIS)}.  \n"
               f"**Região do Ipiranga** = CEP começando com {', '.join(config.CEPS_REGIAO)} "
               "(inclui Heliópolis).  \n"
               "**Clima:** Open-Meteo · **Saúde:** DATASUS/SIH (internações de urgência no SUS)")

crit = config.CRITERIOS[criterio]
limiar = lim[crit["var"]]
corrigida = fonte == "corrigida"
# Clima usado em todas as análises: Open-Meteo ou a série corrigida pelos sensores
cl = clima.marcar_calor(sensores.corrigir(cl_om, calib), lim=lim) if corrigida else cl_om

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
    f"de urgência no SUS** (DATASUS). **{crit['nome']}** = "
    f"**{cruzamento.descricao(criterio, limiar)}**. O limiar é o valor que só os 10% mais quentes "
    f"dos verões de {config.CLIMATOLOGIA[0]}–{config.CLIMATOLOGIA[1]} alcançavam. Como Heliópolis "
    "tem poucas "
    "internações por dia, mostramos também a **região do Ipiranga**, que inclui Heliópolis e vive "
    "o mesmo clima, e a **cidade** como referência.")

if corrigida:
    st.info(f"**Fonte do clima: Heliópolis corrigida pelos sensores.** A série da Open-Meteo foi "
            f"somada a {'+' if calib['delta_tmax'] >= 0 else ''}{f(calib['delta_tmax'], 1)} °C na "
            f"máxima e {'+' if calib['delta_tmin'] >= 0 else ''}{f(calib['delta_tmin'], 1)} °C na "
            f"mínima, a diferença medida pelos sensores em {calib['dias']} dias.")
    if simulado:
        st.warning(AVISO_SIMULADO)
if erro_saude:
    st.warning(f"Os dados do DATASUS não estão disponíveis agora ({erro_saude}). "
               "As abas de clima e sensores continuam funcionando.")
elif not anos:
    st.info("Escolha pelo menos um ano na barra lateral para ver as internações.")
elif r is not None:
    with st.container(border=True):
        st.markdown("#### O que os dados mostram")
        for item in r["conclusoes"]:
            st.markdown(f"**{item['titulo']}** {item['texto']}")

aba_clima, aba_saude, aba_sensores, aba_metodo = st.tabs(
    ["🌡️ O calor está aumentando?", "🏥 Calor × internações", "📡 Sensores da UNAS",
     "📄 Como foi feito"])

# ============================================================ 1. clima
with aba_clima:
    anual = clima.resumo_anual(cl)
    tend = clima.tendencia(anual, criterio)
    dec = clima.por_decada(anual, criterio)
    completos = anual[anual["completo"]]

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
    fig.add_bar(x=anual["ano"], y=anual[criterio],
                name="Heliópolis corrigida" if corrigida else "dias de calor",
                marker=estilo_barras([COR["heliopolis"]] * len(anual), anual["completo"]),
                hovertemplate="%{x}: %{y} dias<extra></extra>")
    if corrigida:   # mostra quanto a correção muda em relação à Open-Meteo
        anual_om = clima.resumo_anual(cl_om)
        fig.add_scatter(x=anual_om["ano"], y=anual_om[criterio], name="Open-Meteo (regional)",
                        mode="lines+markers", line=dict(color=COR["cidade"], width=2),
                        marker=dict(size=6), hovertemplate="%{x}: %{y} dias (Open-Meteo)"
                                                           "<extra></extra>")
    if len(tend["x"]):
        fig.add_scatter(x=tend["x"], y=tend["y"], mode="lines", name="tendência",
                        line=dict(color=TINTA, dash="dash", width=2), hoverinfo="skip")
    fig.update_yaxes(title="dias no ano")
    mostrar(fig, 360, legenda=corrigida)
    if corrigida:
        st.caption("Barras = série corrigida pelos sensores; linha azul = Open-Meteo original. "
                   "A distância entre as duas mostra quantos dias de calor a estimativa regional "
                   "deixa de ver em Heliópolis." + (" **Valores simulados.**" if simulado else ""))

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
    st.caption(("Série corrigida pelos sensores (simulados). " if corrigida and simulado else
                "Série corrigida pelos sensores. " if corrigida else "") +
               "Fonte: Open-Meteo (reanálise ERA5) para o ponto central de Heliópolis. É uma "
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

        # ---- 2.4 arboviroses (análise mensal, à parte)
        st.divider()
        st.header("Dengue, chikungunya e zika × temperatura")
        st.caption("Estas doenças dependem do mosquito Aedes, que se reproduz mais rápido com calor e "
                   "água parada. O efeito aparece semanas depois, por isso a comparação é **por mês**: "
                   "internações por arboviroses (CID A90–A92) no mês × temperatura média e chuva do "
                   "mesmo mês e dos meses anteriores. Só os casos graves internam; é a ponta do "
                   "problema.")
        rec_arbo = st.radio("Lugar", ["cidade", "regiao", "heliopolis"],
                            format_func=saude.RECORTES.get, horizontal=True,
                            key="lugar_arbo", label_visibility="collapsed")
        arbo = cruzamento.arboviroses_mensal(cl, internacoes, rec_arbo)
        cor_arbo = {"Temperatura média": "#e34948", "Chuva acumulada": "#6250d6"}
        if arbo["mensal"]["internacoes"].sum() == 0:
            st.info("Não houve internações por arboviroses neste lugar e período.")
        else:
            a, b = st.columns([2, 3])
            with a:
                st.markdown("##### Quanto o clima anterior explica os casos")
                ca = arbo["correlacao"]
                fig = go.Figure()
                for var_nome, g in ca.groupby("variavel", sort=False):
                    sig = g["p_valor"] < .05
                    fig.add_bar(
                        x=["no mesmo mês", "1 mês antes", "2 meses antes"][:len(g)], y=g["rho"],
                        name=var_nome, marker=estilo_barras([cor_arbo[var_nome]] * len(g), sig),
                        text=[f(x, 2) for x in g["rho"]], textposition="outside",
                        cliponaxis=False,
                        hovertemplate=f"{var_nome}<br>%{{x}}: ρ = %{{y:.2f}}<extra></extra>")
                fig.update_traces(selector=dict(type="bar"), showlegend=False)
                for var_nome, cor_v in cor_arbo.items():     # legenda sempre com a cor cheia
                    fig.add_scatter(x=[None], y=[None], name=var_nome, mode="markers",
                                    marker=dict(symbol="square", size=13, color=cor_v))
                fig.add_hline(y=0, line=dict(color=TINTA, width=1.5))
                fig.update_yaxes(title="correlação (ρ de Spearman)", range=[-1, 1.15])
                mostrar(fig, 360)
                st.caption("ρ perto de +1 = meses mais quentes (ou chuvosos) vêm antes de mais "
                           "casos. Barra vazada = pode ser acaso.")
            with b:
                st.markdown("##### Mês a mês")
                from plotly.subplots import make_subplots
                m = arbo["mensal"]
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.08,
                                    row_heights=[.55, .45])
                fig.add_bar(x=m["mes"], y=m["internacoes"], name="internações",
                            marker_color=COR[rec_arbo], row=1, col=1,
                            hovertemplate="%{x|%m/%Y}: %{y} internações<extra></extra>")
                fig.add_scatter(x=m["mes"], y=m["temp_media"], name="temperatura média",
                                mode="lines+markers", line=dict(color=cor_arbo["Temperatura média"],
                                                                width=2), row=2, col=1,
                                hovertemplate="%{x|%m/%Y}: %{y:.1f} °C<extra></extra>")
                fig.update_yaxes(title_text="internações", row=1, col=1)
                fig.update_yaxes(title_text="°C", row=2, col=1)
                mostrar(fig, 360, legenda=False)
                st.caption("Em cima, internações por mês; embaixo, a temperatura média do mês. "
                           "Repare se os picos de casos vêm um ou dois meses depois dos meses quentes.")

# ============================================================ 3. sensores
CORES_SENSOR = ["#6250d6", "#e87ba4", "#008300", "#eda100", "#e34948", "#1baf7a"]
CORES_RISCO = {"sem risco": "#d6d5cf", "cautela": "#f5c46b", "cautela extrema": "#eb6834",
               "perigo": "#c4322f", "perigo extremo": "#7a1b1a"}


def instrucoes_sensores():
    st.markdown(
        "**Como usar os dados reais dos sensores**\n\n"
        "1. Exporte as leituras para arquivos `.csv` no formato abaixo.\n"
        "2. Dê aos sensores instalados **dentro de Heliópolis** um nome começando com "
        f"`{config.PREFIXO_SENSOR_HELIOPOLIS}` (ex.: `heliopolis_viela_01`). Só eles entram na "
        "calibração; os outros servem de controle.\n"
        "3. Salve os arquivos na pasta `data/sensores/` e recarregue a página. A simulação é "
        "desligada sozinha.\n\n"
        "**Formato** (uma linha por leitura; separador `;` ou `,`):")
    st.table(pd.DataFrame({
        "coluna": sensores.COLUNAS,
        "o que é": ["nome do sensor (ex.: heliopolis_viela_01)", "data e hora da leitura",
                    "temperatura do ar", "umidade relativa do ar (%)",
                    "C ou F (opcional; padrão C)"]}))
    st.download_button("Baixar arquivo-modelo (.csv)", sensores.modelo_csv().encode("utf-8-sig"),
                       "modelo_sensores.csv")


with aba_sensores:
    st.header("Sensores da UNAS")
    if erro_sensores:
        st.error(f"Não foi possível ler os sensores: {erro_sensores}")
    elif df_s is None:
        st.markdown("Ainda **não há dados dos sensores**. A Open-Meteo estima o clima de uma área "
                    "de vários km² e não enxerga o calor dentro das vielas de Heliópolis.")
        instrucoes_sensores()
    else:
        if simulado:
            st.warning(AVISO_SIMULADO)
            with st.expander("Como trocar pelos dados reais"):
                instrucoes_sensores()
        cor_de = {sid: CORES_SENSOR[i % len(CORES_SENSOR)]
                  for i, sid in enumerate(sorted(df_s["sensor_id"].unique()))}

        a, b, c, d = st.columns(4)
        a.metric("Leituras válidas", milhar(rel_s["linhas_limpas"]))
        b.metric("Valores impossíveis removidos", milhar(rel_s["outliers_removidos"]))
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
        for sid, g in dia_s.groupby("sensor_id"):
            fig.add_scatter(x=g["data"], y=g["indice_calor_max"], name=str(sid),
                            mode="lines", line=dict(width=2, color=cor_de[sid]))
        om = cl_om[cl_om["data"].between(dia_s["data"].min(), dia_s["data"].max())]
        fig.add_scatter(x=om["data"], y=om["sensacao_max"], name="Open-Meteo (sensação máx.)",
                        mode="lines", line=dict(color=CINZA, dash="dash", width=2))
        for y0, y1, cor in [(27, 32, "rgba(237,161,0,.08)"), (32, 41, "rgba(235,104,52,.10)"),
                            (41, 54, "rgba(227,73,72,.12)")]:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=cor, line_width=0)
        fig.update_yaxes(title="°C")
        mostrar(fig, 380)

        # ---- 3.2 calibração
        st.divider()
        st.markdown("##### Quanto Heliópolis é mais quente que a Open-Meteo?")
        if calib is None:
            st.info(f"Para calcular a correção são precisos pelo menos "
                    f"{sensores.MINIMO_DIAS_CALIBRACAO} dias completos de sensores com nome "
                    f"começando por `{config.PREFIXO_SENSOR_HELIOPOLIS}`.")
        else:
            a, b, c = st.columns(3)
            a.metric("Máxima: Heliópolis − Open-Meteo",
                     f"{'+' if calib['delta_tmax'] >= 0 else ''}{f(calib['delta_tmax'], 1)} °C",
                     help=f"Média de {calib['dias']} dias; varia ±{f(calib['dp_tmax'], 1)} °C "
                          "de um dia para outro.")
            b.metric("Mínima: Heliópolis − Open-Meteo",
                     f"{'+' if calib['delta_tmin'] >= 0 else ''}{f(calib['delta_tmin'], 1)} °C",
                     help=f"Média de {calib['dias']} dias; varia ±{f(calib['dp_tmin'], 1)} °C.")
            c.metric("Dias usados", calib["dias"])
            pares = calib["pares"]
            fig = go.Figure()
            fig.add_scatter(x=pares["tmax_om"], y=pares["tmax"], mode="markers",
                            name="máxima do dia", marker=dict(color=COR["heliopolis"], size=8,
                                                              opacity=.7),
                            hovertemplate="Open-Meteo %{x:.1f} °C<br>Heliópolis %{y:.1f} °C"
                                          "<extra></extra>")
            fig.add_scatter(x=pares["tmin_om"], y=pares["tmin"], mode="markers",
                            name="mínima do dia", marker=dict(color=COR["cidade"], size=8,
                                                              opacity=.7),
                            hovertemplate="Open-Meteo %{x:.1f} °C<br>Heliópolis %{y:.1f} °C"
                                          "<extra></extra>")
            lo = float(min(pares["tmin_om"].min(), pares["tmin"].min())) - 1
            hi = float(max(pares["tmax_om"].max(), pares["tmax"].max())) + 1
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
        with a:
            st.markdown("##### Horas por dia em cada faixa de risco")
            hr = sensores.horas_em_risco(df_s)
            ordem = (hr[hr["faixa"] != "sem risco"].groupby("sensor_id")["horas_dia"].sum()
                     .sort_values().index.tolist())
            fig = go.Figure()
            for faixa_r in sensores.FAIXAS_RISCO[1]:
                g = hr[hr["faixa"] == faixa_r].set_index("sensor_id").reindex(ordem)
                fig.add_bar(y=ordem, x=g["horas_dia"], name=faixa_r, orientation="h",
                            marker=dict(color=CORES_RISCO[faixa_r], line=dict(color="white",
                                                                               width=1)),
                            hovertemplate=f"%{{y}}<br>{faixa_r}: %{{x:.1f}} h/dia<extra></extra>")
            fig.update_layout(barmode="stack", bargap=.35)
            fig.update_xaxes(title="horas por dia (média)", range=[0, 24], dtick=6)
            st.plotly_chart(grafico(fig, 400).update_layout(
                legend=dict(y=-0.28, yanchor="top", traceorder="normal"),
                margin=dict(b=90)), width="stretch", config=CONFIG_GRAFICO)
            st.caption("Pelo índice de calor de cada leitura. Sensores mais acima passam mais "
                       "horas em risco: são os pontos mais quentes.")
        with b:
            st.markdown("##### A noite esfria?")
            pf = sensores.perfil_horario(df_s)
            fig = go.Figure()
            for sid, g in pf.groupby("sensor_id"):
                fig.add_scatter(x=g["hora"], y=g["temperatura"], name=str(sid), mode="lines",
                                line=dict(width=2, color=cor_de[sid]),
                                hovertemplate=f"{sid}<br>%{{x}}h: %{{y:.1f}} °C<extra></extra>")
            fig.add_vrect(x0=0, x1=6, fillcolor="rgba(98,80,214,.07)", line_width=0,
                          annotation_text="madrugada", annotation_position="bottom left")
            fig.update_xaxes(title="hora do dia", dtick=3, range=[0, 23])
            fig.update_yaxes(title="temperatura média (°C)")
            st.plotly_chart(grafico(fig, 400).update_layout(
                legend=dict(y=-0.28, yanchor="top"), margin=dict(b=90)),
                width="stretch", config=CONFIG_GRAFICO)
            st.caption("Temperatura média em cada hora. Se a madrugada continua quente, o corpo não "
                       "se recupera do calor do dia, e isso pesa mais para idosos e crianças.")

        comp_s = sensores.comparar_com_openmeteo(dia_s, cl_om)
        with st.expander("Diferença de cada sensor para a Open-Meteo e dados diários"):
            if len(comp_s):
                resumo = comp_s.groupby("sensor_id")[["dif_tmax", "dif_tmin"]].mean().round(1)
                resumo.columns = ["máxima: sensor − Open-Meteo (°C)",
                                  "mínima: sensor − Open-Meteo (°C)"]
                st.dataframe(resumo)
            st.dataframe(dia_s, hide_index=True)

# ============================================================ 4. método
with aba_metodo:
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
    if r is not None:
        tab = r["tabela"]
        cols = ["data", "tmax", "tmin", "sensacao_max", "chuva", "dia_calor", "janela_calor"] + \
               [x for x in tab.columns if x.count("__") == 1]
        st.download_button("Baixar tabela diária clima × internações (.csv)",
                           tab[cols].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "calor_internacoes_diario.csv")
    st.caption("Para salvar um gráfico como imagem, passe o mouse sobre ele e clique no ícone de "
               "câmera no canto superior direito. Guia completo: docs/COMO_USAR.md.")
    st.download_button("Baixar série de clima desde 1991 (.csv)",
                       cl.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       "clima_heliopolis_diario.csv")
