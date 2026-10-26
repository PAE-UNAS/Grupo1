"""Medições horárias: sensores da UNAS (se houver) ou estações automáticas do INMET.

INMET: https://portal.inmet.gov.br/dadoshistoricos (um zip por ano, CSV por estação).
A API apitempo pede token, por isso usamos o arquivo anual.
"""
import zipfile

import numpy as np
import pandas as pd
import requests

from meteo import config, indices
from meteo.limpeza import limpar

# o portal do INMET derruba a conexão sem User-Agent de navegador
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
PASTA_INMET = config.CACHE / "inmet"
COLUNAS = ["sensor_id", "zona", "timestamp", "temperatura", "umidade", "unidade_temp"]


def baixar_inmet(inicio, fim, estacao="A701", timeout=600):
    partes = []
    for ano in range(int(inicio[:4]), int(fim[:4]) + 1):
        csv = PASTA_INMET / f"{estacao}_{ano}.csv"
        if not csv.exists():
            zip_ano = PASTA_INMET / f"{ano}.zip"
            if not zip_ano.exists():
                PASTA_INMET.mkdir(parents=True, exist_ok=True)
                resp = requests.get(f"https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip",
                                    headers=NAVEGADOR, timeout=timeout)
                resp.raise_for_status()
                zip_ano.write_bytes(resp.content)
            with zipfile.ZipFile(zip_ano) as zf:
                # no ano corrente sai um arquivo novo por mes, o maior é o mais completo
                infos = [i for i in zf.infolist() if f"_{estacao}_" in i.filename]
                csv.write_bytes(zf.read(max(infos, key=lambda i: i.file_size)))
        partes.append(pd.read_csv(csv, sep=";", skiprows=8, encoding="latin-1", decimal=","))
    df = pd.concat(partes)
    hora = df["Data"] + " " + df["Hora UTC"].str[:4]
    # INMET grava em UTC; São Paulo está em UTC-3 sem horário de verão desde 2019
    df["timestamp"] = pd.to_datetime(hora, format="%Y/%m/%d %H%M") - pd.Timedelta(hours=3)
    df["temperatura"] = pd.to_numeric(df["TEMPERATURA DO AR - BULBO SECO, HORARIA (°C)"],
                                      errors="coerce")
    df["umidade"] = pd.to_numeric(df["UMIDADE RELATIVA DO AR, HORARIA (%)"], errors="coerce")
    df = df[df["timestamp"].between(inicio, f"{fim} 23:59")].replace(-9999, np.nan)
    return df[["timestamp", "temperatura", "umidade"]].reset_index(drop=True)


def open_meteo_horario(inicio, fim, timeout=60):
    params = {"latitude": config.LATITUDE, "longitude": config.LONGITUDE,
              "start_date": inicio, "end_date": fim, "timezone": config.FUSO,
              "hourly": "temperature_2m,relative_humidity_2m"}
    resp = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params,
                        timeout=timeout)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["hourly"])
    return df.set_index(pd.to_datetime(df["time"]))


def inmet(inicio, fim):
    # horas sem medicao recebem o valor do Open-Meteo e ficam marcadas
    modelo = open_meteo_horario(inicio, fim)
    partes = []
    for estacao, nome in config.ESTACOES_INMET.items():
        c = baixar_inmet(inicio, fim, estacao)
        c["preenchido_modelo"] = c["temperatura"].isna() | c["umidade"].isna()
        c["temperatura"] = c["temperatura"].fillna(c["timestamp"].map(modelo["temperature_2m"]))
        c["umidade"] = c["umidade"].fillna(c["timestamp"].map(modelo["relative_humidity_2m"]))
        c["sensor_id"], c["zona"], c["unidade_temp"] = estacao, nome, "C"
        c["fonte"] = f"INMET {estacao}"
        partes.append(c)
    return pd.concat(partes, ignore_index=True)


def sensores():
    arquivos = sorted(config.SENSORES.glob("*.csv"))
    if not arquivos:
        return None
    df = pd.concat([pd.read_csv(a) for a in arquivos], ignore_index=True)
    if "zona" not in df:
        df["zona"] = df["sensor_id"]
    df["fonte"] = "Sensores UNAS"
    return df


def carregar(inicio=config.PERIODO_HORARIO[0], fim=config.PERIODO_HORARIO[1]):
    """Base horária limpa com índice de calor, WBGT e faixa de risco."""
    bruta = sensores()
    if bruta is None:
        bruta = inmet(inicio, fim)
    limpa, relatorio = limpar(bruta)
    return indices.adicionar_indices(limpa), relatorio
