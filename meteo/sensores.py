"""Sensores da UNAS — leitura, limpeza, índice de calor e calibração da Open-Meteo.

╔══════════════════════════════════════════════════════════════════════════╗
║  COMO TROCAR OS DADOS SIMULADOS PELOS DADOS REAIS DOS SENSORES           ║
║                                                                          ║
║  1. Exporte as leituras dos sensores para um ou mais arquivos .csv com   ║
║     as colunas: sensor_id; timestamp; temperatura; umidade; unidade_temp ║
║     (detalhes em meteo/limpeza.py e no README).                          ║
║  2. Dê aos sensores instalados DENTRO de Heliópolis um nome começando    ║
║     com "heliopolis" (ex.: heliopolis_viela_01). Só eles entram na       ║
║     calibração. O prefixo pode ser mudado em                             ║
║     config.PREFIXO_SENSOR_HELIOPOLIS.                                    ║
║  3. Coloque os arquivos em data/sensores/ e recarregue o painel.         ║
║                                                                          ║
║  Pronto: havendo QUALQUER .csv em data/sensores/, os dados simulados     ║
║  deixam de ser usados automaticamente, e os avisos "DADOS SIMULADOS"     ║
║  somem do painel. Para desligar a simulação de vez (ex.: na versão       ║
║  final para a ONG), mude config.SENSORES_PLACEHOLDER para False.         ║
╚══════════════════════════════════════════════════════════════════════════╝

O que é simulado (função `simular`) e por quê: enquanto não há sensores, o
painel precisa mostrar COMO as análises vão funcionar. Os dados simulados
partem da Open-Meteo do último verão e somam um "excesso de calor" fixo por
sensor (config.PLACEHOLDER_EXCESSO). Esses números NÃO são medições e NÃO
devem ser citados como resultado.
"""
# ↑ Docstring do módulo: explica o arquivo e como trocar a simulação pelos dados reais.

# Permite dicas de tipo modernas (ex.: "dict | None") em qualquer versão do Python 3.
from __future__ import annotations

import numpy as np        # NumPy: contas com listas de números (seno, raiz, números aleatórios…).
import pandas as pd       # Pandas: tabelas (DataFrames).

from meteo import config           # Configurações do projeto (pasta dos sensores, prefixo, simulação…).
from meteo.limpeza import limpar   # A função de limpeza dos dados dos sensores (arquivo limpeza.py).

# Colunas obrigatórias (e a opcional "unidade_temp") dos arquivos CSV dos sensores.
COLUNAS = ["sensor_id", "timestamp", "temperatura", "umidade", "unidade_temp"]

# Faixas de risco do Índice de Calor (NOAA/Serviço Meteorológico dos EUA), em °C
# Tupla com duas listas: (cortes em °C, nomes das faixas).
# Ex.: entre 27 e 32 °C = "cautela"; de 54 °C para cima = "perigo extremo".
FAIXAS_RISCO = ([-np.inf, 27, 32, 41, 54, np.inf],
                ["sem risco", "cautela", "cautela extrema", "perigo", "perigo extremo"])

MINIMO_DIAS_CALIBRACAO = 14   # menos que isso: a correção não é calculada


