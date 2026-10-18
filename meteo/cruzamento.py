"""Cruzamento calor × internações.

Perguntas:
  1. Quanto mais quente, mais internações?
  2. Quantos dias depois do calor o efeito aparece?
  3. Nos dias de calor, Heliópolis (e a região do Ipiranga) sofre mais que a cidade?

Como comparar de forma justa
----------------------------
O número de internações muda com o mês (inverno tem mais doenças
respiratórias) e com o dia da semana. Para cada dia calculamos o NORMAL:

    normal = média de internações nos dias SEM calor do mesmo mês e ano
             × peso do dia da semana

e comparamos com o que aconteceu ("+15%" = 15% acima do normal).

Os lugares têm populações muito diferentes, então contar internados não serve
para comparar. Usamos:
  - o AUMENTO de cada lugar em relação ao seu próprio normal (não depende
    da população);
  - a TAXA por 100 mil habitantes (só onde a população é conhecida).

Por que a região do Ipiranga
----------------------------
Heliópolis tem poucas internações por dia, então o acaso pesa muito e os
intervalos de confiança ficam largos. A região (CEPs 042) inclui Heliópolis,
vive o mesmo clima e tem ~10× mais casos. Ela funciona como uma estimativa
mais estável do que acontece em Heliópolis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from meteo import clima as clima_mod
from meteo import config
from meteo.saude import GRUPOS, RECORTES

# Faixas usadas no gráfico "quanto mais quente…", por variável de clima
FAIXAS = {
    "sensacao_max": ([-np.inf, 27, 30, 33, 36, np.inf],
                     ["até 27 °C", "27–30 °C", "30–33 °C", "33–36 °C", "36 °C ou mais"]),
    "tmin": ([-np.inf, 17, 19, 21, np.inf],
             ["até 17 °C", "17–19 °C", "19–21 °C", "21 °C ou mais"]),
}


TEXTO_VAR = {"sensacao_max": "sensação térmica máxima", "tmin": "temperatura mínima"}


def descricao(criterio: str, limiar: float) -> str:
    """Ex.: 'sensação térmica máxima de 35,2 °C ou mais por 3 dias seguidos ou mais'."""
    crit = config.CRITERIOS[criterio]
    texto = f"{TEXTO_VAR[crit['var']]} de {_f(limiar, 1)} °C ou mais"
    if criterio == "onda_calor":
        texto += f" por {config.DIAS_ONDA} dias seguidos ou mais"
    return texto


def col(recorte: str, grupo: str) -> str:
    return f"{recorte}__{grupo}"


def var_do(criterio: str) -> str:
    return config.CRITERIOS[criterio]["var"]


# --------------------------------------------------------------- base diária
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


def _marcas_de_calor(clima: pd.DataFrame, criterio: str) -> pd.DataFrame:
    """Na série diária contínua do clima: dia de calor, janela e defasagens.

    Calculado ANTES de juntar com as internações, porque os anos escolhidos
    podem não ser seguidos (ex.: 2019 e 2022) e a defasagem tem que olhar
    para o dia anterior de verdade, não para a linha anterior da tabela.
    """
    c = clima[["data"]].copy()
    calor = clima[criterio].fillna(False).astype(bool)
    c["dia_calor"] = calor
    for k in range(config.MAX_DEFASAGEM + 1):
        c[f"depois_{k}"] = calor.shift(k, fill_value=False)
    c["janela_calor"] = c[[f"depois_{k}" for k in range(config.DIAS_DEPOIS + 1)]].any(axis=1)
    return c


def montar_tabela(clima: pd.DataFrame, internacoes: pd.DataFrame, criterio: str = "dia_quente",
                  descontar_feriados: bool = True) -> pd.DataFrame:
    var = var_do(criterio)
    base = clima.drop(columns=[c for c in config.CRITERIOS if c in clima])
    base = base.merge(_marcas_de_calor(clima, criterio), on="data")
    tab = internacoes.merge(base, on="data", how="inner").dropna(subset=[var])
    tab = tab.sort_values("data").reset_index(drop=True)
    tab["verao"] = tab["data"].dt.month.isin(config.MESES_QUENTES)
    tab["feriado"] = feriados(tab["data"]) if descontar_feriados else False

    # "Normal" = dias comuns: sem calor e (se pedido) sem feriado
    comum = ~tab["janela_calor"] & ~tab["feriado"]
    util = ~tab["feriado"]
    ano_mes = [tab["data"].dt.year, tab["data"].dt.month]
    semana = tab["data"].dt.dayofweek
    novas = {}
    for r in RECORTES:
        for g in GRUPOS:
            c = col(r, g)
            media = tab[c].where(comum).groupby(ano_mes).transform("mean")
            ref = tab[c].where(comum).groupby(ano_mes).transform("sum")
            media = media.fillna(tab[c].where(util).groupby(ano_mes).transform("mean"))
            # casos usados para estimar o normal do mês (mede a incerteza do normal)
            novas[f"{c}__ref"] = ref.where(ref > 0, tab[c].where(util).groupby(ano_mes).transform("sum"))
            base_util = tab[c].where(util)
            peso = (base_util.groupby(semana).transform("mean") / base_util.mean()
                    if base_util.mean() else 1)
            normal = media * peso
            novas[f"{c}__normal"] = normal
            novas[f"{c}__var"] = 100 * (tab[c] / normal.where(normal > 0) - 1)
    return pd.concat([tab, pd.DataFrame(novas, index=tab.index)], axis=1)


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


# ------------------------------------------ 1. quanto mais quente, mais internações?
def por_faixa(tab: pd.DataFrame, grupo: str, var: str) -> pd.DataFrame:
    """Novembro a março, por faixa de temperatura, nos três recortes."""
    v = tab[tab["verao"]]
    cortes, nomes = FAIXAS[var]
    faixa = pd.cut(v[var], cortes, labels=nomes, right=False)
    linhas = []
    for nome, bloco in v.groupby(faixa, observed=True):
        for r, rotulo in RECORTES.items():
            linhas.append({"faixa": nome, "recorte": r, "lugar": rotulo,
                           **comparar(bloco, col(r, grupo))})
    return pd.DataFrame(linhas)


def correlacao(tab: pd.DataFrame, grupo: str, var: str) -> pd.DataFrame:
    """Spearman: temperatura do dia × % de internações acima do normal (verão)."""
    v = tab[tab["verao"]]
    linhas = []
    for r, rotulo in RECORTES.items():
        d = v[[var, f"{col(r, grupo)}__var"]].dropna()
        if len(d) > 2 and d[var].nunique() > 1:
            rho, p = stats.spearmanr(d[var], d[f"{col(r, grupo)}__var"])
        else:
            rho, p = np.nan, np.nan
        linhas.append({"recorte": r, "lugar": rotulo, "rho": rho, "p_valor": p, "dias": len(d)})
    return pd.DataFrame(linhas)


# ------------------------------------------- 2. quando o efeito aparece?
def defasagem(tab: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """Variação das internações k dias depois de um dia de calor (k = 0…7)."""
    linhas = []
    for k in range(config.MAX_DEFASAGEM + 1):
        bloco = tab[tab[f"depois_{k}"]]
        for r, rotulo in RECORTES.items():
            linhas.append({"dias_depois": k, "recorte": r, "lugar": rotulo,
                           **comparar(bloco, col(r, grupo))})
    return pd.DataFrame(linhas)


# ------------------------------------ arboviroses × temperatura do mês
def arboviroses_mensal(clima: pd.DataFrame, internacoes: pd.DataFrame,
                       recorte: str = "cidade", max_meses: int = 2) -> dict:
    """Internações por arboviroses por mês × temperatura média e chuva de 0 a 2 meses antes.

    O mosquito Aedes se reproduz mais rápido com calor e água parada, e a
    doença aparece semanas depois. Por isso comparamos cada mês com o clima do
    próprio mês e dos meses anteriores (Spearman). Só casos graves internam,
    então isto mostra a ponta do problema; as notificações (SINAN) teriam mais casos.
    """
    c = clima.dropna(subset=["tmedia"]).set_index("data")
    clima_mes = pd.DataFrame({"temp_media": c["tmedia"].resample("MS").mean(),
                              "chuva": c["chuva"].resample("MS").sum()})
    casos = (internacoes.set_index("data")[col(recorte, "arboviroses")]
             .resample("MS").sum().rename("internacoes"))
    mensal = casos.to_frame().join(clima_mes, how="left")
    for k in range(1, max_meses + 1):
        anterior = clima_mes.shift(k)
        mensal[f"temp_media_{k}m"] = anterior["temp_media"].reindex(mensal.index)
        mensal[f"chuva_{k}m"] = anterior["chuva"].reindex(mensal.index)
    linhas = []
    for k in range(max_meses + 1):
        sufixo = "" if k == 0 else f"_{k}m"
        for var, nome in (("temp_media", "Temperatura média"), ("chuva", "Chuva acumulada")):
            d = mensal[["internacoes", var + sufixo]].dropna()
            if len(d) > 3 and d["internacoes"].nunique() > 1:
                rho, p = stats.spearmanr(d["internacoes"], d[var + sufixo])
            else:
                rho, p = np.nan, np.nan
            linhas.append({"meses_antes": k, "variavel": nome, "rho": rho, "p_valor": p,
                           "meses": len(d)})
    return {"mensal": mensal.reset_index(names="mes"), "correlacao": pd.DataFrame(linhas)}


# ------------------------------- 3. Heliópolis e região × cidade em dias de calor
def _razao_de_razoes(a: pd.Series, b: pd.Series) -> dict:
    """O aumento de A é maior que o de B? (razão entre as duas razões, IC 95%)."""
    if min(a["obs"], b["obs"], a["normal"], b["normal"]) > 0:
        rr = (a["obs"] / a["normal"]) / (b["obs"] / b["normal"])
        erro = 1.96 * np.sqrt(a["var_log"] + b["var_log"])
        d = {"vezes": rr, "ic_inf": rr * np.exp(-erro), "ic_sup": rr * np.exp(erro)}
        d["significativo"] = not (d["ic_inf"] <= 1 <= d["ic_sup"])
        return d
    return {"vezes": np.nan, "ic_inf": np.nan, "ic_sup": np.nan, "significativo": False}


def comparar_recortes(tab: pd.DataFrame, grupo: str, pop_heliopolis: int) -> dict:
    j = tab["janela_calor"]
    pops = {"heliopolis": pop_heliopolis, "regiao": None, "cidade": config.POP_SP}
    linhas = []
    for r, rotulo in RECORTES.items():
        res = comparar(tab.loc[j], col(r, grupo))
        fator = 100_000 / pops[r] if pops.get(r) else np.nan
        linhas.append({"recorte": r, "lugar": rotulo, **res,
                       "taxa_normal": res["normal_dia"] * fator,
                       "taxa_calor": res["obs_dia"] * fator})
    df = pd.DataFrame(linhas).set_index("recorte")
    # Heliópolis está dentro da cidade (0,5% da população) e a região também
    # (~5%): a sobreposição é pequena e o teste trata os dois como independentes.
    dif = {r: _razao_de_razoes(df.loc[r], df.loc["cidade"]) for r in ("heliopolis", "regiao")}
    return {"tabela": df.reset_index(), "diferenca": dif}


# ----------------------------------------------------------------- conclusões
def _f(x: float, casas: int = 0) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _mudou(x: float) -> str:
    """'subiram 12%' / 'caíram 5%' / 'ficaram praticamente iguais'."""
    if pd.isna(x) or abs(x) < 0.5:
        return "ficaram praticamente iguais"
    return f"{'subiram' if x > 0 else 'caíram'} {_f(abs(x))}%"


def _confiavel(linha: pd.Series) -> str:
    return "" if linha["significativo"] else " (pode ser acaso)"


def gerar_conclusoes(tab, grupo, criterio, limiar, faixas, corr, lags, comp) -> list[dict]:
    out, nome = [], GRUPOS[grupo].lower()
    crit = config.CRITERIOS[criterio]
    c = corr.set_index("recorte")
    sem_efeito = True

    # 1. Mais calor, mais internações?
    cid = faixas[faixas["recorte"] == "cidade"].reset_index(drop=True)
    reg = faixas[faixas["recorte"] == "regiao"].reset_index(drop=True)
    hel = faixas[faixas["recorte"] == "heliopolis"].reset_index(drop=True)
    if len(cid) >= 2 and not pd.isna(c.loc["cidade", "rho"]):
        cc, topo = c.loc["cidade"], cid.iloc[-1]
        if cc["p_valor"] < .05 and cc["rho"] > 0 and topo["significativo"] and topo["variacao"] > 0:
            resposta, sem_efeito = "Sim, na cidade como um todo.", False
        elif cc["p_valor"] < .05 and cc["rho"] < 0:
            resposta = "Não. Nos dias mais quentes houve até um pouco MENOS internações."
        else:
            resposta = "Com estes dados, não apareceu aumento claro."
        out.append({
            "titulo": "Mais calor, mais internações?",
            "texto": (f"{resposta} No verão, nos dias com {TEXTO_VAR[crit['var']]} de {topo['faixa']}, as "
                      f"internações ({nome}) {_mudou(topo['variacao'])} em relação ao normal na "
                      f"cidade{_confiavel(topo)}, {_mudou(reg['variacao'].iloc[-1])} na região do "
                      f"Ipiranga{_confiavel(reg.iloc[-1])} e {_mudou(hel['variacao'].iloc[-1])} em "
                      f"Heliópolis{_confiavel(hel.iloc[-1])}."),
        })

    # 2. Heliópolis e região nos dias de calor
    t = comp["tabela"].set_index("recorte")
    h, r, ci = t.loc["heliopolis"], t.loc["regiao"], t.loc["cidade"]
    if not pd.isna(ci["variacao"]):
        if h["significativo"]:
            leitura = "Em Heliópolis a mudança já é grande o bastante para não ser acaso."
        elif r["significativo"]:
            leitura = ("Heliópolis sozinha tem poucos casos para afirmar, mas na região do "
                       "Ipiranga, que inclui Heliópolis e vive o mesmo clima, a mudança não é acaso. "
                       "É o indício mais forte do que acontece em Heliópolis.")
        else:
            leitura = ("Nem em Heliópolis nem na região a mudança foi grande o bastante para "
                       "descartar o acaso.")
        dr = comp["diferenca"]["regiao"]
        if dr["significativo"]:
            leitura += (" A região reagiu " + ("mais" if dr["vezes"] > 1 else "menos") +
                        " que a cidade, e o teste indica que a diferença não é acaso.")
        if any(x["significativo"] and x["variacao"] > 0 for x in (h, r, ci)):
            sem_efeito = False
        out.append({
            "titulo": "E em Heliópolis?",
            "texto": (f"Nos dias de calor ({descricao(criterio, limiar)}) e nos "
                      f"{config.DIAS_DEPOIS} dias seguintes, as "
                      f"internações {_mudou(h['variacao'])} em Heliópolis, {_mudou(r['variacao'])} "
                      f"na região do Ipiranga e {_mudou(ci['variacao'])} na cidade. {leitura}"),
        })

    # 3. Quando aparece
    ref = "regiao" if lags.loc[lags["recorte"] == "regiao", "obs"].sum() > 0 else "cidade"
    lr = lags[(lags["recorte"] == ref) & lags["significativo"] & (lags["variacao"] > 0)]
    if len(lr):
        pico = lr.loc[lr["variacao"].idxmax()]
        k = int(pico["dias_depois"])
        quando = "no próprio dia" if k == 0 else f"{k} dia{'s' if k > 1 else ''} depois"
        out.append({
            "titulo": "Quando o efeito aparece?",
            "texto": (f"Na {RECORTES[ref].lower() if ref == 'cidade' else 'região do Ipiranga'}, "
                      f"o maior aumento confiável aparece {quando} do calor "
                      f"({_f(pico['variacao'])}% acima do normal). Isso mostra por quanto tempo "
                      "vale manter o alerta depois de um dia quente."),
        })

    # 4. Taxa por 100 mil
    if not pd.isna(h["taxa_normal"]):
        out.append({
            "titulo": "Proporcionalmente, quem tem mais internados?",
            "texto": (f"Heliópolis tem {_f(h['taxa_normal'], 1)} internações por 100 mil "
                      f"habitantes num dia normal e {_f(h['taxa_calor'], 1)} nos dias de calor; a "
                      f"cidade, {_f(ci['taxa_normal'], 1)} e {_f(ci['taxa_calor'], 1)}. "
                      + ("Heliópolis interna mais, com ou sem calor. "
                         if h["taxa_normal"] > ci["taxa_normal"] else "")
                      + "Parte disso é porque quase todos em Heliópolis dependem do SUS, e o "
                        "número depende da população usada (ajustável na barra lateral)."),
        })

    # 5. Se o calor não apareceu, explicar por quê
    if sem_efeito:
        out.append({
            "titulo": "Por que o calor pode não aparecer nas internações?",
            "texto": ("Quem passa mal com o calor costuma ser atendido no pronto-socorro e liberado, "
                      "sem internar (e o SIH só registra internações). O número de internações também "
                      "depende de haver leito vago. Estudos em São Paulo encontram o efeito do calor "
                      "mais claramente nas MORTES: experimente o grupo \"Internações que terminaram "
                      "em morte\" e o critério \"Onda de calor\"."),
        })
    return out


# -------------------------------------------------------------------- tudo
def analisar(clima: pd.DataFrame, internacoes: pd.DataFrame, grupo: str,
             criterio: str = "dia_quente", pop_heliopolis: int = config.POP_HELIOPOLIS,
             descontar_feriados: bool = True, limiares: dict | None = None) -> dict:
    """Roda todas as análises. `limiares` fixa a régua de calor (ver clima.marcar_calor)."""
    var = var_do(criterio)
    limiar = (limiares or clima_mod.limiares(clima))[var]
    completa = montar_tabela(clima, internacoes, criterio, descontar_feriados)
    tab = completa[~completa["feriado"]].reset_index(drop=True)   # análises só em dias comuns
    faixas = por_faixa(tab, grupo, var)
    corr = correlacao(tab, grupo, var)
    lags = defasagem(tab, grupo)
    comp = comparar_recortes(tab, grupo, pop_heliopolis)
    return {"tabela": tab, "completa": completa, "limiar": limiar, "var": var,
            "dias_calor": int(tab["dia_calor"].sum()),
            "feriados_removidos": int(completa["feriado"].sum()),
            "calor_em_feriado": int((completa["janela_calor"] & completa["feriado"]).sum()),
            "faixas": faixas, "correlacao": corr, "defasagem": lags, "comparacao": comp,
            "conclusoes": gerar_conclusoes(tab, grupo, criterio, limiar, faixas, corr, lags, comp)}
