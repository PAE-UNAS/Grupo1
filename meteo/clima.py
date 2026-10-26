"""Clima — Open-Meteo (reanálise ERA5), dados diários desde 1991.

Docs: https://open-meteo.com/en/docs/historical-weather-api
Gratuita e sem chave. É uma estimativa para uma área de vários km² em volta
de Heliópolis: não mede dentro da favela e tende a subestimar o calor local.
"""
# ↑ Docstring do módulo: texto entre aspas triplas que explica o arquivo. Não executa nada.

# Permite usar dicas de tipo modernas (ex.: "dict | None") mesmo em versões mais antigas do Python.
from __future__ import annotations

# Do módulo "datetime" (já vem com o Python), traz:
#   date      → representa uma data (ano, mês, dia)
#   timedelta → representa um intervalo de tempo (ex.: 6 dias), para somar/subtrair de datas
from datetime import date, timedelta

import numpy as np      # NumPy: contas numéricas (percentis, regressão linear…). Apelido "np".
import pandas as pd     # Pandas: tabelas (DataFrames). Apelido "pd".
import requests         # Requests: faz pedidos HTTP, ou seja, "acessa sites/APIs" pelo código.

from meteo import config   # Nosso arquivo de configurações (coordenadas, pastas, limiares…).

# Endereço (URL) da API de dados históricos da Open-Meteo.
URL = "https://archive-api.open-meteo.com/v1/archive"

# nome na API -> nome no projeto
# Dicionário de tradução: a API devolve colunas em inglês; aqui definimos o nome que usaremos.
VARIAVEIS = {
    "temperature_2m_max": "tmax",              # temperatura máxima do dia, a 2 m do chão (°C)
    "temperature_2m_min": "tmin",              # temperatura mínima do dia (°C)
    "temperature_2m_mean": "tmedia",           # temperatura média do dia (°C)
    "apparent_temperature_max": "sensacao_max",  # considera umidade e vento
    #                                            ↑ sensação térmica máxima: o calor que o corpo sente (°C)
    "precipitation_sum": "chuva",              # chuva acumulada no dia (mm)
}


# "-> date" é uma dica de tipo: avisa que a função devolve uma data.
def ultima_data() -> date:
    """A reanálise é publicada com ~5 dias de atraso."""
    # date.today() = data de hoje. Subtraímos 6 dias (margem de segurança), porque a API
    # ainda não tem os dados dos últimos dias.
    return date.today() - timedelta(days=6)


