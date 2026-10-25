"""Limpeza da base horária: timestamps, unidades, outliers, lacunas e duplicatas."""
import numpy as np
import pandas as pd

TEMP_MIN, TEMP_MAX = -5.0, 50.0
UMID_MIN, UMID_MAX = 0.0, 100.0


def padronizar_timestamp(df):
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", dayfirst=True)
    return df


def padronizar_unidades(df):
    df = df.copy()
    f = df["unidade_temp"] == "F"
    df.loc[f, "temperatura"] = (df.loc[f, "temperatura"] - 32) * 5 / 9
    df["unidade_temp"] = "C"
    return df


def remover_outliers(df):
    df = df.copy()
    df.loc[~df["temperatura"].between(TEMP_MIN, TEMP_MAX), "temperatura"] = np.nan
    df.loc[~df["umidade"].between(UMID_MIN, UMID_MAX), "umidade"] = np.nan
    return df


def tratar_ausentes(df, limite_horas=3):
    df = df.sort_values(["sensor_id", "timestamp"]).copy()
    cols = ["temperatura", "umidade"]
    df[cols] = df.groupby("sensor_id")[cols].transform(
        lambda s: s.interpolate(limit=limite_horas, limit_area="inside"))
    return df


def limpar(df):
    relatorio = {"linhas_brutas": len(df)}
    relatorio["ausentes_antes"] = int(df[["temperatura", "umidade"]].isna().sum().sum())
    relatorio["sensores_em_fahrenheit"] = int((df.groupby("sensor_id")["unidade_temp"]
                                               .first() == "F").sum())

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
