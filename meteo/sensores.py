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
from __future__ import annotations

import numpy as np
import pandas as pd

from meteo import config
from meteo.limpeza import limpar

COLUNAS = ["sensor_id", "timestamp", "temperatura", "umidade", "unidade_temp"]

# Faixas de risco do Índice de Calor (NOAA/Serviço Meteorológico dos EUA), em °C
FAIXAS_RISCO = ([-np.inf, 27, 32, 41, 54, np.inf],
                ["sem risco", "cautela", "cautela extrema", "perigo", "perigo extremo"])

MINIMO_DIAS_CALIBRACAO = 14   # menos que isso: a correção não é calculada


def indice_calor(temp_c, umid):
    """Índice de calor da NOAA (Rothfusz, com os ajustes oficiais), em °C.

    Combina temperatura e umidade: com o ar úmido o suor evapora menos e o
    corpo sente mais calor. Abaixo de ~27 °C usa a fórmula simplificada.
    """
    t = np.asarray(temp_c, dtype=float) * 9 / 5 + 32
    rh = np.asarray(umid, dtype=float)
    simples = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - .22475541 * t * rh
          - .00683783 * t ** 2 - .05481717 * rh ** 2 + .00122874 * t ** 2 * rh
          + .00085282 * t * rh ** 2 - .00000199 * t ** 2 * rh ** 2)
    with np.errstate(invalid="ignore"):
        seco = (rh < 13) & (t >= 80) & (t <= 112)
        hi = np.where(seco, hi - ((13 - rh) / 4) * np.sqrt((17 - np.abs(t - 95)) / 17), hi)
    umido = (rh > 85) & (t >= 80) & (t <= 87)
    hi = np.where(umido, hi + ((rh - 85) / 10) * ((87 - t) / 5), hi)
    hi = np.where((simples + t) / 2 < 80, simples, hi)
    return (hi - 32) * 5 / 9


# ------------------------------------------------------------------- leitura
def arquivos() -> list:
    return sorted(config.SENSORES.glob("*.csv")) if config.SENSORES.exists() else []


def _preparar(bruto: pd.DataFrame, nomes: list[str]) -> tuple[pd.DataFrame, dict]:
    """Limpeza (meteo.limpeza) + índice de calor. Igual para dados reais e simulados."""
    for c in ("temperatura", "umidade"):          # aceita vírgula decimal (Excel em português)
        if c in bruto and not pd.api.types.is_numeric_dtype(bruto[c]):
            bruto[c] = bruto[c].astype(str).str.replace(",", ".", regex=False)
    faltando = [c for c in COLUNAS[:4] if c not in bruto]
    if faltando:
        raise ValueError(f"Faltam colunas nos arquivos de sensores: {', '.join(faltando)}")
    df, relatorio = limpar(bruto)
    df["indice_calor"] = indice_calor(df["temperatura"], df["umidade"])
    relatorio["arquivos"] = nomes
    return df, relatorio


def carregar() -> tuple[pd.DataFrame, dict] | None:
    """DADOS REAIS: lê todos os CSVs de data/sensores/ (None se não houver)."""
    lista = arquivos()
    if not lista:
        return None
    partes = [pd.read_csv(a, sep=None, engine="python", dtype={"sensor_id": str}) for a in lista]
    return _preparar(pd.concat(partes, ignore_index=True), [a.name for a in lista])


