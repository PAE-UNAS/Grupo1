from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src import cruzamento, etl_api, indices, limpeza

st.set_page_config(page_title="Estresse Térmico em Heliópolis", layout="wide")

CAMINHO_REAL = Path("data/raw/sensores.csv")
POLUENTES_CETESB = {"pm2_5": 57, "ozone": 63, "nitrogen_dioxide": 15}
FAIXAS_ALTAS = ["Cautela extrema", "Perigo", "Perigo extremo"]
# sem botao de baixar imagem no plotly
CONFIG_PLOTLY = {"displaylogo": False, "modeBarButtonsToRemove": ["toImage"]}


def grafico(fig, titulo_y=None):
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), legend_title_text="",
                      yaxis_title=titulo_y)
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def correlacao(df):
    fig = px.imshow(df.corr().round(2), text_auto=True, color_continuous_scale="RdBu_r",
                    zmin=-1, zmax=1)
    grafico(fig)


def numero(x):
    return f"{x:,.0f}".replace(",", ".")


def graus(x):
    return f"{x:.1f} °C".replace(".", ",")


@st.cache_data(show_spinner="Baixando medições do INMET...")
def carregar():
    if CAMINHO_REAL.exists():
        bruta, fonte = pd.read_csv(CAMINHO_REAL), "csv"
    else:
        bruta, fonte = etl_api.base_referencia(*etl_api.PERIODO), "api"
    limpa, qualidade = limpeza.limpar(bruta)
    return bruta, indices.adicionar_indices(limpa), qualidade, fonte


@st.cache_data(show_spinner="Baixando Censo do IBGE...")
def carregar_censo():
    try:
        return etl_api.baixar_censo()
    except Exception:
        return None


@st.cache_data(show_spinner="Baixando poluição...")
def carregar_poluicao(inicio, fim):
    # medicao da CETESB quando ha login, senao o modelo do Open-Meteo
    try:
        ini_br, fim_br = (pd.Timestamp(d).strftime("%d/%m/%Y") for d in (inicio, fim))
        partes = {nome: etl_api.baixar_cetesb(ini_br, fim_br, codigo)
                  .rename(columns={"valor": nome})
                  for nome, codigo in POLUENTES_CETESB.items()}
        dia = pd.concat([cruzamento.media_diaria(p, [n]) for n, p in partes.items()], axis=1)
        return dia, "CETESB São Caetano do Sul (medição)"
    except Exception:
        pass
    try:
        poluicao = etl_api.baixar_poluicao(inicio, fim)
    except Exception:
        return None, None
    dia = cruzamento.media_diaria(poluicao, ["pm10", "pm2_5", "ozone", "nitrogen_dioxide"])
    return dia, "Open-Meteo (modelo)"


@st.cache_data(show_spinner="Baixando internações do DATASUS...")
def carregar_internacoes(ano, mes):
    try:
        return cruzamento.internacoes_diarias(etl_api.baixar_internacoes_sih(ano, mes))
    except Exception:
        return None


@st.cache_data(show_spinner="Baixando óbitos do DATASUS...")
def carregar_obitos(ano):
    try:
        return cruzamento.obitos_diarios(etl_api.baixar_obitos_sim(ano))
    except Exception:
        return None


try:
    bruta, base, relatorio_dados, fonte = carregar()
except Exception:
    st.error("Não foi possível baixar os dados agora. Tente mais tarde.")
    st.stop()
censo = carregar_censo()

st.title("Estresse Térmico em Heliópolis")
st.caption("Instituto Mauá de Tecnologia × UNAS Heliópolis (Observatório De Olho na Quebrada)")

# filtros valem para as abas de estresse termico e saude
ini, fim = base["timestamp"].min().date(), base["timestamp"].max().date()
c1, c2 = st.columns([2, 3])
periodo = c1.date_input("Período", (ini, fim), min_value=ini, max_value=fim,
                        format="DD/MM/YYYY")
if len(periodo) != 2:
    st.stop()
locais = sorted(base["zona"].unique())
zonas = c2.multiselect("Local de medição", locais, default=locais,
                       help="Sem sensores em Heliópolis por enquanto: estações do INMET.")

f = base[base["zona"].isin(zonas)
         & base["timestamp"].dt.date.between(periodo[0], periodo[1])]

abas = st.tabs(["Estresse térmico", "População exposta", "Saúde e poluição"])