def indice_calor(temp_c, umid):        # Recebe temperatura (°C) e umidade (%); devolve o índice de calor (°C).
    """Índice de calor da NOAA (Rothfusz, com os ajustes oficiais), em °C.

    Combina temperatura e umidade: com o ar úmido o suor evapora menos e o
    corpo sente mais calor. Abaixo de ~27 °C usa a fórmula simplificada.
    """
    # A fórmula oficial foi feita em Fahrenheit, então convertemos: °F = °C × 9/5 + 32.
    # np.asarray(..., dtype=float) transforma a entrada (número, lista ou coluna) em array de decimais.
    t = np.asarray(temp_c, dtype=float) * 9 / 5 + 32
    rh = np.asarray(umid, dtype=float)       # rh = "relative humidity" (umidade relativa, %).
    # Fórmula simplificada (de Steadman), usada para calor leve.
    simples = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    # Fórmula completa (regressão de Rothfusz), com os coeficientes oficiais da NOAA.
    # "**" é potência: t ** 2 = t ao quadrado.
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - .22475541 * t * rh
          - .00683783 * t ** 2 - .05481717 * rh ** 2 + .00122874 * t ** 2 * rh
          + .00085282 * t * rh ** 2 - .00000199 * t ** 2 * rh ** 2)
    # np.errstate(invalid="ignore") silencia avisos de "raiz de número negativo" neste trecho
    # (eles são calculados mas descartados pelo np.where logo abaixo).
    with np.errstate(invalid="ignore"):
        # Ajuste 1 (oficial): ar MUITO SECO (umidade < 13%) com temperatura entre 80 e 112 °F.
        seco = (rh < 13) & (t >= 80) & (t <= 112)
        # np.where(condição, se_sim, se_não): onde "seco" for True, subtrai a correção; senão mantém hi.
        hi = np.where(seco, hi - ((13 - rh) / 4) * np.sqrt((17 - np.abs(t - 95)) / 17), hi)
    # Ajuste 2 (oficial): ar MUITO ÚMIDO (umidade > 85%) com temperatura entre 80 e 87 °F.
    umido = (rh > 85) & (t >= 80) & (t <= 87)
    hi = np.where(umido, hi + ((rh - 85) / 10) * ((87 - t) / 5), hi)
    # Regra da NOAA: se a média entre a fórmula simples e a temperatura der menos de 80 °F,
    # usa a fórmula simples; senão usa a completa.
    hi = np.where((simples + t) / 2 < 80, simples, hi)
    return (hi - 32) * 5 / 9                 # Converte o resultado de volta para °C.


# ------------------------------------------------------------------- leitura
def arquivos() -> list:                # Lista os arquivos CSV dos sensores.
    # Se a pasta existir, devolve a lista ordenada de arquivos .csv dentro dela; senão, lista vazia.
    return sorted(config.SENSORES.glob("*.csv")) if config.SENSORES.exists() else []


# Devolve uma tupla: (tabela limpa, relatório).
def _preparar(bruto: pd.DataFrame, nomes: list[str]) -> tuple[pd.DataFrame, dict]:
    """Limpeza (meteo.limpeza) + índice de calor. Igual para dados reais e simulados."""
    for c in ("temperatura", "umidade"):          # aceita vírgula decimal (Excel em português)
        # Se a coluna existe e NÃO foi lida como número (provavelmente por causa da vírgula)…
        if c in bruto and not pd.api.types.is_numeric_dtype(bruto[c]):
            # …transforma em texto e troca vírgula por ponto ("33,1" → "33.1").
            # regex=False = a vírgula é tratada como caractere comum, não como padrão especial.
            bruto[c] = bruto[c].astype(str).str.replace(",", ".", regex=False)
    # Verifica se faltam colunas obrigatórias (as 4 primeiras de COLUNAS; unidade_temp é opcional).
    faltando = [c for c in COLUNAS[:4] if c not in bruto]
    if faltando:                                  # Se faltar alguma…
        # …dispara um erro com mensagem clara (", ".join junta os nomes com vírgula).
        raise ValueError(f"Faltam colunas nos arquivos de sensores: {', '.join(faltando)}")
    df, relatorio = limpar(bruto)                 # Limpa os dados (limpeza.py) e recebe o relatório.
    # Calcula o índice de calor de cada leitura e guarda numa coluna nova.
    df["indice_calor"] = indice_calor(df["temperatura"], df["umidade"])
    relatorio["arquivos"] = nomes                 # Anota no relatório de quais arquivos vieram os dados.
    return df, relatorio


# "tuple[...] | None" = devolve uma tupla (tabela, relatório) OU None (se não houver arquivos).
def carregar() -> tuple[pd.DataFrame, dict] | None:
    """DADOS REAIS: lê todos os CSVs de data/sensores/ (None se não houver)."""
    lista = arquivos()                 # Lista de arquivos CSV.
    if not lista:                      # Lista vazia (nenhum arquivo)?
        return None                    # Então não há dados reais.
    # Lê cada arquivo. sep=None + engine="python" → o pandas DESCOBRE sozinho se o separador é ";" ou ",".
    # dtype={"sensor_id": str} → o nome do sensor é sempre lido como texto (mesmo que seja "01").
    partes = [pd.read_csv(a, sep=None, engine="python", dtype={"sensor_id": str}) for a in lista]
    # Junta todos os arquivos numa tabela só e prepara (limpa + índice de calor).
    # [a.name for a in lista] = lista só com os nomes dos arquivos (sem a pasta).
    return _preparar(pd.concat(partes, ignore_index=True), [a.name for a in lista])


