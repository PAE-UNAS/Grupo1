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
# ↑ Docstring do módulo: explica o arquivo inteiro. Não executa nada.

# Permite dicas de tipo modernas (ex.: "dict | None") em qualquer versão do Python 3.
from __future__ import annotations

import numpy as np        # NumPy: contas numéricas (raiz quadrada, exponencial, infinito…).
import pandas as pd       # Pandas: tabelas (DataFrames).
from scipy import stats   # SciPy: estatística. Daqui usamos a correlação de Spearman.

# Importa nosso módulo de clima com outro nome ("clima_mod"), porque várias funções deste
# arquivo têm um PARÂMETRO chamado "clima" e os nomes iguais causariam confusão.
from meteo import clima as clima_mod
from meteo import config  # Configurações do projeto.
# Do módulo de saúde, importa dois dicionários:
#   GRUPOS   → tipos de internação (todas, respiratórias, coração…)
#   RECORTES → lugares (heliopolis, regiao, cidade)
from meteo.saude import GRUPOS, RECORTES

# Faixas usadas no gráfico "quanto mais quente…", por variável de clima
# Para cada variável: (lista de cortes, lista de nomes das faixas).
# -np.inf e np.inf são "menos infinito" e "mais infinito": a primeira e a última faixa não têm limite.
FAIXAS = {
    "sensacao_max": ([-np.inf, 27, 30, 33, 36, np.inf],                         # cortes em °C
                     ["até 27 °C", "27–30 °C", "30–33 °C", "33–36 °C", "36 °C ou mais"]),  # nomes
    "tmin": ([-np.inf, 17, 19, 21, np.inf],
             ["até 17 °C", "17–19 °C", "19–21 °C", "21 °C ou mais"]),
}


# Como escrever o nome de cada variável nos textos do painel.
TEXTO_VAR = {"sensacao_max": "sensação térmica máxima", "tmin": "temperatura mínima"}


def descricao(criterio: str, limiar: float) -> str:   # Recebe o critério e o limiar; devolve uma frase.
    """Ex.: 'sensação térmica máxima de 35,2 °C ou mais por 3 dias seguidos ou mais'."""
    crit = config.CRITERIOS[criterio]   # Dicionário com as informações do critério escolhido.
    # Monta a frase base, ex.: "sensação térmica máxima de 33,5 °C ou mais".
    # _f(limiar, 1) formata com 1 casa decimal e vírgula (função definida mais abaixo).
    texto = f"{TEXTO_VAR[crit['var']]} de {_f(limiar, 1)} °C ou mais"
    if criterio == "onda_calor":        # Se o critério for onda de calor…
        texto += f" por {config.DIAS_ONDA} dias seguidos ou mais"   # …acrescenta a duração ("+=" = concatena).
    return texto


# Define col(): recebe o lugar e o grupo (textos) e devolve o nome da coluna (texto).
def col(recorte: str, grupo: str) -> str:
    # Monta o nome de uma coluna da tabela de internações, juntando lugar e grupo com "__".
    # Ex.: col("heliopolis", "respiratorio") → "heliopolis__respiratorio".
    return f"{recorte}__{grupo}"


# Define var_do(): recebe o código do critério e devolve o nome da variável de clima.
def var_do(criterio: str) -> str:
    # Diz qual variável de clima o critério usa. Ex.: "dia_quente" → "sensacao_max"; "noite_quente" → "tmin".
    return config.CRITERIOS[criterio]["var"]