def obter(clima: pd.DataFrame) -> tuple[pd.DataFrame, dict, bool] | None:
    """Ponto único de entrada usado pelo app: (dados, relatório, é_simulado).

    Ordem de prioridade:
      1. dados reais em data/sensores/  -> é_simulado = False
      2. sem arquivos e SENSORES_PLACEHOLDER = True -> dados simulados (é_simulado = True)
      3. sem arquivos e SENSORES_PLACEHOLDER = False -> None (abas mostram instruções)
    """
    reais = carregar()
    if reais is not None:
        return (*reais, False)
    if config.SENSORES_PLACEHOLDER:
        df, rel = _preparar(simular(clima), ["DADOS SIMULADOS (placeholder)"])
        return df, rel, True
    return None


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
    rng = np.random.default_rng(semente)
    c = clima.dropna(subset=["tmax", "tmin"])
    verao = c[c["mes"].isin([12, 1, 2, 3])]
    # último verão completo: dezembro de um ano até março do seguinte
    fim_verao = verao[verao["mes"] == 3]["data"].max()
    ini_verao = pd.Timestamp(year=fim_verao.year - 1, month=12, day=1)
    dias = c[(c["data"] >= ini_verao) & (c["data"] <= fim_verao)]

    horas = np.arange(24)
    # forma da curva diária: 0 às 6h, 1 às 15h (seno), descendo à noite
    forma = np.clip(np.sin(np.pi * (horas - 6) / 18), 0, None)
    forma = np.where(horas < 6, (6 - horas) / 6 * 0.25, forma)    # madrugada ainda morna

    partes = []
    for sid, (exc_max, exc_min) in config.PLACEHOLDER_EXCESSO.items():
        for _, d in dias.iterrows():
            base = d["tmin"] + (d["tmax"] - d["tmin"]) * forma
            excesso = exc_min + (exc_max - exc_min) * forma
            temp = base + excesso + rng.normal(0, 0.4, 24)
            umid = np.clip(80 - 42 * forma + rng.normal(0, 4, 24), 15, 100)
            partes.append(pd.DataFrame({
                "sensor_id": sid,
                "timestamp": (d["data"] + pd.to_timedelta(horas, "h")).strftime("%d/%m/%Y %H:%M"),
                "temperatura": temp.round(1), "umidade": umid.round(0), "unidade_temp": "C"}))
    df = pd.concat(partes, ignore_index=True)

    # erros de propósito, para a limpeza ter o que corrigir
    df.loc[rng.choice(len(df), 12, replace=False), "temperatura"] = 85.0       # impossível
    df.loc[rng.choice(len(df), 40, replace=False), "temperatura"] = np.nan     # lacunas
    controle = df["sensor_id"].str.startswith("ipiranga")                        # sensor em °F
    df.loc[controle, "temperatura"] = df.loc[controle, "temperatura"] * 9 / 5 + 32
    df.loc[controle, "unidade_temp"] = "F"
    return df


# ------------------------------------------------------------------ resumos
def eh_heliopolis(sensor_id: pd.Series) -> pd.Series:
    return sensor_id.astype(str).str.lower().str.startswith(config.PREFIXO_SENSOR_HELIOPOLIS)


