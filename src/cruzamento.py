"""Agregação diária e cruzamento de calor com poluição e saúde."""
import pandas as pd

GRUPOS_CID = {
    "Desidratação (E86)": ("E86",),
    "Lesão renal aguda (N17)": ("N17",),
    "Circulatório (I)": ("I",),
    "Respiratório (J)": ("J",),
}


def media_diaria(df, colunas):
    out = df.set_index("timestamp")[colunas].resample("D").mean()
    out.index = out.index.date
    out.index.name = "data"
    return out


def internacoes_diarias(sih):
    sih = sih.copy()
    sih["data"] = pd.to_datetime(sih["DT_INTER"], format="%Y%m%d", errors="coerce").dt.date
    cols = {}
    for nome, prefixos in GRUPOS_CID.items():
        mask = sih["DIAG_PRINC"].astype(str).str.startswith(prefixos)
        cols[nome] = sih[mask].groupby("data").size()
    return pd.DataFrame(cols).fillna(0).astype(int).sort_index()


def obitos_diarios(sim):
    sim = sim.copy()
    sim["data"] = pd.to_datetime(sim["DTOBITO"], format="%d%m%Y", errors="coerce").dt.date
    cols = {"Óbitos (total)": sim.groupby("data").size()}
    # IDADE do SIM: 1o digito e a unidade (4 = anos, 5 = mais de 100 anos)
    idade = pd.to_numeric(sim["IDADE"], errors="coerce")
    idoso = ((idade >= 465) & (idade < 500)) | (idade >= 500)
    cols["Óbitos 65+ anos"] = sim[idoso].groupby("data").size()
    for nome, prefixos in GRUPOS_CID.items():
        mask = sim["CAUSABAS"].astype(str).str.startswith(prefixos)
        cols[f"Óbitos {nome}"] = sim[mask].groupby("data").size()
    return pd.DataFrame(cols).fillna(0).astype(int).sort_index()


def correlacao_defasada(tabela, coluna, max_dias=3):
    # r entre o calor de d dias atras e cada coluna de saude
    outras = tabela.drop(columns=coluna)
    return pd.DataFrame({f"{d} dia(s)": outras.corrwith(tabela[coluna].shift(d))
                         for d in range(max_dias + 1)})


def juntar(local_diario, *outros):
    base = local_diario
    for o in outros:
        base = base.join(o, how="left")
    return base