# --------------------------------------------------------------- base diária
def feriados(datas: pd.Series) -> pd.Series:   # Recebe uma coluna de datas; devolve uma coluna True/False.
    """True em feriados, Carnaval e no período de Natal/Ano Novo.

    Nesses dias muita gente viaja e os hospitais internam menos. Como os dias
    mais quentes do ano caem justamente nessa época, sem descontar os feriados
    o calor pareceria DIMINUIR as internações.
    """
    # Importa aqui dentro (só quando a função é usada) a função que calcula a data da Páscoa.
    from dateutil.easter import easter

    # Conjunto de feriados de data fixa, como pares (mês, dia).
    fixos = {(1, 1), (1, 25), (4, 21), (5, 1), (7, 9), (9, 7), (10, 12), (11, 2),
             (11, 15), (11, 20), (12, 25)}           # nacionais + SP (25/01 e 09/07)
    # Para cada data d, verifica se (mês, dia) está no conjunto de feriados fixos → True/False.
    # index=datas.index mantém o mesmo "rótulo de linha" das datas recebidas.
    marca = pd.Series([(d.month, d.day) in fixos for d in datas], index=datas.index)
    # "|=" = "ou igual": a marca fica True se JÁ era True OU se a nova condição for True.
    # Aqui: dezembro, do dia 24 em diante (Natal até o Réveillon).
    marca |= (datas.dt.month == 12) & (datas.dt.day >= 24)          # Natal → Ano Novo
    # E também 1º de janeiro.
    marca |= (datas.dt.month == 1) & (datas.dt.day <= 1)
    for ano in datas.dt.year.unique():   # Para cada ano diferente que aparece nas datas…
        # Calcula a Páscoa daquele ano e converte para o tipo de data do pandas.
        pascoa = pd.Timestamp(easter(int(ano)))
        # Carnaval: do sábado (50 dias antes da Páscoa) até a Quarta-feira de Cinzas (46 dias antes).
        # pd.date_range cria todos os dias desse intervalo; list(...) transforma em lista.
        moveis = list(pd.date_range(pascoa - pd.Timedelta(days=50),    # sábado de Carnaval
                                    pascoa - pd.Timedelta(days=46)))   # quarta de Cinzas
        # Acrescenta à lista a Sexta-feira Santa (2 dias antes) e Corpus Christi (60 dias depois).
        moveis += [pascoa - pd.Timedelta(days=2), pascoa + pd.Timedelta(days=60)]  # Sexta Santa, Corpus Christi
        marca |= datas.isin(moveis)      # Marca True as datas que estão na lista de feriados móveis.
    return marca


# O "_" no começo indica função de uso interno deste arquivo.
def _marcas_de_calor(clima: pd.DataFrame, criterio: str) -> pd.DataFrame:
    """Na série diária contínua do clima: dia de calor, janela e defasagens.

    Calculado ANTES de juntar com as internações, porque os anos escolhidos
    podem não ser seguidos (ex.: 2019 e 2022) e a defasagem tem que olhar
    para o dia anterior de verdade, não para a linha anterior da tabela.
    """
    c = clima[["data"]].copy()          # Nova tabela só com a coluna de datas (os [[ ]] mantêm formato de tabela).
    # Coluna do critério (ex.: "dia_quente"). fillna(False) troca vazios por False;
    # astype(bool) garante que seja True/False.
    calor = clima[criterio].fillna(False).astype(bool)
    c["dia_calor"] = calor              # Guarda: este dia é de calor?
    for k in range(config.MAX_DEFASAGEM + 1):   # k = 0, 1, 2… até MAX_DEFASAGEM (ex.: 7).
        # shift(k) "empurra" a série k dias para frente. Assim, depois_k é True em um dia
        # se houve calor k dias ANTES dele. fill_value=False preenche o começo, que fica sem dado.
        c[f"depois_{k}"] = calor.shift(k, fill_value=False)
    # janela_calor = o próprio dia de calor OU até DIAS_DEPOIS (ex.: 2) dias depois dele.
    # .any(axis=1) = True se QUALQUER uma das colunas da linha for True.
    c["janela_calor"] = c[[f"depois_{k}" for k in range(config.DIAS_DEPOIS + 1)]].any(axis=1)
    return c


