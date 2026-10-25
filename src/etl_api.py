"""Coleta das fontes públicas. Cada baixar_* devolve um DataFrame com timestamp e fonte."""
import io
import os
import tempfile
import zipfile
from ftplib import FTP
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HELIOPOLIS_LAT, HELIOPOLIS_LON = -23.611, -46.594
PASTA_INMET = Path("data/raw/inmet")
# o portal do INMET derruba conexao sem User-Agent de navegador
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
# estacoes automaticas do INMET na capital (Heliopolis fica no meio das duas)
ESTACOES_INMET = {"A701": "Mirante de Santana (13 km)", "A771": "Interlagos (15 km)"}
MUNICIPIO_SP_SIH = "355030"
# verao 2025/26
PERIODO = ("2025-12-01", "2026-03-31")


def open_meteo(url, variaveis, inicio, fim, timeout):
    params = {"latitude": HELIOPOLIS_LAT, "longitude": HELIOPOLIS_LON,
              "start_date": inicio, "end_date": fim,
              "hourly": variaveis, "timezone": "America/Sao_Paulo"}
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["hourly"]).rename(columns={"time": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def baixar_clima(inicio, fim, timeout=30):
    df = open_meteo("https://archive-api.open-meteo.com/v1/archive",
                    "temperature_2m,relative_humidity_2m", inicio, fim, timeout)
    df = df.rename(columns={"temperature_2m": "temp_ref", "relative_humidity_2m": "umid_ref"})
    df["fonte"] = "Open-Meteo Archive"
    return df


def base_referencia(inicio, fim):
    # medicoes reais das estacoes do INMET no formato da base de sensores
    modelo = baixar_clima(inicio, fim).set_index("timestamp")
    partes = []
    for estacao, nome in ESTACOES_INMET.items():
        c = baixar_inmet(inicio, fim, estacao)
        # hora sem medicao recebe o valor do Open-Meteo (modelo) e fica marcada
        c["preenchido_modelo"] = c["temp_inmet"].isna() | c["umid_inmet"].isna()
        c["temp_inmet"] = c["temp_inmet"].fillna(c["timestamp"].map(modelo["temp_ref"]))
        c["umid_inmet"] = c["umid_inmet"].fillna(c["timestamp"].map(modelo["umid_ref"]))
        partes.append(pd.DataFrame({
            "sensor_id": estacao,
            "zona": f"INMET {nome}",
            "timestamp": c["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "temperatura": c["temp_inmet"],
            "umidade": c["umid_inmet"],
            "unidade_temp": "C",
            "preenchido_modelo": c["preenchido_modelo"],
            "fonte": f"INMET {estacao}"}))
    return pd.concat(partes, ignore_index=True)


def baixar_poluicao(inicio, fim, timeout=30):
    df = open_meteo("https://air-quality-api.open-meteo.com/v1/air-quality",
                    "pm10,pm2_5,ozone,nitrogen_dioxide", inicio, fim, timeout)
    df["fonte"] = "Open-Meteo Air Quality"
    return df


def baixar_openaq(raio_m=25000, timeout=30):
    chave = os.environ.get("OPENAQ_API_KEY")
    if not chave:
        raise RuntimeError("OPENAQ_API_KEY não definida")
    resp = requests.get("https://api.openaq.org/v3/locations",
                        params={"coordinates": f"{HELIOPOLIS_LAT},{HELIOPOLIS_LON}",
                                "radius": raio_m, "limit": 100},
                        headers={"X-API-Key": chave}, timeout=timeout)
    resp.raise_for_status()
    df = pd.json_normalize(resp.json()["results"])
    df = df[["id", "name", "coordinates.latitude", "coordinates.longitude"]]
    df["fonte"] = "OpenAQ"
    return df


def baixar_inmet(inicio, fim, estacao="A701", timeout=600):
    # a API apitempo pede token, entao usa o arquivo anual do portal (um zip por ano)
    # https://portal.inmet.gov.br/dadoshistoricos
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
        df = pd.read_csv(csv, sep=";", skiprows=8, encoding="latin-1", decimal=",")
        partes.append(df)
    df = pd.concat(partes)
    hora = df["Data"] + " " + df["Hora UTC"].str[:4]
    # INMET grava em UTC, Sao Paulo está em UTC-3 sem horario de verao desde 2019
    df["timestamp"] = pd.to_datetime(hora, format="%Y/%m/%d %H%M") - pd.Timedelta(hours=3)
    df["temp_inmet"] = pd.to_numeric(df["TEMPERATURA DO AR - BULBO SECO, HORARIA (°C)"],
                                     errors="coerce")
    df["umid_inmet"] = pd.to_numeric(df["UMIDADE RELATIVA DO AR, HORARIA (%)"],
                                     errors="coerce")
    df = df[df["timestamp"].between(inicio, f"{fim} 23:59")]
    df = df.replace(-9999, np.nan)
    df["fonte"] = f"INMET {estacao}"
    return df[["timestamp", "temp_inmet", "umid_inmet", "fonte"]].reset_index(drop=True)


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


def ler_dbf(caminho, colunas):
    # le o dbf direto com numpy, bem mais rapido que linha a linha
    from dbfread import DBF

    cab = DBF(str(caminho), load=False, encoding="latin-1")
    campos = [("apagado", "S1")] + [(c.name, f"S{c.length}") for c in cab.fields]
    bruto = np.fromfile(caminho, dtype=np.dtype(campos), offset=cab.header.headerlen,
                        count=cab.header.numrecords)
    df = pd.DataFrame({c: np.char.decode(bruto[c], "latin-1") for c in colunas})
    return df.apply(lambda s: s.str.strip())


def baixar_dbc(pastas, nome, colunas):
    # tenta cada pasta do FTP do DATASUS ate achar o arquivo
    from datasus_dbc import decompress

    with tempfile.TemporaryDirectory() as tmp:
        dbc = Path(tmp) / nome
        dbf = Path(tmp) / nome.replace(".dbc", ".dbf")
        with FTP("ftp.datasus.gov.br", timeout=60) as ftp:
            ftp.login()
            for pasta in pastas:
                ftp.cwd(pasta)
                if nome in ftp.nlst():
                    break
            else:
                raise FileNotFoundError(nome)
            with open(dbc, "wb") as f:
                ftp.retrbinary(f"RETR {nome}", f.write)
        decompress(str(dbc), str(dbf))
        return ler_dbf(dbf, colunas)


def baixar_internacoes_sih(ano, mes, uf="SP"):
    colunas = ["DT_INTER", "DIAG_PRINC", "IDADE", "COD_IDADE", "SEXO", "MUNIC_RES"]
    df = baixar_dbc(["/dissemin/publicos/SIHSUS/200801_/Dados"],
                    f"RD{uf}{str(ano)[2:]}{mes:02d}.dbc", colunas)
    df = df[df["MUNIC_RES"] == MUNICIPIO_SP_SIH].reset_index(drop=True)
    df["fonte"] = "DATASUS SIH-RD"
    return df


def baixar_obitos_sim(ano, uf="SP"):
    # ano fechado fica em CID10/DORES, ano recente em PRELIM/DORES
    colunas = ["DTOBITO", "CAUSABAS", "IDADE", "SEXO", "CODMUNRES"]
    df = baixar_dbc(["/dissemin/publicos/SIM/CID10/DORES", "/dissemin/publicos/SIM/PRELIM/DORES"],
                    f"DO{uf}{ano}.dbc", colunas)
    df = df[df["CODMUNRES"] == MUNICIPIO_SP_SIH].reset_index(drop=True)
    df["fonte"] = "DATASUS SIM"
    return df


FAIXAS_IDADE = {"V01031": "0 a 4", "V01032": "5 a 9", "V01033": "10 a 14", "V01034": "15 a 19",
                "V01035": "20 a 24", "V01036": "25 a 29", "V01037": "30 a 39", "V01038": "40 a 49",
                "V01039": "50 a 59", "V01040": "60 a 69", "V01041": "70 ou mais"}


def baixar_censo(arquivo=Path("data/raw/ibge/censo_2022.csv"), timeout=900):
    # Censo 2022 por setor censitario: Heliopolis (99 setores), distrito Sacoma e municipio
    # https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/
    if arquivo.exists():
        return pd.read_csv(arquivo, index_col=0)
    base = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"

    def ler(caminho, **kw):
        resp = requests.get(base + caminho, timeout=timeout)
        resp.raise_for_status()
        if caminho.endswith(".xlsx"):
            return pd.read_excel(io.BytesIO(resp.content), dtype=str, **kw)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str, **kw)
        return df

    fcu = ler("Favelas_e_comunidades_urbanas_Resultados_do_universo/Anexos/"
              "FavelaseComunidadesUrbanas2022Setores_20250417.xlsx", sheet_name="Setores_FCUs")
    helio = set(fcu.loc[(fcu["CD_MUN"] == "3550308")
                        & (fcu["NM_FCU"] == "Heliópolis"), "CD_SETOR"])
    basico = ler("Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
                 "Agregados_por_setores_basico_BR_20260520.zip",
                 usecols=["CD_SETOR", "CD_MUN", "NM_DIST", "AREA_KM2", "v0001", "v0007"])
    idade = ler("Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
                "Agregados_por_setores_demografia_BR.zip",
                usecols=["CD_setor", *FAIXAS_IDADE])
    sp = basico[basico["CD_MUN"] == "3550308"].merge(
        idade.rename(columns={"CD_setor": "CD_SETOR"}), on="CD_SETOR", how="left")
    numericas = ["AREA_KM2", "v0001", "v0007", *FAIXAS_IDADE]
    # IBGE usa virgula decimal e "X" em setor com dado sigiloso
    sp[numericas] = sp[numericas].apply(
        lambda s: pd.to_numeric(s.str.replace(",", "."), errors="coerce"))
    recortes = {"Heliópolis": sp[sp["CD_SETOR"].isin(helio)],
                "Distrito Sacomã": sp[sp["NM_DIST"] == "Sacomã"],
                "Município de São Paulo": sp}
    df = pd.DataFrame({nome: r[numericas].sum() for nome, r in recortes.items()}).T
    df = df.rename(columns={"AREA_KM2": "area_km2", "v0001": "pessoas",
                            "v0007": "domicilios", **FAIXAS_IDADE})
    df["setores"] = [len(r) for r in recortes.values()]
    df["fonte"] = "IBGE Censo 2022"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(arquivo)
    return df
