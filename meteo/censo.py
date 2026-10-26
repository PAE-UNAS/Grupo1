"""População de Heliópolis: IBGE, Censo 2022, por setor censitário."""
import io
import zipfile

import pandas as pd
import requests

from meteo import config

FAIXAS_IDADE = {"V01031": "0 a 4", "V01032": "5 a 9", "V01033": "10 a 14", "V01034": "15 a 19",
                "V01035": "20 a 24", "V01036": "25 a 29", "V01037": "30 a 39", "V01038": "40 a 49",
                "V01039": "50 a 59", "V01040": "60 a 69", "V01041": "70 ou mais"}


def baixar_censo(arquivo=config.CACHE / "censo_2022.csv", timeout=900):
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