with abas[0]:
    if f.empty:
        st.info("Nenhum dado para os filtros escolhidos.")
    else:
        dias = f.set_index("timestamp")["indice_calor"].resample("D").max()
        n_locais = f["sensor_id"].nunique()
        c = st.columns(4)
        c[0].metric("Índice de calor máximo", graus(f["indice_calor"].max()))
        c[1].metric("WBGT máximo", graus(f["wbgt"].max()))
        c[2].metric("Dias com alerta (IC ≥ 27 °C)", f"{int((dias >= 27).sum())} de {len(dias)}")
        c[3].metric("Horas em cautela extrema ou pior",
                    numero(f["risco"].isin(FAIXAS_ALTAS).sum() / n_locais),
                    help="Média por local")
        st.caption("Estações a 13 e 15 km de Heliópolis. Na comunidade o calor tende a ser maior.")

        st.subheader("Índice de calor máximo por dia")
        diario = (f.set_index("timestamp").groupby("zona")["indice_calor"]
                  .resample("D").max().reset_index())
        fig = px.line(diario, x="timestamp", y="indice_calor", color="zona",
                      labels={"timestamp": "", "indice_calor": "°C", "zona": ""})
        fig.add_hline(y=27, line_dash="dash", line_color="orange", annotation_text="Alerta")
        fig.add_hline(y=32, line_dash="dash", line_color="red",
                      annotation_text="Cautela extrema")
        grafico(fig, "°C")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Horas por faixa de risco")
            horas = ((f["risco"].value_counts() / n_locais)
                     .reindex([x[1] for x in indices.FAIXAS]).fillna(0).reset_index())
            horas.columns = ["faixa", "horas"]
            grafico(px.bar(horas, x="faixa", y="horas", labels={"faixa": ""}), "horas")
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
            correlacao(f[["temperatura", "umidade", "indice_calor", "wbgt"]])

with abas[1]:
    if censo is None:
        st.error("IBGE indisponível agora. Tente mais tarde.")
    else:
        h, cidade = censo.loc["Heliópolis"], censo.loc["Município de São Paulo"]
        dens_h = h["pessoas"] / h["area_km2"]
        dens_c = cidade["pessoas"] / cidade["area_km2"]
        c = st.columns(4)
        c[0].metric("Moradores", numero(h["pessoas"]))
        c[1].metric("Domicílios", numero(h["domicilios"]))
        c[2].metric("Moradores por km²", numero(dens_h), f"{dens_h / dens_c:.0f}× a cidade",
                    delta_color="off")
        c[3].metric("Crianças 0–4 e idosos 60+",
                    numero(h["0 a 4"] + h["60 a 69"] + h["70 ou mais"]),
                    help="Grupos mais sensíveis ao calor")

        st.subheader("Faixa etária (% dos moradores)")
        faixas = list(etl_api.FAIXAS_IDADE.values())
        perc = pd.DataFrame({"Heliópolis": h[faixas] / h["pessoas"] * 100,
                             "São Paulo": cidade[faixas] / cidade["pessoas"] * 100})
        perc.index = [f"{x} anos" for x in faixas]
        perc = perc.rename_axis("faixa").reset_index().melt("faixa", var_name="recorte",
                                                             value_name="%")
        grafico(px.bar(perc, x="faixa", y="%", color="recorte", barmode="group",
                       labels={"faixa": ""}), "%")

        tabela = censo[["pessoas", "domicilios", "area_km2"]].copy()
        tabela["moradores/km²"] = tabela["pessoas"] / tabela["area_km2"]
        st.dataframe(tabela.style.format({"pessoas": numero, "domicilios": numero,
                                          "area_km2": "{:.2f}", "moradores/km²": numero}),
                     use_container_width=True)
        st.caption(f"IBGE, Censo 2022: {h['setores']:.0f} setores da favela de Heliópolis. "
                   "A estimativa de ~200 mil da UNAS inclui o entorno.")

with abas[2]:
    st.caption("DATASUS, município de São Paulo. Correlação não prova causa. "
               "Defasagem de 0 a 3 dias.")
    if f.empty:
        st.info("Nenhum dado para os filtros escolhidos.")
    else:
        ini_s, fim_s = f["timestamp"].min().date(), f["timestamp"].max().date()
        local = cruzamento.media_diaria(f, ["temperatura", "umidade", "indice_calor"])

        # obitos (baixa um arquivo por ano, demora na primeira vez)
        st.subheader("Óbitos")
        lista = []
        for ano in range(ini_s.year, fim_s.year + 1):
            lista.append(carregar_obitos(ano))
        if any(x is None for x in lista):
            st.write("Não deu para baixar os óbitos agora.")
        else:
            obitos = pd.concat(lista).fillna(0).sort_index()
            tab = cruzamento.juntar(local[["indice_calor"]], obitos)
            grafico(px.line(tab[["Óbitos (total)", "Óbitos 65+ anos"]]), "óbitos")
            st.write(cruzamento.correlacao_defasada(tab, "indice_calor").round(2))
            st.caption("Correlação com o índice de calor. Dados de 2025 e 2026 são preliminares.")

        # internacoes (um arquivo por mes)
        st.subheader("Internações")
        lista = []
        for m in pd.period_range(ini_s, fim_s, freq="M"):
            lista.append(carregar_internacoes(m.year, m.month))
        if any(x is None for x in lista):
            st.write("Não deu para baixar as internações agora.")
        else:
            internacoes = pd.concat(lista).groupby(level=0).sum()
            tab = cruzamento.juntar(local[["indice_calor"]], internacoes)
            grafico(px.line(tab.drop(columns="indice_calor")), "internações")
            st.write(cruzamento.correlacao_defasada(tab, "indice_calor").round(2))
            st.caption("Correlação com o índice de calor.")

        st.subheader("Poluição")
        poluicao, fonte_pol = carregar_poluicao(str(ini_s), str(fim_s))
        if poluicao is None:
            st.error("Poluição indisponível agora.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                grafico(px.line(poluicao, labels={"data": "", "value": "µg/m³"}), "µg/m³")
            with col2:
                correlacao(cruzamento.juntar(local, poluicao))
            st.caption(fonte_pol)