# Define obter(): recebe o clima e devolve (tabela, relatório, é_simulado) ou None.
def obter(clima: pd.DataFrame) -> tuple[pd.DataFrame, dict, bool] | None:
    """Ponto único de entrada usado pelo app: (dados, relatório, é_simulado).

    Ordem de prioridade:
      1. dados reais em data/sensores/  -> é_simulado = False
      2. sem arquivos e SENSORES_PLACEHOLDER = True -> dados simulados (é_simulado = True)
      3. sem arquivos e SENSORES_PLACEHOLDER = False -> None (abas mostram instruções)
    """
    reais = carregar()                 # Tenta ler os dados reais.
    if reais is not None:              # Se existem…
        # …devolve (tabela, relatório, False). O "*reais" "desembrulha" a tupla de 2 itens dentro da nova.
        return (*reais, False)
    if config.SENSORES_PLACEHOLDER:    # Sem dados reais, mas a simulação está ligada no config?
        # Gera dados simulados e prepara do mesmo jeito que os reais.
        df, rel = _preparar(simular(clima), ["DADOS SIMULADOS (placeholder)"])
        return df, rel, True           # O True avisa o painel que os dados são simulados.
    return None                        # Nem dados reais nem simulação: nada a mostrar.


# --------------------------------------------------------- dados simulados
def simular(clima: pd.DataFrame, semente: int = 7) -> pd.DataFrame:
    """PLACEHOLDER — leituras horárias FICTÍCIAS no formato dos CSVs reais.

    >>> APAGUE ou ignore esta função quando houver dados reais. <<<
    Ela só é chamada por `obter` quando data/sensores/ está vazia.

    Como é feita: para cada dia do último verão (dez–mar) da Open-Meteo, a
    temperatura horária segue uma curva com mínima às 6h e máxima às 15h;
    cada sensor ganha o excesso de calor de config.PLACEHOLDER_EXCESSO (mais
    na tarde, menos na madrugada) e ruído. A umidade cai quando esquenta.
    Também são inseridos erros de propósito (leituras impossíveis, lacunas e
    um sensor em Fahrenheit) para mostrar a limpeza funcionando.
    """
    # Gerador de números aleatórios. A "semente" fixa garante que a simulação saia
    # IGUAL toda vez que rodar (resultado reprodutível).
    rng = np.random.default_rng(semente)
    c = clima.dropna(subset=["tmax", "tmin"])     # Só dias com máxima e mínima preenchidas.
    verao = c[c["mes"].isin([12, 1, 2, 3])]       # Só dezembro, janeiro, fevereiro e março.
    # último verão completo: dezembro de um ano até março do seguinte
    fim_verao = verao[verao["mes"] == 3]["data"].max()   # O último dia de março disponível.
    # Início = 1º de dezembro do ano ANTERIOR a esse março.
    ini_verao = pd.Timestamp(year=fim_verao.year - 1, month=12, day=1)
    dias = c[(c["data"] >= ini_verao) & (c["data"] <= fim_verao)]   # Os dias desse verão.

    horas = np.arange(24)              # Array com as horas do dia: [0, 1, 2, …, 23].
    # forma da curva diária: 0 às 6h, 1 às 15h (seno), descendo à noite
    # np.sin(...) faz a curva subir e descer; np.clip(..., 0, None) corta os valores negativos em 0.
    forma = np.clip(np.sin(np.pi * (horas - 6) / 18), 0, None)
    # Entre 0h e 5h, a curva desce devagar de 0,25 até 0 (a madrugada ainda guarda um pouco de calor).
    forma = np.where(horas < 6, (6 - horas) / 6 * 0.25, forma)    # madrugada ainda morna

    partes = []                        # Uma tabela por sensor por dia; juntamos no final.
    # Para cada sensor simulado: sid = nome; (exc_max, exc_min) = quanto ele é mais quente
    # que a Open-Meteo na hora mais quente e na mais fria.
    for sid, (exc_max, exc_min) in config.PLACEHOLDER_EXCESSO.items():
        for _, d in dias.iterrows():   # Percorre os dias, um por um (d = a linha do dia; "_" = número ignorado).
            # Temperatura "base" de cada hora: vai da mínima (forma=0) até a máxima (forma=1).
            base = d["tmin"] + (d["tmax"] - d["tmin"]) * forma
            # Excesso de calor do sensor em cada hora: menor de madrugada, maior à tarde.
            excesso = exc_min + (exc_max - exc_min) * forma
            # Temperatura final = base + excesso + um pequeno ruído aleatório (média 0, desvio 0,4 °C).
            temp = base + excesso + rng.normal(0, 0.4, 24)
            # Umidade: ~80% quando está fresco, caindo até ~38% no pico do calor, com ruído.
            # np.clip limita entre 15% e 100%.
            umid = np.clip(80 - 42 * forma + rng.normal(0, 4, 24), 15, 100)
            # Monta a tabela das 24 leituras daquele sensor naquele dia, no MESMO formato dos CSVs reais.
            partes.append(pd.DataFrame({
                "sensor_id": sid,
                # Data do dia + cada hora (to_timedelta(horas, "h")), escrita como texto "dd/mm/aaaa hh:mm".
                "timestamp": (d["data"] + pd.to_timedelta(horas, "h")).strftime("%d/%m/%Y %H:%M"),
                # .round(1) = 1 casa decimal; .round(0) = número redondo.
                "temperatura": temp.round(1), "umidade": umid.round(0), "unidade_temp": "C"}))
    df = pd.concat(partes, ignore_index=True)    # Junta tudo numa tabela só.

    # erros de propósito, para a limpeza ter o que corrigir
    # rng.choice(len(df), 12, replace=False) sorteia 12 linhas diferentes; nelas a temperatura vira 85 °C.
    df.loc[rng.choice(len(df), 12, replace=False), "temperatura"] = 85.0       # impossível
    # Sorteia 40 linhas e apaga a temperatura (simula falhas de leitura).
    df.loc[rng.choice(len(df), 40, replace=False), "temperatura"] = np.nan     # lacunas
    # Sensores cujo nome começa com "ipiranga" serão gravados em Fahrenheit.
    controle = df["sensor_id"].str.startswith("ipiranga")                        # sensor em °F
    # Converte a temperatura deles para °F (°F = °C × 9/5 + 32)…
    df.loc[controle, "temperatura"] = df.loc[controle, "temperatura"] * 9 / 5 + 32
    df.loc[controle, "unidade_temp"] = "F"       # …e marca a unidade como "F".
    return df