def baixar() -> pd.DataFrame:      # Devolve uma tabela (DataFrame) com o clima diário.
    """Baixa a série diária de 1991 até hoje (ou lê do cache, se já baixou hoje)."""
    fim = ultima_data()            # Último dia que vamos pedir à API.
    # Caminho do arquivo de cache. O "/" junta pastas e arquivo (objeto Path).
    # O nome inclui a data final, ex.: data/cache/clima_2026-10-20.parquet.
    # Parquet é um formato de tabela compactado e rápido de ler.
    arquivo = config.CACHE / f"clima_{fim}.parquet"
    if arquivo.exists():           # Se esse arquivo já existe (já baixamos hoje)…
        return pd.read_parquet(arquivo)   # …lê do disco e devolve, sem acessar a internet.

    # Parâmetros que vão no pedido à API (viram "?latitude=...&longitude=..." na URL).
    params = {
        "latitude": config.LATITUDE, "longitude": config.LONGITUDE,   # o ponto de Heliópolis
        # Data inicial: 1º de janeiro do primeiro ano da climatologia (1991). Data final: "fim".
        "start_date": f"{config.CLIMATOLOGIA[0]}-01-01", "end_date": str(fim),
        # "daily" = quais variáveis diárias queremos. ",".join(VARIAVEIS) junta as CHAVES do
        # dicionário com vírgulas: "temperature_2m_max,temperature_2m_min,...".
        # "timezone" = fuso horário, para que "o dia" seja o dia de Brasília.
        "daily": ",".join(VARIAVEIS), "timezone": config.FUSO,
    }
    try:                           # Tenta acessar a API…
        # requests.get faz o pedido. timeout=120 → desiste se demorar mais de 120 segundos.
        resp = requests.get(URL, params=params, timeout=120)
    except requests.RequestException:   # …se der erro de rede (sem internet, servidor fora do ar)…
        resp = None                # …marca que não houve resposta.
    # status_code 200 = "deu certo" no protocolo HTTP. Qualquer outro número indica problema.
    if resp is None or resp.status_code != 200:
        # Sem internet ou API fora do ar: usa o último arquivo baixado, se houver
        # glob("clima_*.parquet") lista os arquivos que combinam com o padrão (* = qualquer coisa).
        # sorted(...) ordena pelo nome; como o nome tem a data, o último é o mais recente.
        anteriores = sorted(config.CACHE.glob("clima_*.parquet"))
        if anteriores:                               # Se existe algum arquivo antigo…
            return pd.read_parquet(anteriores[-1])   # …usa o mais recente ([-1] = último da lista).
        # Monta a explicação do erro: os 300 primeiros caracteres da resposta da API, ou "sem conexão".
        motivo = resp.text[:300] if resp is not None else "sem conexão"
        # "raise" dispara um erro de propósito, que interrompe a função e é mostrado no painel.
        raise RuntimeError(f"Open-Meteo recusou o pedido: {motivo}")

    # resp.json() transforma a resposta (texto no formato JSON) em dicionário Python.
    # ["daily"] pega a parte com os dados diários. pd.DataFrame(...) transforma em tabela.
    # .rename(...) troca os nomes das colunas: "time" vira "data" e as demais seguem VARIAVEIS.
    # (**VARIAVEIS "espalha" o dicionário dentro de outro dicionário.)
    df = pd.DataFrame(resp.json()["daily"]).rename(columns={"time": "data", **VARIAVEIS})
    # Cria a pasta de cache, se não existir. parents=True cria pastas intermediárias;
    # exist_ok=True não reclama se ela já existir.
    config.CACHE.mkdir(parents=True, exist_ok=True)
    for antigo in config.CACHE.glob("clima_*.parquet"):   # só guarda a versão mais nova
        antigo.unlink()            # .unlink() apaga o arquivo antigo.
    df.to_parquet(arquivo)         # Salva a tabela nova no cache.
    return df                      # Devolve a tabela.


def tratar(df: pd.DataFrame) -> pd.DataFrame:   # Recebe a tabela crua e devolve a tabela limpa.
    """Tipos, duplicatas, valores impossíveis e colunas de calendário."""
    df = df.copy()                 # Trabalha numa CÓPIA, para não alterar a tabela original por engano.
    df["data"] = pd.to_datetime(df["data"])   # Converte o texto "2024-01-15" em data de verdade.
    # drop_duplicates("data") remove dias repetidos (mantém o primeiro);
    # sort_values("data") ordena do mais antigo ao mais novo;
    # reset_index(drop=True) renumera as linhas 0, 1, 2…
    df = df.drop_duplicates("data").sort_values("data").reset_index(drop=True)

    for col in ["tmax", "tmin", "tmedia", "sensacao_max"]:   # Para cada coluna de temperatura…
        # Garante que é número. errors="coerce" transforma o que não for número em vazio (NaN).
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # df.loc[condição, coluna] = None → apaga (deixa vazio) os valores que satisfazem a condição.
        # Condição: menor que −5 °C OU (|) maior que 50 °C, impossíveis em São Paulo.
        df.loc[(df[col] < -5) | (df[col] > 50), col] = None     # fora do possível em SP
    # Chuva: converte para número e .clip(lower=0) troca negativos por 0 (não existe chuva negativa).
    df["chuva"] = pd.to_numeric(df["chuva"], errors="coerce").clip(lower=0)
    # Se a mínima for maior que a máxima, o dia está errado: apaga as três temperaturas desse dia.
    df.loc[df["tmin"] > df["tmax"], ["tmax", "tmin", "tmedia"]] = None

    # Dias que faltarem aparecem como linhas vazias (não somem em silêncio)
    # pd.date_range cria TODOS os dias entre a primeira e a última data (freq="D" = diário).
    grade = pd.date_range(df["data"].min(), df["data"].max(), freq="D")
    # set_index("data") usa a data como "índice" (rótulo das linhas);
    # reindex(grade) cria uma linha para cada dia da grade (os que faltavam ficam vazios);
    # rename_axis("data") dá nome ao índice; reset_index() volta a data para uma coluna normal.
    df = df.set_index("data").reindex(grade).rename_axis("data").reset_index()

    # Cria duas colunas de uma vez: o ano e o mês de cada data (.dt dá acesso às partes da data).
    df["ano"], df["mes"] = df["data"].dt.year, df["data"].dt.month
    return marcar_calor(df)        # Marca quais dias são de calor (função definida mais abaixo) e devolve.


