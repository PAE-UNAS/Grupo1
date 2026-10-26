"""Poluição do ar: CETESB QUALAR (medição, precisa de login) ou Open-Meteo (modelo)."""
import io
import os

import pandas as pd
import requests

from meteo import config


def baixar_openmeteo(inicio, fim, timeout=60):
    params = {"latitude": config.LATITUDE, "longitude": config.LONGITUDE,
              "start_date": inicio, "end_date": fim, "timezone": config.FUSO,
              "hourly": "pm10,pm2_5,ozone,nitrogen_dioxide"}
    resp = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", params=params,
                        timeout=timeout)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["hourly"]).rename(columns={"time": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def baixar_cetesb(inicio, fim, parametro=57, estacao=86, timeout=60):
    # QUALAR exige cadastro gratis: CETESB_USUARIO e CETESB_SENHA
    # estacao 86 = Sao Caetano do Sul (3,9 km de Heliopolis); parametro 57 = MP2.5,
    # 63 = O3, 15 = NO2, 25 = temperatura, 28 = umidade. Datas em dd/mm/aaaa.
    usuario, senha = os.environ.get("CETESB_USUARIO"), os.environ.get("CETESB_SENHA")
    if not (usuario and senha):
        raise RuntimeError("CETESB_USUARIO e CETESB_SENHA não definidos")
    s = requests.Session()
    s.post("https://qualar.cetesb.sp.gov.br/qualar/autenticador",
           data={"cetesb_login": usuario, "cetesb_password": senha}, timeout=timeout)
    resp = s.post("https://qualar.cetesb.sp.gov.br/qualar/exportaDados.do?method=pesquisar",
                  data={"irede": "A", "dataInicialStr": inicio, "dataFinalStr": fim,
                        "iTipoDado": "P", "estacaoVO.nestcaMonto": estacao,
                        "parametroVO.nparmt": parametro}, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_html(io.StringIO(resp.text), decimal=",", thousands=".")[1]
    df = df.iloc[:, [4, 5, 10, 12]]
    df.columns = ["dia", "hora", "valor", "valido"]
    df = df[df["valido"] == "Sim"]
    # QUALAR marca meia-noite como 24:00
    df["timestamp"] = (pd.to_datetime(df["dia"], format="%d/%m/%Y")
                       + pd.to_timedelta(df["hora"].str[:2].astype(int), unit="h"))
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["fonte"] = f"CETESB QUALAR {estacao}/{parametro}"
    return df[["timestamp", "valor", "fonte"]].reset_index(drop=True)




CETESB_PARAMETROS = {"pm2_5": 57, "ozone": 63, "nitrogen_dioxide": 15}


def media_diaria(df, colunas):
    out = df.set_index("timestamp")[colunas].resample("D").mean()
    return out.rename_axis("data")


def diaria(inicio, fim):
    """Média diária em µg/m³ e o nome da fonte. CETESB quando há login, senão Open-Meteo."""
    try:
        ini_br, fim_br = (pd.Timestamp(d).strftime("%d/%m/%Y") for d in (inicio, fim))
        partes = [media_diaria(baixar_cetesb(ini_br, fim_br, cod).rename(columns={"valor": nome}),
                               [nome]) for nome, cod in CETESB_PARAMETROS.items()]
        return pd.concat(partes, axis=1), "CETESB São Caetano do Sul (medição)"
    except Exception:
        pass
    df = baixar_openmeteo(inicio, fim)
    return media_diaria(df, ["pm10", "pm2_5", "ozone", "nitrogen_dioxide"]), "Open-Meteo (modelo)"