def diario(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo por sensor e dia: máxima, mínima e índice de calor máximo."""
    d = df.assign(data=df["timestamp"].dt.normalize())
    out = d.groupby(["sensor_id", "data"]).agg(
        tmax=("temperatura", "max"), tmin=("temperatura", "min"),
        umidade_media=("umidade", "mean"), indice_calor_max=("indice_calor", "max"),
        leituras=("temperatura", "count")).reset_index()
    out["risco"] = pd.cut(out["indice_calor_max"], bins=FAIXAS_RISCO[0],
                          labels=FAIXAS_RISCO[1], right=False)
    return out


def comparar_com_openmeteo(dia: pd.DataFrame, clima: pd.DataFrame) -> pd.DataFrame:
    """Diferença sensor − Open-Meteo, por dia (positivo = sensor mais quente)."""
    m = dia.merge(clima[["data", "tmax", "tmin"]], on="data", suffixes=("", "_openmeteo"))
    m["dif_tmax"] = m["tmax"] - m["tmax_openmeteo"]
    m["dif_tmin"] = m["tmin"] - m["tmin_openmeteo"]
    return m


def horas_em_risco(df: pd.DataFrame) -> pd.DataFrame:
    """Média de horas por dia em cada faixa de risco do índice de calor, por sensor.

    O intervalo entre leituras é descoberto sozinho (mediana dos intervalos),
    então funciona para sensores que medem a cada hora, 10 min, etc.
    """
    linhas = []
    for sid, g in df.dropna(subset=["indice_calor"]).groupby("sensor_id"):
        passo = g["timestamp"].sort_values().diff().median()
        horas_por_leitura = passo / pd.Timedelta(hours=1) if pd.notna(passo) else 1.0
        n_dias = g["timestamp"].dt.normalize().nunique()
        faixa = pd.cut(g["indice_calor"], bins=FAIXAS_RISCO[0], labels=FAIXAS_RISCO[1],
                       right=False)
        cont = faixa.value_counts().reindex(FAIXAS_RISCO[1], fill_value=0)
        for nome, n in cont.items():
            linhas.append({"sensor_id": sid, "faixa": nome,
                           "horas_dia": n * horas_por_leitura / max(n_dias, 1)})
    return pd.DataFrame(linhas)


def perfil_horario(df: pd.DataFrame) -> pd.DataFrame:
    """Temperatura média em cada hora do dia, por sensor (mostra se a noite esfria)."""
    d = df.assign(hora=df["timestamp"].dt.hour)
    return d.groupby(["sensor_id", "hora"])["temperatura"].mean().reset_index()


# --------------------------------------------- calibração da Open-Meteo
def calibrar(dia: pd.DataFrame, clima: pd.DataFrame) -> dict | None:
    """Quanto Heliópolis é mais quente que a Open-Meteo (máxima e mínima).

    Usa só os sensores DENTRO de Heliópolis (prefixo em config) e só os dias
    com leituras suficientes (≥ 18 horas). A correção é um valor fixo (média
    das diferenças): com poucos meses de dados, é mais seguro que uma
    regressão. O desvio-padrão mostra o quanto a diferença varia de dia para dia.
    """
    h = dia[eh_heliopolis(dia["sensor_id"]) & (dia["leituras"] >= 18)]
    if h.empty:
        return None
    media_dia = h.groupby("data")[["tmax", "tmin"]].mean().reset_index()   # média entre sensores
    m = media_dia.merge(clima[["data", "tmax", "tmin"]], on="data", suffixes=("", "_om")).dropna()
    if len(m) < MINIMO_DIAS_CALIBRACAO:
        return None
    dmax, dmin = m["tmax"] - m["tmax_om"], m["tmin"] - m["tmin_om"]
    return {"delta_tmax": float(dmax.mean()), "delta_tmin": float(dmin.mean()),
            "dp_tmax": float(dmax.std()), "dp_tmin": float(dmin.std()), "dias": len(m),
            "sensores": sorted(h["sensor_id"].unique()), "pares": m}


def corrigir(clima: pd.DataFrame, calib: dict) -> pd.DataFrame:
    """Série 'Heliópolis corrigida': Open-Meteo + diferenças medidas pelos sensores.

    A sensação térmica recebe a mesma correção da máxima. Limitação: a
    diferença é medida no verão dos sensores e aplicada a todos os anos.
    Depois de corrigir, chame clima.marcar_calor(..., lim=<limiares regionais>)
    para manter a MESMA régua de calor da Open-Meteo.
    """
    c = clima.copy()
    c["tmax"] = c["tmax"] + calib["delta_tmax"]
    c["tmin"] = c["tmin"] + calib["delta_tmin"]
    c["tmedia"] = c["tmedia"] + (calib["delta_tmax"] + calib["delta_tmin"]) / 2
    c["sensacao_max"] = c["sensacao_max"] + calib["delta_tmax"]
    return c


def modelo_csv() -> str:
    """Arquivo-modelo (só o formato, com valores fictícios) para a equipe preencher."""
    return ("sensor_id;timestamp;temperatura;umidade;unidade_temp\n"
            "heliopolis_01;15/01/2026 14:00;33,1;58;C\n"
            "heliopolis_01;15/01/2026 15:00;34,0;55;C\n"
            "ipiranga_controle_01;2026-01-15 14:00;91,4;60;F\n")