# Define a função carregar(): sem parâmetros, devolve a tabela de clima pronta para usar.
def carregar() -> pd.DataFrame:
    # Atalho que faz tudo: baixa (ou lê do cache) e depois trata. É o que o app.py chama.
    return tratar(baixar())


# -------------------------------------------------------- o que é "calor"
# "-> dict[str, float]" = devolve um dicionário com textos como chaves e números decimais como valores.
def limiares(df: pd.DataFrame) -> dict[str, float]:
    """Percentil 90 de cada variável nos meses quentes do período de referência.

    Usar um período fixo (1991–2020) faz "dia de calor" significar a mesma
    coisa em qualquer ano: se hoje há mais dias acima do limiar, é porque
    esquentou, e não porque a régua mudou.
    """
    ini, fim = config.CLIMATOLOGIA      # Desempacota a tupla (1991, 2020) em duas variáveis.
    # Filtra a tabela: anos entre 1991 e 2020 (inclusive) E (&) meses quentes (nov a mar).
    ref = df[df["ano"].between(ini, fim) & df["mes"].isin(config.MESES_QUENTES)]
    # .notna().sum() conta quantos valores NÃO são vazios. Se houver menos de 365…
    if ref["sensacao_max"].notna().sum() < 365:   # série curta: usa o que houver
        ref = df[df["mes"].isin(config.MESES_QUENTES)]   # …usa todos os anos disponíveis.
    # Monta um dicionário {variável: percentil 90}. Ex.: {"sensacao_max": 33.5, "tmin": 21.2}.
    # np.nanpercentile calcula o percentil ignorando vazios. PERCENTIL_DIA_CALOR = 90 →
    # só 10% dos dias de referência ficam acima desse valor.
    return {v: float(np.nanpercentile(ref[v], config.PERCENTIL_DIA_CALOR))
            # As variáveis vêm dos critérios do config. {c["var"] for c in ...} é um CONJUNTO
            # (sem repetidos) com a variável de cada critério.
            for v in {c["var"] for c in config.CRITERIOS.values()}}


# O "_" no começo do nome indica que a função é de uso interno deste arquivo.
def _ondas(quente: pd.Series, minimo: int) -> pd.Series:
    """Marca os dias que fazem parte de uma sequência de `minimo`+ dias quentes."""
    # Truque para numerar "blocos" de dias iguais seguidos:
    # quente.shift() desloca a série 1 dia; "!=" fica True quando o valor muda de um dia para o outro;
    # .cumsum() (soma acumulada) dá um número novo a cada mudança. Ex.:
    #   quente: F F T T T F T  →  bloco: 1 1 2 2 2 3 4
    bloco = (quente != quente.shift()).cumsum()
    # Para cada dia, quantos dias tem o bloco a que ele pertence. Ex.: 2 2 3 3 3 1 1
    tamanho = quente.groupby(bloco).transform("size")
    # É onda se o dia for quente E o bloco tiver pelo menos "minimo" dias (ex.: 3).
    return quente & (tamanho >= minimo)


# "lim: dict | None = None" → lim pode ser um dicionário ou None (vazio); o padrão é None.
def marcar_calor(df: pd.DataFrame, lim: dict | None = None) -> pd.DataFrame:
    """Uma coluna booleana por critério de calor (dia_quente, noite_quente, onda_calor).

    `lim` permite fixar os limiares. Na série corrigida pelos sensores usamos
    os limiares da Open-Meteo, para que a régua de calor seja a mesma e a
    diferença apareça como MAIS dias acima do limiar.
    """
    df = df.copy()                       # Cópia, para não mexer na tabela original.
    # "lim or limiares(df)": se lim veio preenchido, usa ele; se é None, calcula a partir desta tabela.
    lim = lim or limiares(df)
    # Coluna True/False: a sensação térmica máxima do dia passou do limiar?
    df["dia_quente"] = df["sensacao_max"] >= lim["sensacao_max"]
    # Coluna True/False: a mínima do dia (a noite) ficou acima do limiar?
    df["noite_quente"] = df["tmin"] >= lim["tmin"]
    # Coluna True/False: o dia faz parte de uma sequência de DIAS_ONDA (ex.: 3) dias quentes seguidos?
    df["onda_calor"] = _ondas(df["dia_quente"], config.DIAS_ONDA)
    # .attrs é um "bolso" de informações extras da tabela. Guardamos os limiares usados.
    df.attrs["limiares"] = lim
    return df