# Define montar_tabela(): recebe clima e internações (e, opcionalmente, critério e se desconta
# feriados) e devolve a tabela diária completa.
def montar_tabela(clima: pd.DataFrame, internacoes: pd.DataFrame, criterio: str = "dia_quente",
                  descontar_feriados: bool = True) -> pd.DataFrame:
    # Monta a tabela principal: 1 linha por dia, com clima + internações + o "normal" de cada série.
    var = var_do(criterio)              # Variável de clima do critério (ex.: "sensacao_max").
    # Tira do clima as colunas antigas de critério (dia_quente etc.), que serão recalculadas.
    # [c for c in ... if c in clima] = só as que existem na tabela (evita erro).
    base = clima.drop(columns=[c for c in config.CRITERIOS if c in clima])
    # merge = juntar tabelas pela coluna "data" (como o PROCV do Excel). Acrescenta as marcas de calor.
    base = base.merge(_marcas_de_calor(clima, criterio), on="data")
    # Junta internações + clima. how="inner" mantém só os dias que existem nas DUAS tabelas.
    # dropna(subset=[var]) remove dias sem a variável de clima.
    tab = internacoes.merge(base, on="data", how="inner").dropna(subset=[var])
    tab = tab.sort_values("data").reset_index(drop=True)   # Ordena por data e renumera as linhas.
    # Coluna True/False: o dia está nos meses quentes (novembro a março)?
    tab["verao"] = tab["data"].dt.month.isin(config.MESES_QUENTES)
    # Coluna True/False: é feriado? Se o usuário desligou o desconto, todos ficam False.
    tab["feriado"] = feriados(tab["data"]) if descontar_feriados else False

    # "Normal" = dias comuns: sem calor e (se pedido) sem feriado
    # "~" inverte True/False. comum = NÃO está na janela de calor E NÃO é feriado.
    comum = ~tab["janela_calor"] & ~tab["feriado"]
    util = ~tab["feriado"]              # util = qualquer dia que não seja feriado.
    # Duas chaves de agrupamento: ano e mês (para calcular a média de cada mês de cada ano).
    ano_mes = [tab["data"].dt.year, tab["data"].dt.month]
    semana = tab["data"].dt.dayofweek   # Dia da semana: 0 = segunda … 6 = domingo.
    novas = {}                          # Dicionário onde vamos guardar as colunas novas antes de juntar.
    for r in RECORTES:                  # Para cada lugar (heliopolis, regiao, cidade)…
        for g in GRUPOS:                # …e cada tipo de internação…
            c = col(r, g)               # …nome da coluna, ex.: "regiao__todas".
            # .where(comum) apaga os dias que NÃO são comuns (vira vazio). Depois:
            # groupby(ano_mes).transform("mean") = média do mês, repetida em todas as linhas daquele mês.
            media = tab[c].where(comum).groupby(ano_mes).transform("mean")
            # Mesma ideia, mas a SOMA de casos dos dias comuns do mês (quantos casos sustentam a média).
            ref = tab[c].where(comum).groupby(ano_mes).transform("sum")
            # Se um mês não teve nenhum dia comum, a média fica vazia; preenche (fillna) com a
            # média de todos os dias não-feriado desse mês.
            media = media.fillna(tab[c].where(util).groupby(ano_mes).transform("mean"))
            # casos usados para estimar o normal do mês (mede a incerteza do normal)
            # ref.where(ref > 0, outra coisa) = mantém ref onde é maior que 0; senão usa a soma dos dias úteis.
            novas[f"{c}__ref"] = ref.where(ref > 0, tab[c].where(util).groupby(ano_mes).transform("sum"))
            base_util = tab[c].where(util)   # A série só com dias não-feriado.
            # Peso do dia da semana = média daquele dia da semana ÷ média geral.
            # Ex.: se segundas têm 10% mais internações, o peso da segunda é 1,10.
            # "if base_util.mean() else 1": se a média geral for 0 (sem casos), usa peso 1 (evita dividir por zero).
            peso = (base_util.groupby(semana).transform("mean") / base_util.mean()
                    if base_util.mean() else 1)
            normal = media * peso       # O NORMAL esperado para cada dia = média do mês × peso do dia da semana.
            novas[f"{c}__normal"] = normal   # Guarda a coluna do normal.
            # Variação percentual do dia: (observado ÷ normal − 1) × 100.
            # normal.where(normal > 0) apaga normais iguais a zero (evita dividir por zero).
            novas[f"{c}__var"] = 100 * (tab[c] / normal.where(normal > 0) - 1)
    # Junta (concat) a tabela original com todas as colunas novas, lado a lado (axis=1).
    # Fazer isso de uma vez no fim é mais rápido do que criar coluna por coluna.
    return pd.concat([tab, pd.DataFrame(novas, index=tab.index)], axis=1)


# Define _incerteza_normal(): recebe um bloco de dias e o nome da coluna; devolve um número decimal.
def _incerteza_normal(bloco: pd.DataFrame, c: str) -> float:
    """Variância relativa da soma dos 'normais' do bloco.

    O normal de um mês é uma média estimada com C casos, então tem erro
    relativo ~ 1/C. Dias do mesmo mês compartilham o mesmo erro.
    """
    mes = [bloco["data"].dt.year, bloco["data"].dt.month]     # Agrupamento por ano e mês.
    soma_mes = bloco.groupby(mes)[f"{c}__normal"].sum()       # Soma dos normais de cada mês dentro do bloco.
    casos = bloco.groupby(mes)[f"{c}__ref"].first()           # Quantos casos sustentam o normal de cada mês.
    total = soma_mes.sum()                                    # Soma de todos os normais do bloco.
    # Fórmula da variância relativa: Σ (soma_mês² ÷ casos) ÷ total².
    # clip(lower=1) evita dividir por zero (mínimo de 1 caso). Se total for 0, devolve "não é número".
    return float((soma_mes ** 2 / casos.clip(lower=1)).sum() / total ** 2) if total > 0 else np.nan


