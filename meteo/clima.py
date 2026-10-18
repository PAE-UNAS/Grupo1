"""Clima — Open-Meteo (reanálise ERA5), dados diários desde 1991.

Docs: https://open-meteo.com/en/docs/historical-weather-api
Gratuita e sem chave. É uma estimativa para uma área de vários km² em volta
de Heliópolis: não mede dentro da favela e tende a subestimar o calor local.
"""
from datetime import date, timedelta

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
    resp = requests.get(URL, params=params, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Open-Meteo recusou o pedido: {resp.text[:300]}")

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
    return df


def carregar() -> pd.DataFrame:
    return tratar(baixar())
