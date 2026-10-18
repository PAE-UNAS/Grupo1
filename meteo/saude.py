"""Saúde — DATASUS, Sistema de Informações Hospitalares do SUS (SIH).

Cada internação paga pelo SUS gera uma AIH (Autorização de Internação
Hospitalar) com: data de entrada, diagnóstico (CID-10), idade e o CEP DE
RESIDÊNCIA do paciente. É o CEP que permite separar os moradores de Heliópolis.

O DATASUS publica um arquivo por estado e por mês de processamento:
    ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RDSP2401.dbc

Cuidados:
- O mês do arquivo é o mês em que o hospital COBROU, não o da internação.
  Uma internação de dezembro pode aparecer no arquivo de fevereiro. Por isso
  baixamos os meses do ano e mais 3 meses seguintes, e usamos DT_INTER.
- Só entram internações de URGÊNCIA (CAR_INT = 02). Cirurgias marcadas
  (eletivas) não têm relação com o calor e variam com o dia da semana.
- Só a AIH principal (IDENT = 1), para não contar a mesma pessoa duas vezes.
"""
from __future__ import annotations

import ftplib
import re
from pathlib import Path

import numpy as np
import pandas as pd
from dbfread import DBF
from pyreaddbc import dbc2dbf

from meteo import config

SERVIDOR = "ftp.datasus.gov.br"
PASTA = "/dissemin/publicos/SIHSUS/200801_/Dados"
COLUNAS = ["N_AIH", "CEP", "DT_INTER", "DIAG_PRINC", "IDADE", "COD_IDADE", "MORTE"]
MESES_DE_ATRASO = 3

GRUPOS = {
    "todas": "Todas as internações de urgência",
    "respiratorio": "Doenças respiratórias",
    "circulatorio": "Coração e circulação",
    "rins_desidratacao": "Rins, desidratação e insolação",
    "idosos": "Pessoas com 65 anos ou mais",
}
RECORTES = {"heliopolis": "Heliópolis", "resto_sp": "Resto da cidade de SP"}


# ------------------------------------------------------------------ download
def meses_disponiveis() -> list[str]:
    """Lista 'AAMM' dos arquivos RDSP no FTP (sem internet: os que estão no cache)."""
    try:
        with ftplib.FTP(SERVIDOR, timeout=60) as ftp:
            ftp.login()
            nomes = ftp.nlst(PASTA)
        meses = [m.group(1) for n in nomes if (m := re.search(r"RDSP(\d{4})\.DBC$", n.upper()))]
    except (OSError, ftplib.Error):
        meses = [p.stem[-4:] for p in config.CACHE.glob("internacoes_*.parquet")]
    return sorted(set(meses))


def anos_completos(meses: list[str]) -> list[int]:
    """Anos cujos 12 meses + 3 meses de atraso já foram publicados."""
    disponiveis = set(meses)
    anos = sorted({2000 + int(m[:2]) for m in meses})
    return [a for a in anos if all(m in disponiveis for m in _meses_do_ano(a))]


def _meses_do_ano(ano: int) -> list[str]:
    datas = pd.period_range(f"{ano}-01", periods=12 + MESES_DE_ATRASO, freq="M")
    return [p.strftime("%y%m") for p in datas]


def _ler_dbf(caminho: Path) -> pd.DataFrame:
    """Lê só as linhas de residentes do município de SP (urgência, AIH principal).

    `raw=True` evita decodificar as ~100 colunas de cada linha: o filtro é feito
    nos bytes e só as linhas que interessam são convertidas. Bem mais rápido.
    """
    mun = config.MUNICIPIO_SP.encode()
    linhas = []
    for reg in DBF(str(caminho), raw=True):
        if (reg["MUNIC_RES"].strip()[:6] == mun and reg["CAR_INT"].strip() == b"02"
                and reg["IDENT"].strip() == b"1"):
            linhas.append({c: reg[c].decode("latin-1").strip() for c in COLUNAS})
    return pd.DataFrame(linhas, columns=COLUNAS)


