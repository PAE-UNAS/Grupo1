"""Estresse térmico em Heliópolis. Rodar: streamlit run app.py"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from meteo import censo, clima, config, cruzamento, estacoes, indices, poluicao, saude

st.set_page_config(page_title="Estresse Térmico em Heliópolis", layout="wide")

# cor de cada recorte, a mesma em todos os graficos
COR = {"heliopolis": "#eb6834", "regiao": "#1baf7a", "cidade": "#2a78d6"}
TINTA = "#52514e"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
FAIXAS_ALTAS = ["Cautela extrema", "Perigo", "Perigo extremo"]
# sem botao de baixar imagem
CONFIG_PLOTLY = {"displaylogo": False, "modeBarButtonsToRemove": ["toImage"]}


def grafico(fig, titulo_y=None, altura=380):
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=10, b=0), separators=",.",
                      legend=dict(orientation="h", y=1.12, x=0, title=None), yaxis_title=titulo_y)
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def barras(cores, significativos):
    # cheia = diferenca confiavel, vazada = pode ser acaso
    return dict(color=[c if s else "rgba(0,0,0,0)" for c, s in zip(cores, significativos)],
                line=dict(color=cores, width=2.5))


def numero(x):
    return f"{x:,.0f}".replace(",", ".")


def num(x, casas=1):
    return "–" if pd.isna(x) else f"{x:.{casas}f}".replace(".", ",")


def pct(x):
    return "–" if pd.isna(x) else ("+" if x > 0 else "") + f"{x:.0f}%"


@st.cache_data(show_spinner="Baixando medições horárias do INMET...")
def dados_horarios():
    return estacoes.carregar()


@st.cache_data(show_spinner="Baixando clima desde 1991 (Open-Meteo)...", ttl="12h")
def dados_clima():
    return clima.carregar()


@st.cache_data(show_spinner="Baixando Censo do IBGE...")
def dados_censo():
    try:
        return censo.baixar_censo()
    except Exception:
        return None


@st.cache_data(show_spinner="Baixando poluição...")
def dados_poluicao(inicio, fim):
    try:
        return poluicao.diaria(inicio, fim)
    except Exception:
        return None, None


@st.cache_data(show_spinner="Consultando o DATASUS...", ttl="24h")
def meses_saude():
    return saude.meses_disponiveis()


@st.cache_data(show_spinner="Contando internações...")
def dados_saude(anos):
    return saude.carregar(list(anos))


st.title("Estresse Térmico em Heliópolis")
st.caption("Instituto Mauá de Tecnologia × UNAS Heliópolis (Observatório De Olho na Quebrada)")

abas = st.tabs(["Estresse térmico", "O calor está aumentando?", "População exposta",
                "Calor e internações"])

# ------------------------------------------------------------ estresse termico
with abas[0]:
    try:
        base, qualidade = dados_horarios()
    except Exception:
        st.error("Não deu para baixar as medições agora.")
        st.stop()

    ini, fim = base["timestamp"].min().date(), base["timestamp"].max().date()
    c1, c2 = st.columns([2, 3])
    periodo = c1.date_input("Período", (ini, fim), min_value=ini, max_value=fim,
                            format="DD/MM/YYYY")
    locais = sorted(base["zona"].unique())
    zonas = c2.multiselect("Local de medição", locais, default=locais)
    if len(periodo) != 2:
        st.stop()
    f = base[base["zona"].isin(zonas) & base["timestamp"].dt.date.between(*periodo)]

    if f.empty:
        st.info("Nenhum dado para os filtros escolhidos.")
    else:
        dias = f.set_index("timestamp")["indice_calor"].resample("D").max()
        n_locais = f["sensor_id"].nunique()
        c = st.columns(4)
        c[0].metric("Índice de calor máximo", f"{num(f['indice_calor'].max())} °C")
        c[1].metric("WBGT máximo", f"{num(f['wbgt'].max())} °C")
        c[2].metric("Dias com alerta (IC ≥ 27 °C)", f"{int((dias >= 27).sum())} de {len(dias)}")
        c[3].metric("Horas em cautela extrema ou pior",
                    numero(f["risco"].isin(FAIXAS_ALTAS).sum() / n_locais))
        st.caption("Estações do INMET a 13 e 15 km de Heliópolis. Na comunidade o calor tende "
                   "a ser maior.")

        st.subheader("Índice de calor máximo por dia")
        diario = (f.set_index("timestamp").groupby("zona")["indice_calor"]
                  .resample("D").max().reset_index())
        fig = px.line(diario, x="timestamp", y="indice_calor", color="zona",
                      labels={"timestamp": ""})
        fig.add_hline(y=27, line_dash="dash", line_color="orange", annotation_text="Alerta")
        fig.add_hline(y=32, line_dash="dash", line_color="red", annotation_text="Cautela extrema")
        grafico(fig, "°C")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Horas por faixa de risco")
            horas = ((f["risco"].value_counts() / n_locais)
                     .reindex([x[1] for x in indices.FAIXAS]).fillna(0))
            grafico(px.bar(x=horas.index, y=horas.values, labels={"x": ""}), "horas")
        with col2:
            st.subheader("Índice de calor médio por hora")
            hora = (f.groupby([f["timestamp"].dt.hour.rename("hora"), "zona"])["indice_calor"]
                    .mean().reset_index())
            grafico(px.line(hora, x="hora", y="indice_calor", color="zona", markers=True), "°C")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribuição por local")
            grafico(px.box(f, x="zona", y="indice_calor", labels={"zona": ""}), "°C")
        with col2:
            st.subheader("Correlações")
            corr = f[["temperatura", "umidade", "indice_calor", "wbgt"]].corr().round(2)
            grafico(px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r",
                              zmin=-1, zmax=1))

        st.subheader("Poluição no período")
        pol, fonte_pol = dados_poluicao(str(periodo[0]), str(periodo[1]))
        if pol is None:
            st.write("Não deu para baixar a poluição agora.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                grafico(px.line(pol, labels={"data": "", "value": "µg/m³"}), "µg/m³")
            with col2:
                calor_dia = f.set_index("timestamp")["indice_calor"].resample("D").mean()
                tab = pol.join(calor_dia.rename("indice_calor"))
                grafico(px.imshow(tab.corr().round(2), text_auto=True,
                                  color_continuous_scale="RdBu_r", zmin=-1, zmax=1))
            st.caption(fonte_pol)

# ------------------------------------------------------- calor desde 1991
try:
    cl = dados_clima()
    lim = clima.limiares(cl)
except Exception:
    cl = None

with abas[1]:
    if cl is None:
        st.error("Não deu para baixar o clima da Open-Meteo agora.")
    else:
        criterio = st.radio("O que conta como calor", list(config.CRITERIOS), horizontal=True,
                            format_func=lambda c: config.CRITERIOS[c]["nome"], key="crit_clima")
        crit = config.CRITERIOS[criterio]
        anual = clima.resumo_anual(cl)
        tend = clima.tendencia(anual, criterio)
        dec = clima.por_decada(anual, criterio)

        c = st.columns(3)
        if len(dec) >= 2:
            c[0].metric(f"Por ano em {dec['rotulo'].iloc[0]}", num(dec["mean"].iloc[0], 0))
            c[1].metric(f"Por ano em {dec['rotulo'].iloc[-1]}", num(dec["mean"].iloc[-1], 0))
        c[2].metric("Tendência (dias por década)", num(tend["por_decada"]))
        st.caption(f"{crit['nome']}: {cruzamento.descricao(criterio, lim[crit['var']])} "
                   f"(10% mais quentes dos verões de {config.CLIMATOLOGIA[0]}–"
                   f"{config.CLIMATOLOGIA[1]}).")

        st.subheader(f"{crit['plural']} por ano")
        fig = go.Figure()
        fig.add_bar(x=anual["ano"], y=anual[criterio], name="dias",
                    marker=barras([COR["heliopolis"]] * len(anual), anual["completo"]))
        if len(tend["x"]):
            fig.add_scatter(x=tend["x"], y=tend["y"], mode="lines", name="tendência",
                            line=dict(color=TINTA, dash="dash"))
        fig.update_layout(showlegend=False)
        grafico(fig, "dias no ano")
        st.caption("Barra vazada = ano ainda incompleto. Linha tracejada = tendência.")

        st.subheader("Dias de calor por mês")
        mapa = clima.mapa_ano_mes(cl, criterio)
        fig = go.Figure(go.Heatmap(z=mapa.values, x=MESES, y=mapa.index, colorscale="Oranges",
                                   xgap=2, ygap=2))
        fig.update_yaxes(autorange="reversed", dtick=5)
        grafico(fig, altura=600)
        st.caption("Open-Meteo (reanálise ERA5), ponto central de Heliópolis.")

# ------------------------------------------------------------ populacao
with abas[2]:
    pop = dados_censo()
    if pop is None:
        st.error("IBGE indisponível agora.")
    else:
        h, cidade = pop.loc["Heliópolis"], pop.loc["Município de São Paulo"]
        dens_h = h["pessoas"] / h["area_km2"]
        dens_c = cidade["pessoas"] / cidade["area_km2"]
        c = st.columns(4)
        c[0].metric("Moradores", numero(h["pessoas"]))
        c[1].metric("Domicílios", numero(h["domicilios"]))
        c[2].metric("Moradores por km²", numero(dens_h), f"{dens_h / dens_c:.0f}× a cidade",
                    delta_color="off")
        c[3].metric("Crianças 0–4 e idosos 60+",
                    numero(h["0 a 4"] + h["60 a 69"] + h["70 ou mais"]))

        st.subheader("Faixa etária (% dos moradores)")
        faixas = list(censo.FAIXAS_IDADE.values())
        perc = pd.DataFrame({"Heliópolis": h[faixas] / h["pessoas"] * 100,
                             "São Paulo": cidade[faixas] / cidade["pessoas"] * 100})
        perc.index = [f"{x} anos" for x in faixas]
        perc = perc.rename_axis("faixa").reset_index().melt("faixa", var_name="recorte",
                                                             value_name="%")
        grafico(px.bar(perc, x="faixa", y="%", color="recorte", barmode="group",
                       labels={"faixa": ""}), "%")

        tabela = pop[["pessoas", "domicilios", "area_km2"]].copy()
        tabela["moradores/km²"] = tabela["pessoas"] / tabela["area_km2"]
        st.dataframe(tabela.style.format({"pessoas": numero, "domicilios": numero,
                                          "area_km2": "{:.2f}", "moradores/km²": numero}),
                     use_container_width=True)
        st.caption(f"IBGE, Censo 2022: {h['setores']:.0f} setores da favela de Heliópolis. "
                   "A estimativa de ~200 mil da UNAS inclui o entorno.")

# ------------------------------------------------------ calor e internacoes
with abas[3]:
    try:
        anos_ok = saude.anos_completos(meses_saude())
    except Exception:
        anos_ok = []
    if cl is None or not anos_ok:
        st.error("DATASUS ou Open-Meteo indisponível agora.")
    else:
        c1, c2, c3 = st.columns(3)
        criterio = c1.selectbox("O que conta como calor", list(config.CRITERIOS),
                                format_func=lambda c: config.CRITERIOS[c]["nome"],
                                key="crit_saude")
        grupo = c2.selectbox("Tipo de internação", list(saude.GRUPOS),
                             format_func=saude.GRUPOS.get)
        padrao = [a for a in anos_ok if a not in config.ANOS_PANDEMIA][-2:]
        anos = c3.multiselect("Anos", anos_ok, default=padrao)
        st.caption("Heliópolis = CEP " + ", ".join(config.CEPS_HELIOPOLIS) + ". Região do "
                   "Ipiranga = CEP 042. Internações de urgência no SUS. Cada ano novo leva "
                   "alguns minutos para baixar na primeira vez.")

        if anos:
            # baixa os meses que faltam, um arquivo por vez
            faltando = sorted({m for a in anos for m in saude._meses_do_ano(a)
                               if not (config.CACHE / f"internacoes_{m}.parquet").exists()})
            if faltando:
                barra = st.progress(0.0)
                for i, m in enumerate(faltando):
                    barra.progress(i / len(faltando),
                                   f"Baixando DATASUS: {i + 1} de {len(faltando)} (20{m[:2]}/{m[2:]})")
                    saude.baixar_mes(m)
                barra.empty()
            r = cruzamento.analisar(cl, dados_saude(tuple(sorted(anos))), grupo, criterio,
                                    config.POP_HELIOPOLIS, True, limiares=lim)

            with st.container(border=True):
                for item in r["conclusoes"]:
                    st.markdown(f"**{item['titulo']}** {item['texto']}")

            st.subheader("Quanto mais quente, mais internações?")
            fx = r["faixas"]
            fig = go.Figure()
            for rec, nome in saude.RECORTES.items():
                d = fx[fx["recorte"] == rec]
                fig.add_bar(x=d["faixa"].astype(str), y=d["variacao"], name=nome,
                            marker=barras([COR[rec]] * len(d), d["significativo"]),
                            text=[pct(v) for v in d["variacao"]], textposition="outside")
            fig.add_hline(y=0, line_color=TINTA)
            fig.update_xaxes(title=cruzamento.TEXTO_VAR[r["var"]])
            grafico(fig, "% acima do normal", 420)
            st.caption("Novembro a março. Barra vazada = pode ser acaso.")

            st.subheader("Quando o efeito aparece?")
            lg = r["defasagem"]
            fig = go.Figure()
            for rec, nome in saude.RECORTES.items():
                d = lg[lg["recorte"] == rec]
                fig.add_scatter(x=d["dias_depois"], y=d["variacao"], name=nome,
                                mode="lines+markers", line=dict(color=COR[rec]),
                                marker=dict(size=10, line=dict(color=COR[rec], width=2),
                                            color=[COR[rec] if s else "white"
                                                   for s in d["significativo"]]))
            fig.add_hline(y=0, line_color=TINTA)
            fig.update_xaxes(title="dias depois do dia de calor", dtick=1)
            grafico(fig, "% acima do normal")

            st.subheader("Nos dias de calor, Heliópolis sofre mais?")
            t = r["comparacao"]["tabela"]
            fig = go.Figure(go.Bar(
                x=t["lugar"], y=t["variacao"], text=[pct(v) for v in t["variacao"]],
                marker=barras([COR[x] for x in t["recorte"]], t["significativo"]),
                error_y=dict(type="data", symmetric=False, array=t["ic_sup"] - t["variacao"],
                             arrayminus=t["variacao"] - t["ic_inf"], color="#a3a29c")))
            fig.add_hline(y=0, line_color=TINTA)
            grafico(fig, "% acima do normal")
            st.caption(f"Dias de calor e os {config.DIAS_DEPOIS} seguintes, cada lugar comparado "
                       "com o próprio normal. Traço cinza = intervalo de 95%.")
