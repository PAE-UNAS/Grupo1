"""Limpeza de séries de sensores de temperatura e umidade.

Veio da branch `feature-limpeza-dados`. Foi pensada para os sensores que a
UNAS pretende instalar em Heliópolis, mas serve para qualquer série com as
colunas abaixo (uma linha por leitura):

    sensor_id     identificador do sensor (texto)
    timestamp     data e hora da leitura (aceita vários formatos, dia primeiro)
    temperatura   número
    umidade       umidade relativa do ar, em %
    unidade_temp  "C" ou "F" (opcional; se faltar, assume Celsius)

Etapas, nesta ordem:
    1. padronizar_timestamp  texto -> data/hora
    2. padronizar_unidades   Fahrenheit -> Celsius
    3. remover_outliers      valores fisicamente impossíveis viram vazio
    4. tratar_ausentes       lacunas curtas (até 3 leituras) são interpoladas
    5. remove leituras duplicadas (mesmo sensor e horário)
"""
# ↑ Docstring do módulo: explica o arquivo. Não executa nada.

import numpy as np      # NumPy: usamos o "np.nan", que representa um valor vazio ("não é número").
import pandas as pd     # Pandas: tabelas (DataFrames).

# Limites físicos plausíveis para São Paulo. Fora disso é erro do sensor.
# Duas variáveis definidas na mesma linha: a menor e a maior temperatura aceitas (°C).
TEMP_MIN, TEMP_MAX = -5.0, 50.0
# Umidade relativa só pode ir de 0% a 100%.
UMID_MIN, UMID_MAX = 0.0, 100.0


def padronizar_timestamp(df):          # Etapa 1: transforma o texto de data/hora em data/hora de verdade.
    df = df.copy()                     # Trabalha numa cópia, para não alterar a tabela original.
    # pd.to_datetime converte o texto. format="mixed" aceita formatos diferentes no mesmo arquivo;
    # dayfirst=True lê "05/03/2024" como 5 de março (padrão brasileiro), e não como 3 de maio.
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", dayfirst=True)
    return df


def padronizar_unidades(df):           # Etapa 2: converte Fahrenheit para Celsius.
    df = df.copy()
    if "unidade_temp" not in df:       # Se a tabela nem tem a coluna de unidade…
        df["unidade_temp"] = "C"       # …assume que tudo está em Celsius.
    # Cria uma coluna True/False: a unidade é "F"?
    # astype(str) garante texto; .str.strip() tira espaços; .str.upper() põe em maiúscula ("f" → "F").
    f = df["unidade_temp"].astype(str).str.strip().str.upper() == "F"
    # Nas linhas em Fahrenheit (df.loc[f, ...]), aplica a fórmula de conversão: °C = (°F − 32) × 5/9.
    df.loc[f, "temperatura"] = (df.loc[f, "temperatura"] - 32) * 5 / 9
    df["unidade_temp"] = "C"           # Agora tudo está em Celsius.
    return df


def remover_outliers(df):              # Etapa 3: apaga valores impossíveis (erro do sensor).
    df = df.copy()
    # .between(min, max) = True se o valor estiver entre os limites. "~" inverte: True se estiver FORA.
    # Nessas linhas, a temperatura vira vazia (np.nan).
    df.loc[~df["temperatura"].between(TEMP_MIN, TEMP_MAX), "temperatura"] = np.nan
    # Mesma coisa para a umidade.
    df.loc[~df["umidade"].between(UMID_MIN, UMID_MAX), "umidade"] = np.nan
    return df


def tratar_ausentes(df, limite_horas=3):   # Etapa 4: preenche buracos curtos. Padrão: até 3 leituras.
    """Interpola lacunas curtas DENTRO da série de cada sensor.

    Lacunas maiores que `limite_horas` leituras continuam vazias: inventar
    dados por muito tempo esconderia uma falha real do sensor.
    """
    # Ordena por sensor e depois por horário (a interpolação precisa da ordem certa).
    df = df.sort_values(["sensor_id", "timestamp"]).copy()
    cols = ["temperatura", "umidade"]  # Colunas que vamos preencher.
    # groupby("sensor_id") faz a operação separadamente para cada sensor (não mistura sensores).
    # .transform(lambda s: ...) aplica a função a cada coluna de cada sensor e devolve no mesmo formato.
    # s.interpolate(...) preenche os vazios com valores "no meio do caminho" entre os vizinhos:
    #   limit=limite_horas      → preenche no máximo 3 vazios seguidos;
    #   limit_area="inside"     → só preenche buracos ENTRE dois valores (não inventa no começo nem no fim).
    df[cols] = df.groupby("sensor_id")[cols].transform(
        lambda s: s.interpolate(limit=limite_horas, limit_area="inside"))
    return df


def limpar(df):                        # Função principal: faz todas as etapas e conta o que foi feito.
    """Aplica todas as etapas e devolve (dados limpos, relatório de qualidade)."""
    df = df.copy()
    for c in ("temperatura", "umidade"):   # Para as duas colunas numéricas…
        # …converte para número; o que não for número (ex.: "erro") vira vazio.
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "unidade_temp" not in df:       # Sem coluna de unidade → assume Celsius.
        df["unidade_temp"] = "C"

    # O relatório é um dicionário que vai acumulando números sobre a limpeza.
    relatorio = {"linhas_brutas": len(df)}   # Quantas linhas chegaram.
    # Quantos valores vazios havia ANTES da limpeza. .isna() marca os vazios;
    # .sum().sum() soma por coluna e depois soma as colunas.
    relatorio["ausentes_antes"] = int(df[["temperatura", "umidade"]].isna().sum().sum())
    # Quantos sensores estavam em Fahrenheit: pega a unidade da 1ª linha de cada sensor,
    # verifica se é "F" e conta os True.
    relatorio["sensores_em_fahrenheit"] = int(
        (df.groupby("sensor_id")["unidade_temp"].first().astype(str).str.upper() == "F").sum())

    df = padronizar_timestamp(df)      # Etapa 1.
    df = padronizar_unidades(df)       # Etapa 2.

    antes = df[["temperatura", "umidade"]].isna().sum().sum()    # Vazios antes de remover os impossíveis.
    df = remover_outliers(df)          # Etapa 3.
    depois = df[["temperatura", "umidade"]].isna().sum().sum()   # Vazios depois.
    # A diferença é quantos valores impossíveis foram apagados.
    relatorio["outliers_removidos"] = int(depois - antes)

    df = tratar_ausentes(df)           # Etapa 4.
    # Quantos vazios sobraram depois de preencher os buracos curtos.
    relatorio["ausentes_depois"] = int(df[["temperatura", "umidade"]].isna().sum().sum())

    # Etapa 5: remove leituras repetidas (mesmo sensor no mesmo horário), mantendo a primeira.
    df = df.drop_duplicates(["sensor_id", "timestamp"])
    relatorio["linhas_limpas"] = len(df)   # Quantas linhas sobraram no fim.
    # Devolve DUAS coisas (uma tupla): a tabela limpa (com linhas renumeradas) e o relatório.
    return df.reset_index(drop=True), relatorio