# Define comparar(): recebe um bloco de dias e o nome da coluna; devolve um dicionário de resultados.
def comparar(bloco: pd.DataFrame, c: str) -> dict:
    """Observado × normal nos dias do bloco, com intervalo de 95%.

    O intervalo considera a variação natural dos casos (Poisson) E a incerteza
    do próprio normal, que é grande quando há poucos casos (Heliópolis).
    """
    # o = total observado (soma dos casos); n = total esperado (soma dos normais); dias = nº de linhas.
    o, n, dias = float(bloco[c].sum()), float(bloco[f"{c}__normal"].sum()), len(bloco)
    # Resultados que sempre devolvemos. max(dias, 1) evita dividir por zero se o bloco estiver vazio.
    base = {"dias": dias, "obs": o, "normal": n, "obs_dia": o / max(dias, 1),
            "normal_dia": n / max(dias, 1), "var_log": np.nan}
    if n <= 0 or o <= 0:                # Sem casos observados ou sem normal: não dá para comparar.
        # "base | {...}" junta dois dicionários (o da direita acrescenta/substitui chaves).
        return base | {"variacao": np.nan, "ic_inf": np.nan, "ic_sup": np.nan,
                       "significativo": False}
    # Incerteza (variância, em escala logarítmica) = variação natural dos casos (1/o, modelo de Poisson)
    # + incerteza do próprio normal.
    var_log = 1 / o + _incerteza_normal(bloco, c)
    # razão = observado ÷ normal (1,15 = 15% acima). erro = 1,96 × desvio-padrão (1,96 dá 95% de confiança).
    razao, erro = o / n, 1.96 * np.sqrt(var_log)
    # Limites inferior e superior do intervalo de 95% (calculados em escala log e voltados com exp).
    lo, hi = razao * np.exp(-erro), razao * np.exp(erro)
    # variacao, ic_inf e ic_sup em porcentagem. "significativo" = o intervalo NÃO contém 1
    # (ou seja, não contém 0% de variação) → a diferença dificilmente é acaso.
    return base | {"var_log": var_log, "variacao": 100 * (razao - 1), "ic_inf": 100 * (lo - 1),
                   "ic_sup": 100 * (hi - 1), "significativo": not (lo <= 1 <= hi)}


# ------------------------------------------ 1. quanto mais quente, mais internações?
def por_faixa(tab: pd.DataFrame, grupo: str, var: str) -> pd.DataFrame:
    """Novembro a março, por faixa de temperatura, nos três recortes."""
    v = tab[tab["verao"]]               # Só os dias de verão.
    cortes, nomes = FAIXAS[var]         # Desempacota os cortes e os nomes da variável escolhida.
    # pd.cut classifica cada valor numa faixa. right=False → a faixa inclui o limite de baixo
    # e não o de cima (ex.: 30 cai em "30–33", não em "27–30").
    faixa = pd.cut(v[var], cortes, labels=nomes, right=False)
    linhas = []                         # Lista de resultados (cada item vira uma linha da tabela final).
    # Agrupa os dias por faixa. observed=True ignora faixas sem nenhum dia.
    for nome, bloco in v.groupby(faixa, observed=True):
        for r, rotulo in RECORTES.items():   # .items() dá os pares (chave, valor), ex.: ("regiao", "Região do Ipiranga").
            # Acrescenta uma linha: faixa, lugar e o resultado da comparação
            # (**comparar(...) espalha as chaves do dicionário devolvido).
            linhas.append({"faixa": nome, "recorte": r, "lugar": rotulo,
                           **comparar(bloco, col(r, grupo))})
    return pd.DataFrame(linhas)         # Transforma a lista de dicionários em tabela.


