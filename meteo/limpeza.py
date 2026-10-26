"""Limpeza de séries de sensores de temperatura e umidade.

Veio da branch `feature-limpeza-dados`. Foi pensada para os sensores que a
UNAS pretende instalar em Heliópolis, mas serve para qualquer série com as
colunas abaixo (uma linha por leitura):

    sensor_id     identificador do sensor (texto)
    timestamp     data e hora da leitura (aceita vários formatos, dia primeiro)
    temperatura   número
    umidade       umidade relativa do ar, em %
    unidade_temp  "C" ou "F" (opcional; se faltar, assume Celsius)

Etapas, nesta ordem:
    1. padronizar_timestamp  texto -> data/hora
    2. padronizar_unidades   Fahrenheit -> Celsius
    3. remover_outliers      valores fisicamente impossíveis viram vazio
    4. tratar_ausentes       lacunas curtas (até 3 leituras) são interpoladas
    5. remove leituras duplicadas (mesmo sensor e horário)
"""
import numpy as np
import pandas as pd

# Limites físicos plausíveis para São Paulo. Fora disso é erro do sensor.
TEMP_MIN, TEMP_MAX = -5.0, 50.0
UMID_MIN, UMID_MAX = 0.0, 100.0


def padronizar_timestamp(df):
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", dayfirst=True)
    return df


def padronizar_unidades(df):
    df = df.copy()
    if "unidade_temp" not in df:
        df["unidade_temp"] = "C"
    f = df["unidade_temp"].astype(str).str.strip().str.upper() == "F"
    df.loc[f, "temperatura"] = (df.loc[f, "temperatura"] - 32) * 5 / 9
    df["unidade_temp"] = "C"
    return df


def remover_outliers(df):
    df = df.copy()
    df.loc[~df["temperatura"].between(TEMP_MIN, TEMP_MAX), "temperatura"] = np.nan
    df.loc[~df["umidade"].between(UMID_MIN, UMID_MAX), "umidade"] = np.nan
    return df


def tratar_ausentes(df, limite_horas=3):
    """Interpola lacunas curtas DENTRO da série de cada sensor.

    Lacunas maiores que `limite_horas` leituras continuam vazias: inventar
    dados por muito tempo esconderia uma falha real do sensor.
    """
    df = df.sort_values(["sensor_id", "timestamp"]).copy()
    cols = ["temperatura", "umidade"]
    df[cols] = df.groupby("sensor_id")[cols].transform(
        lambda s: s.interpolate(limit=limite_horas, limit_area="inside"))
    return df


def limpar(df):
    """Aplica todas as etapas e devolve (dados limpos, relatório de qualidade)."""
    df = df.copy()
    for c in ("temperatura", "umidade"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "unidade_temp" not in df:
        df["unidade_temp"] = "C"

    relatorio = {"linhas_brutas": len(df)}
    relatorio["ausentes_antes"] = int(df[["temperatura", "umidade"]].isna().sum().sum())
    relatorio["sensores_em_fahrenheit"] = int(
        (df.groupby("sensor_id")["unidade_temp"].first().astype(str).str.upper() == "F").sum())

    df = padronizar_timestamp(df)
    df = padronizar_unidades(df)

    antes = df[["temperatura", "umidade"]].isna().sum().sum()
    df = remover_outliers(df)
    depois = df[["temperatura", "umidade"]].isna().sum().sum()
    relatorio["outliers_removidos"] = int(depois - antes)

    df = tratar_ausentes(df)
    relatorio["ausentes_depois"] = int(df[["temperatura", "umidade"]].isna().sum().sum())

    df = df.drop_duplicates(["sensor_id", "timestamp"])
    relatorio["linhas_limpas"] = len(df)
    return df.reset_index(drop=True), relatorio