# ----------------------------------------------- o calor está aumentando?
def resumo_anual(df: pd.DataFrame) -> pd.DataFrame:
    """Dias de calor por ano (cada critério) + tendência em dias por década.

    O ano corrente aparece marcado como incompleto.
    """
    criterios = list(config.CRITERIOS)   # Nomes dos critérios: ["dia_quente", "noite_quente", "onda_calor"].
    # groupby("ano") agrupa as linhas por ano. .agg(...) calcula um resumo por grupo:
    #   para cada critério c → nova coluna c = soma (sum) dos True (True vale 1) = nº de dias de calor no ano;
    #   dias_com_dado = quantos dias do ano têm sensação térmica preenchida (count ignora vazios).
    # O "**{...}" cria esses argumentos a partir de um dicionário.
    anual = df.groupby("ano").agg(**{c: (c, "sum") for c in criterios},
                                  dias_com_dado=("sensacao_max", "count"))
    # Ano "completo" = tem pelo menos 360 dias com dado (o ano atual, ainda em andamento, não tem).
    anual["completo"] = anual["dias_com_dado"] >= 360
    return anual.reset_index()           # Volta "ano" a ser coluna normal e devolve.


# Define tendencia(): recebe o resumo anual e o critério; devolve um dicionário com a reta.
def tendencia(anual: pd.DataFrame, criterio: str) -> dict:
    """Reta de tendência (mínimos quadrados) só com anos completos."""
    a = anual[anual["completo"]]         # Só anos completos (o ano incompleto distorceria a reta).
    if len(a) < 5:                       # Com menos de 5 anos não faz sentido traçar tendência:
        return {"por_decada": np.nan, "x": [], "y": []}   # devolve vazio (np.nan = "não é número").
    # np.polyfit(x, y, 1) ajusta uma RETA (grau 1) aos pontos. Devolve [inclinação, intercepto].
    # A inclinação = quantos dias de calor a mais por ano.
    coef = np.polyfit(a["ano"], a[criterio], 1)
    x = np.array([a["ano"].min(), a["ano"].max()])   # Dois pontos (primeiro e último ano) para desenhar a reta.
    # por_decada = inclinação × 10 (dias a mais por década).
    # np.polyval(coef, x) calcula a altura da reta nesses dois anos.
    return {"por_decada": 10 * coef[0], "x": x, "y": np.polyval(coef, x)}


# Define por_decada(): recebe o resumo anual e o critério; devolve uma tabela por década.
def por_decada(anual: pd.DataFrame, criterio: str) -> pd.DataFrame:
    """Média de dias de calor por ano em cada década (só anos completos)."""
    a = anual[anual["completo"]].copy()  # Só anos completos (cópia, porque vamos criar coluna nova).
    # "//" é divisão inteira. Ex.: 1997 // 10 = 199; × 10 = 1990. Assim cada ano ganha sua década.
    a["decada"] = (a["ano"] // 10) * 10
    # Agrupa por década e calcula a média (mean) e a quantidade de anos (count) de dias de calor.
    d = a.groupby("decada")[criterio].agg(["mean", "count"]).reset_index()
    # Rótulo legível da década, ex.: "1991–1999" ou "2020–2025".
    # max(x, primeiro ano) evita mostrar 1990 se a série começa em 1991;
    # min(x + 9, último ano) evita mostrar 2029 se a série termina em 2025.
    d["rotulo"] = [f"{max(x, a['ano'].min())}–{min(x + 9, a['ano'].max())}" for x in d["decada"]]
    return d


# Define mapa_ano_mes(): recebe o clima diário e o critério; devolve a grade ano × mês.
def mapa_ano_mes(df: pd.DataFrame, criterio: str) -> pd.DataFrame:
    """Matriz ano × mês com o número de dias de calor (para o mapa de calor)."""
    # pivot_table monta uma tabela cruzada: linhas = anos, colunas = meses,
    # valores = soma dos dias de calor (True conta 1). É a mesma ideia da "tabela dinâmica" do Excel.
    m = df.pivot_table(index="ano", columns="mes", values=criterio, aggfunc="sum")
    # Garante as 12 colunas na ordem 1..12, mesmo que algum mês não tenha aparecido.
    return m.reindex(columns=range(1, 13))