# Define correlacao(): recebe a tabela, o grupo e a variável; devolve uma tabela com rho e p-valor por lugar.
def correlacao(tab: pd.DataFrame, grupo: str, var: str) -> pd.DataFrame:
    """Spearman: temperatura do dia × % de internações acima do normal (verão)."""
    v = tab[tab["verao"]]               # Só verão.
    linhas = []
    for r, rotulo in RECORTES.items():  # Para cada lugar…
        # Pega duas colunas (temperatura e variação %) e remove dias com valor vazio.
        d = v[[var, f"{col(r, grupo)}__var"]].dropna()
        # Só calcula se houver mais de 2 dias e a temperatura variar (nunique = nº de valores diferentes).
        if len(d) > 2 and d[var].nunique() > 1:
            # Correlação de Spearman: rho (de −1 a +1) e p (chance de ser acaso).
            rho, p = stats.spearmanr(d[var], d[f"{col(r, grupo)}__var"])
        else:
            rho, p = np.nan, np.nan     # Dados insuficientes: "não é número".
        linhas.append({"recorte": r, "lugar": rotulo, "rho": rho, "p_valor": p, "dias": len(d)})
    return pd.DataFrame(linhas)


# ------------------------------------------- 2. quando o efeito aparece?
def defasagem(tab: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """Variação das internações k dias depois de um dia de calor (k = 0…7)."""
    linhas = []
    for k in range(config.MAX_DEFASAGEM + 1):   # k = 0 (o próprio dia), 1, 2… até 7.
        bloco = tab[tab[f"depois_{k}"]]         # Os dias que vêm exatamente k dias depois de um dia de calor.
        for r, rotulo in RECORTES.items():      # Para cada lugar, compara esses dias com o normal.
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
    # Remove dias sem temperatura média e usa a data como índice (necessário para o resample).
    c = clima.dropna(subset=["tmedia"]).set_index("data")
    # resample("MS") agrupa por mês ("Month Start" = cada mês rotulado pelo 1º dia).
    # Temperatura → média do mês; chuva → soma do mês.
    clima_mes = pd.DataFrame({"temp_media": c["tmedia"].resample("MS").mean(),
                              "chuva": c["chuva"].resample("MS").sum()})
    # Internações por arboviroses do lugar escolhido, somadas por mês, com a coluna renomeada.
    casos = (internacoes.set_index("data")[col(recorte, "arboviroses")]
             .resample("MS").sum().rename("internacoes"))
    # .to_frame() transforma a série em tabela; .join junta o clima do mês (how="left" mantém todos os meses de casos).
    mensal = casos.to_frame().join(clima_mes, how="left")
    for k in range(1, max_meses + 1):   # k = 1 e 2 (meses antes).
        anterior = clima_mes.shift(k)   # Desloca o clima k meses: cada mês recebe o clima de k meses antes.
        # reindex(mensal.index) alinha pelas mesmas datas da tabela mensal.
        mensal[f"temp_media_{k}m"] = anterior["temp_media"].reindex(mensal.index)
        mensal[f"chuva_{k}m"] = anterior["chuva"].reindex(mensal.index)
    linhas = []
    for k in range(max_meses + 1):      # k = 0 (mesmo mês), 1 e 2.
        sufixo = "" if k == 0 else f"_{k}m"   # Nome da coluna: "temp_media", "temp_media_1m", "temp_media_2m".
        # Para cada variável de clima (nome técnico, nome bonito)…
        for var, nome in (("temp_media", "Temperatura média"), ("chuva", "Chuva acumulada")):
            d = mensal[["internacoes", var + sufixo]].dropna()   # Duas colunas, sem vazios.
            # Só calcula se houver mais de 3 meses e o número de casos variar.
            if len(d) > 3 and d["internacoes"].nunique() > 1:
                rho, p = stats.spearmanr(d["internacoes"], d[var + sufixo])
            else:
                rho, p = np.nan, np.nan
            linhas.append({"meses_antes": k, "variavel": nome, "rho": rho, "p_valor": p,
                           "meses": len(d)})
    # Devolve a tabela mês a mês (índice vira coluna "mes") e a tabela de correlações.
    return {"mensal": mensal.reset_index(names="mes"), "correlacao": pd.DataFrame(linhas)}


# ------------------------------- 3. Heliópolis e região × cidade em dias de calor
def _razao_de_razoes(a: pd.Series, b: pd.Series) -> dict:
    """O aumento de A é maior que o de B? (razão entre as duas razões, IC 95%)."""
    # Só calcula se nenhum dos números for zero (para não dividir por zero).
    if min(a["obs"], b["obs"], a["normal"], b["normal"]) > 0:
        # Razão de A (obs/normal) dividida pela razão de B. Ex.: 1,20 / 1,10 ≈ 1,09.
        rr = (a["obs"] / a["normal"]) / (b["obs"] / b["normal"])
        # As incertezas dos dois lugares se SOMAM (em escala log).
        erro = 1.96 * np.sqrt(a["var_log"] + b["var_log"])
        d = {"vezes": rr, "ic_inf": rr * np.exp(-erro), "ic_sup": rr * np.exp(erro)}
        # Diferença confiável se o intervalo não contém 1 (1 = os dois aumentaram igual).
        d["significativo"] = not (d["ic_inf"] <= 1 <= d["ic_sup"])
        return d
    return {"vezes": np.nan, "ic_inf": np.nan, "ic_sup": np.nan, "significativo": False}


# Define comparar_recortes(): recebe a tabela, o grupo e a população de Heliópolis;
# devolve um dicionário com a tabela de comparação e os testes de diferença.
def comparar_recortes(tab: pd.DataFrame, grupo: str, pop_heliopolis: int) -> dict:
    j = tab["janela_calor"]             # True nos dias de calor e nos 2 seguintes.
    # População de cada lugar. A região não tem população conhecida (None).
    pops = {"heliopolis": pop_heliopolis, "regiao": None, "cidade": config.POP_SP}
    linhas = []
    for r, rotulo in RECORTES.items():
        res = comparar(tab.loc[j], col(r, grupo))   # Compara os dias de calor com o normal.
        # Fator para converter "casos por dia" em "casos por 100 mil habitantes por dia".
        # Se a população for desconhecida, fica "não é número".
        fator = 100_000 / pops[r] if pops.get(r) else np.nan
        linhas.append({"recorte": r, "lugar": rotulo, **res,
                       "taxa_normal": res["normal_dia"] * fator,   # taxa num dia normal
                       "taxa_calor": res["obs_dia"] * fator})      # taxa nos dias de calor
    df = pd.DataFrame(linhas).set_index("recorte")   # Tabela com o lugar como índice.
    # Heliópolis está dentro da cidade (0,5% da população) e a região também
    # (~5%): a sobreposição é pequena e o teste trata os dois como independentes.
    # Compara Heliópolis × cidade e região × cidade (dicionário com 2 resultados).
    dif = {r: _razao_de_razoes(df.loc[r], df.loc["cidade"]) for r in ("heliopolis", "regiao")}
    return {"tabela": df.reset_index(), "diferenca": dif}


# ----------------------------------------------------------------- conclusões
def _f(x: float, casas: int = 0) -> str:
    # Formata número com vírgula decimal. Ex.: _f(3.14159, 2) → "3,14".
    return f"{x:.{casas}f}".replace(".", ",")


# Define _mudou(): recebe uma variação (%) e devolve uma frase.
def _mudou(x: float) -> str:
    """'subiram 12%' / 'caíram 5%' / 'ficaram praticamente iguais'."""
    if pd.isna(x) or abs(x) < 0.5:      # Vazio ou menos de meio por cento…
        return "ficaram praticamente iguais"
    # Escolhe o verbo pelo sinal e mostra o número sem sinal.
    return f"{'subiram' if x > 0 else 'caíram'} {_f(abs(x))}%"


# Define _confiavel(): recebe uma linha de resultado e devolve um aviso (ou texto vazio).
def _confiavel(linha: pd.Series) -> str:
    # Se o resultado NÃO for confiável, acrescenta o aviso " (pode ser acaso)"; senão, nada.
    return "" if linha["significativo"] else " (pode ser acaso)"


# Define gerar_conclusoes(): recebe todos os resultados das análises.
def gerar_conclusoes(tab, grupo, criterio, limiar, faixas, corr, lags, comp) -> list[dict]:
    # Escreve as conclusões em português, a partir dos números calculados. Devolve uma lista de
    # dicionários {"titulo": ..., "texto": ...}.
    out, nome = [], GRUPOS[grupo].lower()   # out = lista de conclusões; nome = grupo em minúsculas.
    crit = config.CRITERIOS[criterio]       # Informações do critério de calor.
    c = corr.set_index("recorte")           # Correlações com o lugar como índice (facilita c.loc["cidade"]).
    sem_efeito = True                       # Começa supondo que não apareceu efeito; muda se aparecer.

    # 1. Mais calor, mais internações?
    # Separa as faixas de cada lugar (reset_index renumera as linhas a partir de 0).
    cid = faixas[faixas["recorte"] == "cidade"].reset_index(drop=True)
    reg = faixas[faixas["recorte"] == "regiao"].reset_index(drop=True)
    hel = faixas[faixas["recorte"] == "heliopolis"].reset_index(drop=True)
    # Só escreve se houver pelo menos 2 faixas e a correlação da cidade existir.
    if len(cid) >= 2 and not pd.isna(c.loc["cidade", "rho"]):
        cc, topo = c.loc["cidade"], cid.iloc[-1]   # cc = correlação da cidade; topo = a faixa MAIS quente.
        # "Sim" se: correlação significativa (p < 0,05) E positiva E a faixa mais quente subiu de forma confiável.
        if cc["p_valor"] < .05 and cc["rho"] > 0 and topo["significativo"] and topo["variacao"] > 0:
            resposta, sem_efeito = "Sim, na cidade como um todo.", False
        elif cc["p_valor"] < .05 and cc["rho"] < 0:   # Correlação significativa, mas NEGATIVA.
            resposta = "Não. Nos dias mais quentes houve até um pouco MENOS internações."
        else:                                          # Nada conclusivo.
            resposta = "Com estes dados, não apareceu aumento claro."
        out.append({
            "titulo": "Mais calor, mais internações?",
            # Monta o texto com os números da faixa mais quente nos três lugares (.iloc[-1] = última linha).
            "texto": (f"{resposta} No verão, nos dias com {TEXTO_VAR[crit['var']]} de {topo['faixa']}, as "
                      f"internações ({nome}) {_mudou(topo['variacao'])} em relação ao normal na "
                      f"cidade{_confiavel(topo)}, {_mudou(reg['variacao'].iloc[-1])} na região do "
                      f"Ipiranga{_confiavel(reg.iloc[-1])} e {_mudou(hel['variacao'].iloc[-1])} em "
                      f"Heliópolis{_confiavel(hel.iloc[-1])}."),
        })

    # 2. Heliópolis e região nos dias de calor
    t = comp["tabela"].set_index("recorte")   # Tabela da comparação, indexada pelo lugar.
    h, r, ci = t.loc["heliopolis"], t.loc["regiao"], t.loc["cidade"]   # Uma linha para cada lugar.
    if not pd.isna(ci["variacao"]):           # Só se houver resultado para a cidade.
        if h["significativo"]:                # Heliópolis sozinha já tem resultado confiável?
            leitura = "Em Heliópolis a mudança já é grande o bastante para não ser acaso."
        elif r["significativo"]:              # Senão, a região tem?
            leitura = ("Heliópolis sozinha tem poucos casos para afirmar, mas na região do "
                       "Ipiranga, que inclui Heliópolis e vive o mesmo clima, a mudança não é acaso. "
                       "É o indício mais forte do que acontece em Heliópolis.")
        else:                                 # Nenhum dos dois.
            leitura = ("Nem em Heliópolis nem na região a mudança foi grande o bastante para "
                       "descartar o acaso.")
        dr = comp["diferenca"]["regiao"]      # Teste "a região reagiu diferente da cidade?".
        if dr["significativo"]:
            leitura += (" A região reagiu " + ("mais" if dr["vezes"] > 1 else "menos") +
                        " que a cidade, e o teste indica que a diferença não é acaso.")
        # any(...) = True se ALGUM dos três lugares teve aumento confiável → então houve efeito.
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
    # Usa a região como referência se ela teve algum caso; senão usa a cidade.
    ref = "regiao" if lags.loc[lags["recorte"] == "regiao", "obs"].sum() > 0 else "cidade"
    # Filtra as defasagens desse lugar que são confiáveis E positivas.
    lr = lags[(lags["recorte"] == ref) & lags["significativo"] & (lags["variacao"] > 0)]
    if len(lr):                               # Se existir pelo menos uma…
        pico = lr.loc[lr["variacao"].idxmax()]   # …pega a de maior aumento (idxmax = linha do maior valor).
        k = int(pico["dias_depois"])          # Quantos dias depois do calor.
        # Frase do "quando": "no próprio dia", "1 dia depois", "3 dias depois"…
        quando = "no próprio dia" if k == 0 else f"{k} dia{'s' if k > 1 else ''} depois"
        out.append({
            "titulo": "Quando o efeito aparece?",
            "texto": (f"Na {RECORTES[ref].lower() if ref == 'cidade' else 'região do Ipiranga'}, "
                      f"o maior aumento confiável aparece {quando} do calor "
                      f"({_f(pico['variacao'])}% acima do normal). Isso mostra por quanto tempo "
                      "vale manter o alerta depois de um dia quente."),
        })

    # 4. Taxa por 100 mil
    if not pd.isna(h["taxa_normal"]):         # Só se a taxa de Heliópolis existir.
        out.append({
            "titulo": "Proporcionalmente, quem tem mais internados?",
            "texto": (f"Heliópolis tem {_f(h['taxa_normal'], 1)} internações por 100 mil "
                      f"habitantes num dia normal e {_f(h['taxa_calor'], 1)} nos dias de calor; a "
                      f"cidade, {_f(ci['taxa_normal'], 1)} e {_f(ci['taxa_calor'], 1)}. "
                      # Frase extra só se Heliópolis tiver taxa maior que a cidade.
                      + ("Heliópolis interna mais, com ou sem calor. "
                         if h["taxa_normal"] > ci["taxa_normal"] else "")
                      + "Parte disso é porque quase todos em Heliópolis dependem do SUS, e o "
                        "número depende da população usada (ajustável na barra lateral)."),
        })

    # 5. Se o calor não apareceu, explicar por quê
    if sem_efeito:                            # Se em nenhum momento apareceu efeito confiável…
        out.append({
            "titulo": "Por que o calor pode não aparecer nas internações?",
            "texto": ("Quem passa mal com o calor costuma ser atendido no pronto-socorro e liberado, "
                      "sem internar (e o SIH só registra internações). O número de internações também "
                      "depende de haver leito vago. Estudos em São Paulo encontram o efeito do calor "
                      "mais claramente nas MORTES: experimente o grupo \"Internações que terminaram "
                      "em morte\" e o critério \"Onda de calor\"."),
            # (o \" dentro da string é uma aspa dupla "escapada", para não fechar o texto)
        })
    return out                                # Devolve a lista de conclusões.


# -------------------------------------------------------------------- tudo
# Função principal deste arquivo: o app.py chama só ela.
def analisar(clima: pd.DataFrame, internacoes: pd.DataFrame, grupo: str,
             criterio: str = "dia_quente", pop_heliopolis: int = config.POP_HELIOPOLIS,
             descontar_feriados: bool = True, limiares: dict | None = None) -> dict:
    """Roda todas as análises. `limiares` fixa a régua de calor (ver clima.marcar_calor)."""
    var = var_do(criterio)                    # Variável de clima do critério.
    # Limiar usado: se "limiares" veio preenchido, usa; senão calcula a partir do clima. [var] pega o da variável.
    limiar = (limiares or clima_mod.limiares(clima))[var]
    # Tabela completa: 1 linha por dia, com clima, internações e normais.
    completa = montar_tabela(clima, internacoes, criterio, descontar_feriados)
    # Tira os feriados (o "~" inverte): as análises usam só dias comuns.
    tab = completa[~completa["feriado"]].reset_index(drop=True)   # análises só em dias comuns
    faixas = por_faixa(tab, grupo, var)       # Análise 1: por faixa de temperatura.
    corr = correlacao(tab, grupo, var)        # Análise 1b: correlação de Spearman.
    lags = defasagem(tab, grupo)              # Análise 2: dias depois do calor.
    comp = comparar_recortes(tab, grupo, pop_heliopolis)   # Análise 3: Heliópolis × região × cidade.
    # Devolve tudo num dicionário, que o app.py usa para desenhar o painel.
    return {"tabela": tab, "completa": completa, "limiar": limiar, "var": var,
            "dias_calor": int(tab["dia_calor"].sum()),                  # nº de dias de calor
            "feriados_removidos": int(completa["feriado"].sum()),       # nº de feriados tirados
            # nº de dias de calor que caíram em feriado (True & True conta 1)
            "calor_em_feriado": int((completa["janela_calor"] & completa["feriado"]).sum()),
            "faixas": faixas, "correlacao": corr, "defasagem": lags, "comparacao": comp,
            "conclusoes": gerar_conclusoes(tab, grupo, criterio, limiar, faixas, corr, lags, comp)}
