"""Clima — Open-Meteo (reanálise ERA5), dados diários desde 1991.

Docs: https://open-meteo.com/en/docs/historical-weather-api
Gratuita e sem chave. É uma estimativa para uma área de vários km² em volta
de Heliópolis: não mede dentro da favela e tende a subestimar o calor local.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from meteo import config

URL = "https://archive-api.open-meteo.com/v1/archive"

# nome na API -> nome no projeto
VARIAVEIS = {
    "temperature_2m_max": "tmax",
    "temperature_2m_min": "tmin",
    "temperature_2m_mean": "tmedia",
    "apparent_temperature_max": "sensacao_max",  # considera umidade e vento
    "precipitation_sum": "chuva",
}


def ultima_data() -> date:
    """A reanálise é publicada com ~5 dias de atraso."""
    return date.today() - timedelta(days=6)


def baixar() -> pd.DataFrame:
    """Baixa a série diária de 1991 até hoje (ou lê do cache, se já baixou hoje)."""
    fim = ultima_data()
    arquivo = config.CACHE / f"clima_{fim}.parquet"
    if arquivo.exists():
        return pd.read_parquet(arquivo)

    params = {
        "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
        "start_date": f"{config.CLIMATOLOGIA[0]}-01-01", "end_date": str(fim),
        "daily": ",".join(VARIAVEIS), "timezone": config.FUSO,
    }
    try:
        resp = requests.get(URL, params=params, timeout=120)
    except requests.RequestException:
        resp = None
    if resp is None or resp.status_code != 200:
        # Sem internet ou API fora do ar: usa o último arquivo baixado, se houver
        anteriores = sorted(config.CACHE.glob("clima_*.parquet"))
        if anteriores:
            return pd.read_parquet(anteriores[-1])
        motivo = resp.text[:300] if resp is not None else "sem conexão"
        raise RuntimeError(f"Open-Meteo recusou o pedido: {motivo}")

    df = pd.DataFrame(resp.json()["daily"]).rename(columns={"time": "data", **VARIAVEIS})
    config.CACHE.mkdir(parents=True, exist_ok=True)
    for antigo in config.CACHE.glob("clima_*.parquet"):   # só guarda a versão mais nova
        antigo.unlink()
    df.to_parquet(arquivo)
    return df


def tratar(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos, duplicatas, valores impossíveis e colunas de calendário."""
    df = df.copy()
    df["data"] = pd.to_datetime(df["data"])
    df = df.drop_duplicates("data").sort_values("data").reset_index(drop=True)

    for col in ["tmax", "tmin", "tmedia", "sensacao_max"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[(df[col] < -5) | (df[col] > 50), col] = None     # fora do possível em SP
    df["chuva"] = pd.to_numeric(df["chuva"], errors="coerce").clip(lower=0)
    df.loc[df["tmin"] > df["tmax"], ["tmax", "tmin", "tmedia"]] = None

    # Dias que faltarem aparecem como linhas vazias (não somem em silêncio)
    grade = pd.date_range(df["data"].min(), df["data"].max(), freq="D")
    df = df.set_index("data").reindex(grade).rename_axis("data").reset_index()

    df["ano"], df["mes"] = df["data"].dt.year, df["data"].dt.month
    return marcar_calor(df)


def carregar() -> pd.DataFrame:
    return tratar(baixar())


# -------------------------------------------------------- o que é "calor"
def limiares(df: pd.DataFrame) -> dict[str, float]:
    """Percentil 90 de cada variável nos meses quentes do período de referência.

    Usar um período fixo (1991–2020) faz "dia de calor" significar a mesma
    coisa em qualquer ano: se hoje há mais dias acima do limiar, é porque
    esquentou, e não porque a régua mudou.
    """
    ini, fim = config.CLIMATOLOGIA
    ref = df[df["ano"].between(ini, fim) & df["mes"].isin(config.MESES_QUENTES)]
    if ref["sensacao_max"].notna().sum() < 365:   # série curta: usa o que houver
        ref = df[df["mes"].isin(config.MESES_QUENTES)]
    return {v: float(np.nanpercentile(ref[v], config.PERCENTIL_DIA_CALOR))
            for v in {c["var"] for c in config.CRITERIOS.values()}}


def _ondas(quente: pd.Series, minimo: int) -> pd.Series:
    """Marca os dias que fazem parte de uma sequência de `minimo`+ dias quentes."""
    bloco = (quente != quente.shift()).cumsum()
    tamanho = quente.groupby(bloco).transform("size")
    return quente & (tamanho >= minimo)


def marcar_calor(df: pd.DataFrame, lim: dict | None = None) -> pd.DataFrame:
    """Uma coluna booleana por critério de calor (dia_quente, noite_quente, onda_calor).

    `lim` permite fixar os limiares. Na série corrigida pelos sensores usamos
    os limiares da Open-Meteo, para que a régua de calor seja a mesma e a
    diferença apareça como MAIS dias acima do limiar.
    """
    df = df.copy()
    lim = lim or limiares(df)
    df["dia_quente"] = df["sensacao_max"] >= lim["sensacao_max"]
    df["noite_quente"] = df["tmin"] >= lim["tmin"]
    df["onda_calor"] = _ondas(df["dia_quente"], config.DIAS_ONDA)
    df.attrs["limiares"] = lim
    return df


# ----------------------------------------------- o calor está aumentando?
def resumo_anual(df: pd.DataFrame) -> pd.DataFrame:
    """Dias de calor por ano (cada critério) + tendência em dias por década.

    O ano corrente aparece marcado como incompleto.
    """
    criterios = list(config.CRITERIOS)
    anual = df.groupby("ano").agg(**{c: (c, "sum") for c in criterios},
                                  dias_com_dado=("sensacao_max", "count"))
    anual["completo"] = anual["dias_com_dado"] >= 360
    return anual.reset_index()


def tendencia(anual: pd.DataFrame, criterio: str) -> dict:
    """Reta de tendência (mínimos quadrados) só com anos completos."""
    a = anual[anual["completo"]]
    if len(a) < 5:
        return {"por_decada": np.nan, "x": [], "y": []}
    coef = np.polyfit(a["ano"], a[criterio], 1)
    x = np.array([a["ano"].min(), a["ano"].max()])
    return {"por_decada": 10 * coef[0], "x": x, "y": np.polyval(coef, x)}


def por_decada(anual: pd.DataFrame, criterio: str) -> pd.DataFrame:
    """Média de dias de calor por ano em cada década (só anos completos)."""
    a = anual[anual["completo"]].copy()
    a["decada"] = (a["ano"] // 10) * 10
    d = a.groupby("decada")[criterio].agg(["mean", "count"]).reset_index()
    d["rotulo"] = [f"{max(x, a['ano'].min())}–{min(x + 9, a['ano'].max())}" for x in d["decada"]]
    return d


def mapa_ano_mes(df: pd.DataFrame, criterio: str) -> pd.DataFrame:
    """Matriz ano × mês com o número de dias de calor (para o mapa de calor)."""
    m = df.pivot_table(index="ano", columns="mes", values=criterio, aggfunc="sum")
    return m.reindex(columns=range(1, 13))
