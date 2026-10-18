"""Cruzamento sensação térmica × internações.

Duas perguntas:
  1. Quanto maior a sensação térmica, mais internações?
  2. Nos dias de calor, Heliópolis tem mais internados que o resto de SP?

Como comparar de forma justa
----------------------------
O número de internações muda com o mês (inverno tem mais doenças
respiratórias) e com o dia da semana. Para cada dia calculamos o NORMAL:

    normal = média de internações nos dias SEM calor do mesmo mês e ano
             × peso do dia da semana

e comparamos com o que aconteceu ("+15%" = 15% acima do normal).

Heliópolis tem ~50 vezes menos gente que o resto da cidade, então contar
internados não serve para comparar os dois. Usamos:
  - o AUMENTO de cada lugar em relação ao seu próprio normal (não depende
    da população);
  - a TAXA por 100 mil habitantes (depende da população informada).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from meteo import config
from meteo.saude import GRUPOS, RECORTES

VAR = "sensacao_max"
FAIXAS = [-np.inf, 27, 30, 33, 36, np.inf]
NOMES_FAIXAS = ["até 27 °C", "27–30 °C", "30–33 °C", "33–36 °C", "36 °C ou mais"]


def col(recorte: str, grupo: str) -> str:
    return f"{recorte}__{grupo}"


# --------------------------------------------------------------- base diária
def limiar_calor(tab: pd.DataFrame) -> float:
    return float(np.nanpercentile(tab[VAR], config.PERCENTIL_DIA_CALOR))


def dias_de_calor(tab: pd.DataFrame) -> pd.Series:
    """Dias de calor E os DIAS_DEPOIS dias seguintes (o efeito demora um pouco)."""
    marca = tab["dia_calor"].copy()
    for d in range(1, config.DIAS_DEPOIS + 1):
        marca |= tab["dia_calor"].shift(d, fill_value=False)
    return marca


def feriados(datas: pd.Series) -> pd.Series:
    """True em feriados, Carnaval e no período de Natal/Ano Novo.

    Nesses dias muita gente viaja e os hospitais internam menos. Como os dias
    mais quentes do ano caem justamente nessa época, sem descontar os feriados
    o calor pareceria DIMINUIR as internações.
    """
    from dateutil.easter import easter

    fixos = {(1, 1), (1, 25), (4, 21), (5, 1), (7, 9), (9, 7), (10, 12), (11, 2),
             (11, 15), (11, 20), (12, 25)}           # nacionais + SP (25/01 e 09/07)
    marca = pd.Series([(d.month, d.day) in fixos for d in datas], index=datas.index)
    marca |= (datas.dt.month == 12) & (datas.dt.day >= 24)          # Natal → Ano Novo
    marca |= (datas.dt.month == 1) & (datas.dt.day <= 1)
    for ano in datas.dt.year.unique():
        pascoa = pd.Timestamp(easter(int(ano)))
        moveis = list(pd.date_range(pascoa - pd.Timedelta(days=50),    # sábado de Carnaval
                                    pascoa - pd.Timedelta(days=46)))   # quarta de Cinzas
        moveis += [pascoa - pd.Timedelta(days=2), pascoa + pd.Timedelta(days=60)]  # Sexta Santa, Corpus Christi
        marca |= datas.isin(moveis)
    return marca


def montar_tabela(clima: pd.DataFrame, internacoes: pd.DataFrame,
                  descontar_feriados: bool = True) -> pd.DataFrame:
    tab = internacoes.merge(clima, on="data", how="inner").dropna(subset=[VAR])
    tab = tab.sort_values("data").reset_index(drop=True)
    tab["dia_calor"] = tab[VAR] >= limiar_calor(tab)
    tab["janela_calor"] = dias_de_calor(tab)
    tab["verao"] = tab["data"].dt.month.isin(config.MESES_QUENTES)
    tab["feriado"] = feriados(tab["data"]) if descontar_feriados else False

    # "Normal" = dias comuns: sem calor e (se pedido) sem feriado
    comum = ~tab["janela_calor"] & ~tab["feriado"]
    util = ~tab["feriado"]
    ano_mes = [tab["data"].dt.year, tab["data"].dt.month]
    semana = tab["data"].dt.dayofweek
    for r in RECORTES:
        for g in GRUPOS:
            c = col(r, g)
            media = tab[c].where(comum).groupby(ano_mes).transform("mean")
            ref = tab[c].where(comum).groupby(ano_mes).transform("sum")
            media = media.fillna(tab[c].where(util).groupby(ano_mes).transform("mean"))
            # casos usados para estimar o normal do mês (mede a incerteza do normal)
            tab[f"{c}__ref"] = ref.where(ref > 0, tab[c].where(util).groupby(ano_mes).transform("sum"))
            base = tab[c].where(util)
            peso = (base.groupby(semana).transform("mean") / base.mean()) if base.mean() else 1
            tab[f"{c}__normal"] = media * peso
            tab[f"{c}__var"] = 100 * (tab[c] / tab[f"{c}__normal"].where(tab[f"{c}__normal"] > 0) - 1)
    return tab


def _incerteza_normal(bloco: pd.DataFrame, c: str) -> float:
    """Variância relativa da soma dos 'normais' do bloco.

    O normal de um mês é uma média estimada com C casos, então tem erro
    relativo ~ 1/C. Dias do mesmo mês compartilham o mesmo erro.
    """
    mes = [bloco["data"].dt.year, bloco["data"].dt.month]
    soma_mes = bloco.groupby(mes)[f"{c}__normal"].sum()
    casos = bloco.groupby(mes)[f"{c}__ref"].first()
    total = soma_mes.sum()
    return float((soma_mes ** 2 / casos.clip(lower=1)).sum() / total ** 2) if total > 0 else np.nan


def comparar(bloco: pd.DataFrame, c: str) -> dict:
    """Observado × normal nos dias do bloco, com intervalo de 95%.

    O intervalo considera a variação natural dos casos (Poisson) E a incerteza
    do próprio normal, que é grande quando há poucos casos (Heliópolis).
    """
    o, n, dias = float(bloco[c].sum()), float(bloco[f"{c}__normal"].sum()), len(bloco)
    base = {"dias": dias, "obs": o, "normal": n, "obs_dia": o / max(dias, 1),
            "normal_dia": n / max(dias, 1), "var_log": np.nan}
    if n <= 0 or o <= 0:
        return base | {"variacao": np.nan, "ic_inf": np.nan, "ic_sup": np.nan,
                       "significativo": False}
    var_log = 1 / o + _incerteza_normal(bloco, c)
    razao, erro = o / n, 1.96 * np.sqrt(var_log)
    lo, hi = razao * np.exp(-erro), razao * np.exp(erro)
    return base | {"var_log": var_log, "variacao": 100 * (razao - 1), "ic_inf": 100 * (lo - 1),
                   "ic_sup": 100 * (hi - 1), "significativo": not (lo <= 1 <= hi)}


# ------------------------------------- 1. sensação térmica × internações
def por_faixa(tab: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """Novembro a março, por faixa de sensação térmica, nos dois lugares."""
    v = tab[tab["verao"]]
    faixa = pd.cut(v[VAR], FAIXAS, labels=NOMES_FAIXAS, right=False)
    linhas = []
    for nome, bloco in v.groupby(faixa, observed=True):
        for r, rotulo in RECORTES.items():
            c = col(r, grupo)
            linhas.append({"faixa": nome, "recorte": r, "lugar": rotulo, **comparar(bloco, c)})
    return pd.DataFrame(linhas)


def correlacao(tab: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """Spearman: sensação térmica do dia × % de internações acima do normal (verão)."""
    v = tab[tab["verao"]]
    linhas = []
    for r, rotulo in RECORTES.items():
        d = v[[VAR, f"{col(r, grupo)}__var"]].dropna()
        rho, p = stats.spearmanr(d[VAR], d[f"{col(r, grupo)}__var"])
        linhas.append({"recorte": r, "lugar": rotulo, "rho": rho, "p_valor": p, "dias": len(d)})
    return pd.DataFrame(linhas)


# ------------------------------------ 2. Heliópolis × resto em dias de calor
def heliopolis_x_resto(tab: pd.DataFrame, grupo: str, pop_heliopolis: int) -> dict:
    j = tab["janela_calor"]
    pops = {"heliopolis": pop_heliopolis, "resto_sp": config.POP_SP - pop_heliopolis}
    linhas = []
    for r, rotulo in RECORTES.items():
        c = col(r, grupo)
        res = comparar(tab.loc[j], c)
        fator = 100_000 / pops[r]
        linhas.append({"recorte": r, "lugar": rotulo, **res,
                       "taxa_normal": res["normal_dia"] * fator,
                       "taxa_calor": res["obs_dia"] * fator})
    df = pd.DataFrame(linhas).set_index("recorte")

    # O aumento de Heliópolis é maior que o do resto? (razão entre as duas razões)
    h, rs = df.loc["heliopolis"], df.loc["resto_sp"]
    if min(h["obs"], rs["obs"], h["normal"], rs["normal"]) > 0:
        rr = (h["obs"] / h["normal"]) / (rs["obs"] / rs["normal"])
        erro = 1.96 * np.sqrt(h["var_log"] + rs["var_log"])
        dif = {"vezes": rr, "ic_inf": rr * np.exp(-erro), "ic_sup": rr * np.exp(erro)}
        dif["significativo"] = not (dif["ic_inf"] <= 1 <= dif["ic_sup"])
    else:
        dif = {"vezes": np.nan, "ic_inf": np.nan, "ic_sup": np.nan, "significativo": False}
    return {"tabela": df.reset_index(), "diferenca": dif}


# ----------------------------------------------------------------- conclusões
def _f(x: float, casas: int = 0) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _var(x: float) -> str:
    if pd.isna(x):
        return "–"
    if abs(x) < 0.5:
        return "0%"
    return ("+" if x > 0 else "−") + _f(abs(x)) + "%"


def _mudou(x: float) -> str:
    """'subiram 12%' / 'caíram 5%' / 'ficaram iguais'."""
    if pd.isna(x) or abs(x) < 0.5:
        return "ficaram praticamente iguais"
    return f"{'subiram' if x > 0 else 'caíram'} {_f(abs(x))}%"


def gerar_conclusoes(tab, grupo, faixas, corr, comp) -> list[dict]:
    out, nome = [], GRUPOS[grupo].lower()
    limiar = tab.loc[tab["dia_calor"], VAR].min() if tab["dia_calor"].any() else np.nan
    c = corr.set_index("recorte")
    sem_efeito = True

    # 1. Mais calor, mais internações?
    rs = faixas[faixas["recorte"] == "resto_sp"].reset_index(drop=True)
    hl = faixas[faixas["recorte"] == "heliopolis"].reset_index(drop=True)
    if len(rs) >= 2:
        cr = c.loc["resto_sp"]
        topo = rs.iloc[-1]
        if cr["p_valor"] < .05 and cr["rho"] > 0 and topo["significativo"] and topo["variacao"] > 0:
            resposta, sem_efeito = "Sim.", False
        elif cr["p_valor"] < .05 and cr["rho"] < 0:
            resposta = "Não. Nos dias mais quentes houve até um pouco MENOS internações."
        else:
            resposta = "Com estes dados, não apareceu aumento."
        out.append({
            "titulo": "Mais calor, mais internações?",
            "texto": (f"{resposta} No verão, nos dias com sensação térmica {topo['faixa']}, as "
                      f"internações ({nome}) {_mudou(topo['variacao'])} em relação ao normal no resto "
                      f"da cidade e {_mudou(hl['variacao'].iloc[-1])} em Heliópolis. Correlação entre "
                      f"sensação térmica e internações: ρ = {_f(cr['rho'], 2)} no resto de SP e "
                      f"ρ = {_f(c.loc['heliopolis', 'rho'], 2)} em Heliópolis "
                      "(0 = nenhuma relação; 1 = relação perfeita)."),
        })

    # 2. Heliópolis × resto
    t = comp["tabela"].set_index("recorte")
    h, r = t.loc["heliopolis"], t.loc["resto_sp"]
    dif = comp["diferenca"]
    if not pd.isna(dif["vezes"]):
        if not h["significativo"] and not r["significativo"]:
            veredito = ("Nos dois lugares a mudança foi pequena demais para descartar o acaso, "
                        "então não dá para dizer que Heliópolis é mais afetada.")
        elif dif["significativo"]:
            veredito = ("A mudança em Heliópolis foi maior que no resto da cidade."
                        if dif["vezes"] > 1 else
                        "A mudança em Heliópolis foi menor que no resto da cidade.")
        else:
            veredito = ("A diferença entre os dois lugares pode ser acaso (Heliópolis tem poucos "
                        "casos por dia).")
        out.append({
            "titulo": "Heliópolis é mais afetada nos dias de calor?",
            "texto": (f"Nos dias de calor (sensação térmica ≥ {_f(limiar, 1)} °C) e nos "
                      f"{config.DIAS_DEPOIS} seguintes, as internações {_mudou(h['variacao'])} em "
                      f"Heliópolis e {_mudou(r['variacao'])} no resto de SP. {veredito}"),
        })

    # 3. Taxa por 100 mil
    out.append({
        "titulo": "Proporcionalmente, quem tem mais internados?",
        "texto": (f"Heliópolis tem {_f(h['taxa_normal'], 1)} internações de urgência por 100 mil "
                  f"habitantes num dia normal e {_f(h['taxa_calor'], 1)} nos dias de calor; o resto "
                  f"da cidade, {_f(r['taxa_normal'], 1)} e {_f(r['taxa_calor'], 1)}. "
                  + ("Heliópolis interna mais, com ou sem calor. " if h["taxa_normal"] > r["taxa_normal"]
                     else "")
                  + "Parte disso é porque quase todos em Heliópolis dependem do SUS, e o número "
                    "depende da população usada (ajustável na barra lateral)."),
    })

    # 4. Se o calor não apareceu, explicar por quê
    if sem_efeito:
        out.append({
            "titulo": "Por que o calor pode não aparecer nas internações?",
            "texto": ("Quem passa mal com o calor costuma ser atendido no pronto-socorro e liberado, "
                      "sem internar (e o SIH só registra internações). O número de internações também "
                      "depende de haver leito vago. Estudos em São Paulo encontram o efeito do calor "
                      "mais claramente nas MORTES. Um próximo passo é olhar as mortes no hospital e "
                      "os óbitos do SIM."),
        })
    return out


# -------------------------------------------------------------------- tudo
def analisar(clima: pd.DataFrame, internacoes: pd.DataFrame, grupo: str,
             pop_heliopolis: int = config.POP_HELIOPOLIS,
             descontar_feriados: bool = True) -> dict:
    completa = montar_tabela(clima, internacoes, descontar_feriados)
    tab = completa[~completa["feriado"]].reset_index(drop=True)   # análises só em dias comuns
    faixas = por_faixa(tab, grupo)
    corr = correlacao(tab, grupo)
    comp = heliopolis_x_resto(tab, grupo, pop_heliopolis)
    return {"tabela": tab, "completa": completa, "limiar": limiar_calor(completa),
            "feriados_removidos": int(completa["feriado"].sum()),
            "calor_em_feriado": int((completa["janela_calor"] & completa["feriado"]).sum()),
            "faixas": faixas, "correlacao": corr, "comparacao": comp,
            "conclusoes": gerar_conclusoes(tab, grupo, faixas, corr, comp)}
