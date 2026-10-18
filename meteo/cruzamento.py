"""Cruzamento calor × internações.

A pergunta: quando faz muito calor, mais gente precisa ser internada às pressas?

Como comparar de forma justa
----------------------------
O número de internações muda com o mês (inverno tem mais doenças
respiratórias) e com o dia da semana. Então, para cada dia, calculamos quantas
internações seriam NORMAIS para aquele mês e aquele dia da semana:

    normal = média de internações por dia no mesmo mês do mesmo ano
             × peso do dia da semana (ex.: segunda costuma ter mais)

E comparamos com o que aconteceu: "+15%" quer dizer 15% acima do normal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from meteo import config
from meteo.saude import GRUPOS, RECORTES

FAIXAS_TEMP = [-np.inf, 26, 28, 30, 32, 34, np.inf]
NOMES_FAIXAS = ["até 26 °C", "26–28 °C", "28–30 °C", "30–32 °C", "32–34 °C", "34 °C ou mais"]


def col(recorte: str, grupo: str) -> str:
    return f"{recorte}__{grupo}"


# --------------------------------------------------------------- base diária
def montar_tabela(clima: pd.DataFrame, internacoes: pd.DataFrame) -> pd.DataFrame:
    """Junta clima e internações por dia e calcula o 'normal' de cada série."""
    tab = internacoes.merge(clima, on="data", how="inner").dropna(subset=["tmax"])
    tab = tab.sort_values("data").reset_index(drop=True)
    tab["muito_quente"] = tab["tmax"] >= config.DIA_MUITO_QUENTE
    tab["verao"] = tab["data"].dt.month.isin(config.MESES_QUENTES)
    # O "normal" é calculado só com dias SEM calor; senão os próprios dias
    # quentes inflariam a média do mês e esconderiam o efeito.
    sem_calor = ~dias_de_calor(tab)
    ano_mes = [tab["data"].dt.year, tab["data"].dt.month]
    dia_semana = tab["data"].dt.dayofweek
    for recorte in RECORTES:
        for grupo in GRUPOS:
            c = col(recorte, grupo)
            media_mes = tab[c].where(sem_calor).groupby(ano_mes).transform("mean")
            media_mes = media_mes.fillna(tab.groupby(ano_mes)[c].transform("mean"))
            peso_semana = (tab.groupby(dia_semana)[c].transform("mean") / tab[c].mean()
                           if tab[c].mean() > 0 else 1.0)
            tab[f"{c}__normal"] = media_mes * peso_semana
    return tab


def comparar(obs: pd.Series, normal: pd.Series) -> dict:
    """Observado × normal, com intervalo de 95% (aproximação de Poisson)."""
    o, n = float(obs.sum()), float(normal.sum())
    if n <= 0 or o <= 0:
        return {"dias": len(obs), "obs_dia": o / max(len(obs), 1),
                "normal_dia": n / max(len(obs), 1), "variacao": np.nan,
                "ic_inf": np.nan, "ic_sup": np.nan, "significativo": False}
    razao, erro = o / n, 1.96 / np.sqrt(o)
    lo, hi = razao * np.exp(-erro), razao * np.exp(erro)
    return {"dias": len(obs), "obs_dia": o / len(obs), "normal_dia": n / len(obs),
            "variacao": 100 * (razao - 1), "ic_inf": 100 * (lo - 1), "ic_sup": 100 * (hi - 1),
            "significativo": not (lo <= 1 <= hi)}


def dias_de_calor(tab: pd.DataFrame) -> pd.Series:
    """Dias muito quentes E os DIAS_DEPOIS dias seguintes (sem contar repetido)."""
    marca = tab["muito_quente"].copy()
    for d in range(1, config.DIAS_DEPOIS + 1):
        marca |= tab["muito_quente"].shift(d, fill_value=False)
    return marca


# ------------------------------------------------------------------ análises
def por_faixa_de_temperatura(tab: pd.DataFrame, recorte: str, grupo: str) -> pd.DataFrame:
    """Só novembro a março: internações vs. normal em cada faixa de máxima."""
    v = tab[tab["verao"]]
    faixa = pd.cut(v["tmax"], FAIXAS_TEMP, labels=NOMES_FAIXAS, right=False)
    c = col(recorte, grupo)
    linhas = [{"faixa": nome, **comparar(bloco[c], bloco[f"{c}__normal"])}
              for nome, bloco in v.groupby(faixa, observed=True)]
    return pd.DataFrame(linhas)


def por_grupo(tab: pd.DataFrame, recorte: str) -> pd.DataFrame:
    calor = dias_de_calor(tab)
    linhas = [{"grupo": g, "nome": nome,
               **comparar(tab.loc[calor, col(recorte, g)], tab.loc[calor, f"{col(recorte, g)}__normal"])}
              for g, nome in GRUPOS.items()]
    return pd.DataFrame(linhas)


def heliopolis_x_cidade(tab: pd.DataFrame, grupo: str) -> pd.DataFrame:
    calor = dias_de_calor(tab)
    c = lambda r: col(r, grupo)  # noqa: E731
    return pd.DataFrame([{"recorte": r, "nome": nome,
                          **comparar(tab.loc[calor, c(r)], tab.loc[calor, f"{c(r)}__normal"])}
                         for r, nome in RECORTES.items()])


def dias_depois(tab: pd.DataFrame, recorte: str, grupo: str, maximo: int = 7) -> pd.DataFrame:
    """Para cada dia muito quente, olha o próprio dia e os dias seguintes."""
    c = col(recorte, grupo)
    quentes = np.flatnonzero(tab["muito_quente"].to_numpy())
    linhas = []
    for d in range(maximo + 1):
        idx = quentes + d
        idx = idx[idx < len(tab)]
        linhas.append({"dias_depois": d,
                       **comparar(tab[c].iloc[idx], tab[f"{c}__normal"].iloc[idx])})
    return pd.DataFrame(linhas)


def limiares_mensais(clima: pd.DataFrame) -> pd.Series:
    """P90 da máxima de cada mês em 1991–2020: o 'quente demais' para o mês."""
    ref = clima[clima["ano"].between(*config.CLIMATOLOGIA)]
    return ref.groupby("mes")["tmax"].quantile(config.ONDA_PERCENTIL / 100)


def ondas_de_calor(tab: pd.DataFrame, limiares: pd.Series, recorte: str,
                   grupo: str) -> pd.DataFrame:
    """Ondas (3+ dias acima do P90 do mês) e as internações a mais em cada uma."""
    t = tab.sort_values("data").reset_index(drop=True)
    quente = t["tmax"] > t["data"].dt.month.map(limiares)
    quebra = (~quente) | (t["data"].diff() != pd.Timedelta(days=1))
    seq = quebra.cumsum()
    c = col(recorte, grupo)
    eventos = []
    for _, bloco in t[quente].groupby(seq[quente]):
        if len(bloco) < config.ONDA_DIAS:
            continue
        i0, i1 = bloco.index[0], min(bloco.index[-1] + config.DIAS_DEPOIS, len(t) - 1)
        r = comparar(t.loc[i0:i1, c], t.loc[i0:i1, f"{c}__normal"])
        eventos.append({"inicio": bloco["data"].iat[0], "fim": bloco["data"].iat[-1],
                        "dias": len(bloco), "tmax_pico": bloco["tmax"].max(),
                        "internacoes": int(t.loc[i0:i1, c].sum()),
                        "normal": round(t.loc[i0:i1, f"{c}__normal"].sum(), 1),
                        "a_mais": round(t.loc[i0:i1, c].sum() - t.loc[i0:i1, f"{c}__normal"].sum(), 1),
                        "variacao": r["variacao"]})
    return pd.DataFrame(eventos, columns=["inicio", "fim", "dias", "tmax_pico", "internacoes",
                                          "normal", "a_mais", "variacao"])


# ----------------------------------------------------------------- conclusões
def _f(x: float, casas: int = 0) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _var(x: float) -> str:
    return ("+" if x >= 0 else "−") + _f(abs(x)) + "%"


def gerar_conclusoes(tab: pd.DataFrame, recorte: str, grupo: str, geral: dict,
                     grupos: pd.DataFrame, cidade: pd.DataFrame, depois: pd.DataFrame,
                     ondas: pd.DataFrame) -> list[dict]:
    lugar = "moradores de Heliópolis" if recorte == "heliopolis" else "moradores do resto da cidade"
    n_quentes = int(tab["muito_quente"].sum())
    out = []

    if n_quentes == 0:
        return [{"titulo": "Sem dias muito quentes",
                 "texto": f"Nenhum dia passou de {_f(config.DIA_MUITO_QUENTE)} °C nos anos escolhidos."}]

    out.append({
        "titulo": "A resposta curta",
        "texto": (f"Em {n_quentes} dias a máxima passou de {_f(config.DIA_MUITO_QUENTE)} °C. "
                  f"Nesses dias e nos {config.DIAS_DEPOIS} seguintes, os {lugar} tiveram em média "
                  f"{_f(geral['obs_dia'], 1)} internações de urgência por dia, contra "
                  f"{_f(geral['normal_dia'], 1)} num dia normal da mesma época: "
                  f"**{_var(geral['variacao'])}**. "
                  + ("A diferença é grande demais para ser acaso." if geral["significativo"] else
                     "Com a quantidade de dados disponível, essa diferença ainda pode ser acaso.")),
    })

    sig = grupos[grupos["significativo"] & (grupos["grupo"] != "todas")]
    if len(sig):
        pior = sig.loc[sig["variacao"].idxmax()]
        out.append({"titulo": "O que mais aumenta",
                    "texto": f"O maior aumento foi em “{pior['nome'].lower()}”: "
                             f"{_var(pior['variacao'])} nos dias de calor."})

    h = cidade.set_index("recorte")
    if h["variacao"].notna().all():
        dif = h.loc["heliopolis", "variacao"] - h.loc["resto_sp", "variacao"]
        out.append({"titulo": "Heliópolis sente mais?",
                    "texto": f"Nos dias de calor, as internações subiram {_var(h.loc['heliopolis', 'variacao'])} "
                             f"em Heliópolis e {_var(h.loc['resto_sp', 'variacao'])} no resto da cidade. "
                             + ("Heliópolis foi mais afetada." if dif > 0 else
                                "Heliópolis não foi mais afetada que a média da cidade.")
                             + (" Mas a diferença entre os dois pode ser acaso: Heliópolis tem poucos "
                                "casos por dia." if h.loc["heliopolis", "ic_inf"] < h.loc["resto_sp", "variacao"]
                                < h.loc["heliopolis", "ic_sup"] else "")})

    pico = depois.loc[depois["variacao"].idxmax()]
    dia = int(pico["dias_depois"])
    quando = ("no próprio dia de calor" if dia == 0 else "no dia seguinte ao calor" if dia == 1
              else f"{dia} dias depois do calor")
    out.append({"titulo": "Quando o efeito aparece",
                "texto": f"O pico de internações acontece {quando} ({_var(pico['variacao'])}). "
                         "O efeito é rápido: o alerta precisa sair antes ou no começo da onda de calor."})

    if len(ondas):
        out.append({"titulo": "Ondas de calor",
                    "texto": f"Houve {len(ondas)} ondas de calor. Somando todas, foram cerca de "
                             f"{_f(ondas['a_mais'].sum())} internações a mais do que o normal "
                             f"entre {lugar}."})
    return out


# -------------------------------------------------------------------- tudo
def analisar(clima: pd.DataFrame, internacoes: pd.DataFrame, recorte: str, grupo: str) -> dict:
    tab = montar_tabela(clima, internacoes)
    c = col(recorte, grupo)
    calor = dias_de_calor(tab)
    geral = comparar(tab.loc[calor, c], tab.loc[calor, f"{c}__normal"])
    grupos = por_grupo(tab, recorte)
    cidade = heliopolis_x_cidade(tab, grupo)
    depois = dias_depois(tab, recorte, grupo)
    ondas = ondas_de_calor(tab, limiares_mensais(clima), recorte, grupo)
    return {
        "tabela": tab, "geral": geral, "faixas": por_faixa_de_temperatura(tab, recorte, grupo),
        "grupos": grupos, "cidade": cidade, "depois": depois, "ondas": ondas,
        "conclusoes": gerar_conclusoes(tab, recorte, grupo, geral, grupos, cidade, depois, ondas),
    }