# ------------------------------------------------------------------ resumos
def eh_heliopolis(sensor_id: pd.Series) -> pd.Series:
    # True para os sensores cujo nome (em minúsculas) começa com o prefixo de Heliópolis (ex.: "heliopolis").
    return sensor_id.astype(str).str.lower().str.startswith(config.PREFIXO_SENSOR_HELIOPOLIS)


# Define diario(): recebe as leituras e devolve uma tabela com 1 linha por sensor por dia.
def diario(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo por sensor e dia: máxima, mínima e índice de calor máximo."""
    # .assign cria uma coluna "data" sem alterar a tabela original.
    # .dt.normalize() zera a hora (15/01 14:00 → 15/01 00:00), deixando só o dia.
    d = df.assign(data=df["timestamp"].dt.normalize())
    # Agrupa por sensor e dia e calcula, para cada grupo:
    out = d.groupby(["sensor_id", "data"]).agg(
        tmax=("temperatura", "max"), tmin=("temperatura", "min"),       # máxima e mínima do dia
        umidade_media=("umidade", "mean"),                              # umidade média
        indice_calor_max=("indice_calor", "max"),                       # pior índice de calor do dia
        leituras=("temperatura", "count")).reset_index()                # quantas leituras válidas
    # Classifica o índice de calor máximo de cada dia numa faixa de risco (pd.cut).
    out["risco"] = pd.cut(out["indice_calor_max"], bins=FAIXAS_RISCO[0],
                          labels=FAIXAS_RISCO[1], right=False)
    return out


# Define comparar_com_openmeteo(): recebe o resumo diário dos sensores e o clima;
# devolve a mesma tabela com as diferenças.
def comparar_com_openmeteo(dia: pd.DataFrame, clima: pd.DataFrame) -> pd.DataFrame:
    """Diferença sensor − Open-Meteo, por dia (positivo = sensor mais quente)."""
    # Junta o resumo diário dos sensores com a máxima e a mínima da Open-Meteo do mesmo dia.
    # suffixes=("", "_openmeteo"): as colunas repetidas da Open-Meteo ganham o final "_openmeteo".
    m = dia.merge(clima[["data", "tmax", "tmin"]], on="data", suffixes=("", "_openmeteo"))
    m["dif_tmax"] = m["tmax"] - m["tmax_openmeteo"]   # Diferença na máxima (sensor − Open-Meteo).
    m["dif_tmin"] = m["tmin"] - m["tmin_openmeteo"]   # Diferença na mínima.
    return m


# Define horas_em_risco(): recebe as leituras e devolve uma tabela sensor × faixa × horas por dia.
def horas_em_risco(df: pd.DataFrame) -> pd.DataFrame:
    """Média de horas por dia em cada faixa de risco do índice de calor, por sensor.

    O intervalo entre leituras é descoberto sozinho (mediana dos intervalos),
    então funciona para sensores que medem a cada hora, 10 min, etc.
    """
    # Lista vazia onde vamos acumular os resultados (cada item vira uma linha da tabela final).
    linhas = []
    # Remove leituras sem índice de calor e percorre sensor por sensor (sid = nome; g = as leituras dele).
    for sid, g in df.dropna(subset=["indice_calor"]).groupby("sensor_id"):
        # Intervalo típico entre leituras: ordena os horários, calcula a diferença entre leituras
        # seguidas (.diff()) e pega a mediana (ex.: 1 hora ou 10 minutos).
        passo = g["timestamp"].sort_values().diff().median()
        # Converte o intervalo em horas (10 min → 0,1667 h). Se não der para calcular, assume 1 hora.
        horas_por_leitura = passo / pd.Timedelta(hours=1) if pd.notna(passo) else 1.0
        n_dias = g["timestamp"].dt.normalize().nunique()   # Em quantos dias diferentes o sensor mediu.
        # Classifica cada leitura numa faixa de risco.
        faixa = pd.cut(g["indice_calor"], bins=FAIXAS_RISCO[0], labels=FAIXAS_RISCO[1],
                       right=False)
        # Conta quantas leituras caíram em cada faixa; reindex garante todas as faixas (as sem leitura ficam 0).
        cont = faixa.value_counts().reindex(FAIXAS_RISCO[1], fill_value=0)
        for nome, n in cont.items():   # Para cada faixa (nome) e sua contagem (n)…
            # …horas por dia = nº de leituras × horas por leitura ÷ nº de dias.
            linhas.append({"sensor_id": sid, "faixa": nome,
                           "horas_dia": n * horas_por_leitura / max(n_dias, 1)})
    return pd.DataFrame(linhas)


# Define perfil_horario(): recebe as leituras e devolve a temperatura média por hora e sensor.
def perfil_horario(df: pd.DataFrame) -> pd.DataFrame:
    """Temperatura média em cada hora do dia, por sensor (mostra se a noite esfria)."""
    d = df.assign(hora=df["timestamp"].dt.hour)   # Nova coluna com só a hora (0 a 23).
    # Média da temperatura para cada combinação sensor × hora.
    return d.groupby(["sensor_id", "hora"])["temperatura"].mean().reset_index()


# --------------------------------------------- calibração da Open-Meteo
def calibrar(dia: pd.DataFrame, clima: pd.DataFrame) -> dict | None:
    """Quanto Heliópolis é mais quente que a Open-Meteo (máxima e mínima).

    Usa só os sensores DENTRO de Heliópolis (prefixo em config) e só os dias
    com leituras suficientes (≥ 18 horas). A correção é um valor fixo (média
    das diferenças): com poucos meses de dados, é mais seguro que uma
    regressão. O desvio-padrão mostra o quanto a diferença varia de dia para dia.
    """
    # Filtra: sensores de Heliópolis E dias com pelo menos 18 leituras (dia quase completo).
    h = dia[eh_heliopolis(dia["sensor_id"]) & (dia["leituras"] >= 18)]
    if h.empty:                        # Nenhum dado útil?
        return None                    # Sem calibração.
    # Se houver vários sensores em Heliópolis, tira a média entre eles para cada dia.
    media_dia = h.groupby("data")[["tmax", "tmin"]].mean().reset_index()   # média entre sensores
    # Junta com a Open-Meteo do mesmo dia (colunas dela terminam em "_om") e remove dias com vazio.
    m = media_dia.merge(clima[["data", "tmax", "tmin"]], on="data", suffixes=("", "_om")).dropna()
    if len(m) < MINIMO_DIAS_CALIBRACAO:   # Menos de 14 dias: pouco para confiar.
        return None
    # Diferenças diárias (sensores − Open-Meteo) na máxima e na mínima.
    dmax, dmin = m["tmax"] - m["tmax_om"], m["tmin"] - m["tmin_om"]
    # Devolve:
    #   delta_tmax / delta_tmin → diferença MÉDIA (é a correção aplicada);
    #   dp_tmax / dp_tmin       → desvio-padrão (quanto a diferença oscila de um dia para outro);
    #   dias                    → quantos dias entraram na conta;
    #   sensores                → quais sensores foram usados;
    #   pares                   → a tabela dia a dia (para o gráfico de pontos).
    return {"delta_tmax": float(dmax.mean()), "delta_tmin": float(dmin.mean()),
            "dp_tmax": float(dmax.std()), "dp_tmin": float(dmin.std()), "dias": len(m),
            "sensores": sorted(h["sensor_id"].unique()), "pares": m}


# Define corrigir(): recebe o clima e a calibração; devolve a série de clima corrigida.
def corrigir(clima: pd.DataFrame, calib: dict) -> pd.DataFrame:
    """Série 'Heliópolis corrigida': Open-Meteo + diferenças medidas pelos sensores.

    A sensação térmica recebe a mesma correção da máxima. Limitação: a
    diferença é medida no verão dos sensores e aplicada a todos os anos.
    Depois de corrigir, chame clima.marcar_calor(..., lim=<limiares regionais>)
    para manter a MESMA régua de calor da Open-Meteo.
    """
    c = clima.copy()                   # Cópia, para não alterar a série original.
    c["tmax"] = c["tmax"] + calib["delta_tmax"]   # Soma a diferença média à máxima de TODOS os dias.
    c["tmin"] = c["tmin"] + calib["delta_tmin"]   # Soma a diferença média à mínima.
    # A média do dia recebe a média das duas correções.
    c["tmedia"] = c["tmedia"] + (calib["delta_tmax"] + calib["delta_tmin"]) / 2
    # A sensação térmica máxima recebe a mesma correção da máxima.
    c["sensacao_max"] = c["sensacao_max"] + calib["delta_tmax"]
    return c


def modelo_csv() -> str:               # Devolve o TEXTO de um CSV de exemplo (para o botão "baixar modelo").
    """Arquivo-modelo (só o formato, com valores fictícios) para a equipe preencher."""
    # Strings coladas umas nas outras. "\n" = quebra de linha. 1ª linha = cabeçalho;
    # as outras são exemplos (inclusive um sensor em Fahrenheit e outro formato de data).
    return ("sensor_id;timestamp;temperatura;umidade;unidade_temp\n"
            "heliopolis_01;15/01/2026 14:00;33,1;58;C\n"
            "heliopolis_01;15/01/2026 15:00;34,0;55;C\n"
            "ipiranga_controle_01;2026-01-15 14:00;91,4;60;F\n")