def baixar_mes(aamm: str) -> pd.DataFrame:
    """Internações de urgência de residentes de SP em um arquivo mensal (com cache)."""
    arquivo = config.CACHE / f"internacoes_{aamm}.parquet"
    if arquivo.exists():
        return pd.read_parquet(arquivo)

    config.CACHE.mkdir(parents=True, exist_ok=True)
    dbc = config.CACHE / f"RDSP{aamm}.dbc"
    with ftplib.FTP(SERVIDOR, timeout=300) as ftp:
        ftp.login()
        ftp.cwd(PASTA)
        nome = next(n for n in ftp.nlst() if n.upper() == f"RDSP{aamm}.DBC")
        with open(dbc, "wb") as f:
            ftp.retrbinary(f"RETR {nome}", f.write)
    dbf = dbc.with_suffix(".dbf")
    dbc2dbf(str(dbc), str(dbf))
    df = _ler_dbf(dbf)
    df.to_parquet(arquivo)
    dbc.unlink(missing_ok=True)       # apaga os arquivos grandes do estado
    dbf.unlink(missing_ok=True)
    return df


# ---------------------------------------------------------------- tratamento
def tratar(df: pd.DataFrame) -> pd.DataFrame:
    """Datas, idade, recorte (Heliópolis ou resto) e grupos de diagnóstico."""
    df = df.drop_duplicates("N_AIH").copy()
    df["data"] = pd.to_datetime(df["DT_INTER"], format="%Y%m%d", errors="coerce")

    # COD_IDADE: 4 = anos, 5 = 100 + anos; 1–3 = horas/dias/meses (bebês)
    cod = pd.to_numeric(df["COD_IDADE"], errors="coerce")
    valor = pd.to_numeric(df["IDADE"], errors="coerce")
    df["idade"] = np.select([cod == 4, cod == 5, cod.between(1, 3)],
                            [valor, 100 + valor, 0], default=np.nan)

    cep = df["CEP"].str.replace(r"\D", "", regex=True).str.zfill(8)
    df["recorte"] = np.where(cep.str[:5].isin(config.CEPS_HELIOPOLIS),
                             "heliopolis", "resto_sp")

    cid = df["DIAG_PRINC"].str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    df["todas"] = True
    df["respiratorio"] = cid.str.startswith("J")
    df["circulatorio"] = cid.str.startswith("I")
    # Efeitos mais diretos do calor: insuficiência renal aguda, desidratação,
    # distúrbios de sais minerais, efeitos do calor e da luz (insolação)
    df["rins_desidratacao"] = cid.str.match(r"^(N1[7-9]|E8[67]|T67|X30)")
    df["idosos"] = df["idade"] >= 65
    return df.dropna(subset=["data"])


def internacoes_diarias(df: pd.DataFrame, anos: list[int]) -> pd.DataFrame:
    """Uma linha por dia; colunas '<recorte>__<grupo>' com o número de internações."""
    df = df[df["data"].dt.year.isin(anos)]
    grade = pd.DatetimeIndex(np.concatenate(
        [pd.date_range(f"{a}-01-01", f"{a}-12-31") for a in sorted(anos)]))
    partes = []
    for recorte in RECORTES:
        contagem = df[df["recorte"] == recorte].groupby("data")[list(GRUPOS)].sum()
        contagem.columns = [f"{recorte}__{g}" for g in GRUPOS]
        partes.append(contagem)
    diario = pd.concat(partes, axis=1).reindex(grade).fillna(0).astype(int)
    return diario.rename_axis("data").reset_index()


def carregar(anos: list[int], progresso=None) -> pd.DataFrame:
    """Baixa (se preciso) e conta as internações por dia nos anos pedidos.

    `progresso(i, total, aamm)` é chamado a cada arquivo (para a barra do app).
    """
    meses = sorted({m for a in anos for m in _meses_do_ano(a)})
    partes = []
    for i, aamm in enumerate(meses):
        if progresso:
            progresso(i, len(meses), aamm)
        partes.append(baixar_mes(aamm))
    return internacoes_diarias(tratar(pd.concat(partes, ignore_index=True)), anos)
