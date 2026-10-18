"""Testes dos tratamentos de dados. Rodar:  python -m pytest"""
import numpy as np
import pandas as pd

from meteo import clima, cruzamento, saude, sensores
from meteo.limpeza import limpar


def test_limpeza_converte_fahrenheit_remove_outliers_e_interpola():
    df = pd.DataFrame({
        "sensor_id": ["a"] * 5 + ["b"] * 2,
        "timestamp": ["01/02/2026 10:00", "01/02/2026 11:00", "01/02/2026 12:00",
                      "01/02/2026 13:00", "01/02/2026 13:00", "2026-02-01 10:00",
                      "2026-02-01 11:00"],
        "temperatura": [30, 99, np.nan, 33, 33, 86, 88],
        "umidade": [60, 60, 60, 60, 60, 120, 50],
        "unidade_temp": ["C"] * 5 + ["F"] * 2,
    })
    limpo, rel = limpar(df)
    assert rel["sensores_em_fahrenheit"] == 1
    assert rel["outliers_removidos"] == 2              # 99 °C e 120% de umidade
    assert len(limpo) == 6                             # leitura repetida removida
    a = limpo[limpo["sensor_id"] == "a"]["temperatura"].tolist()
    assert a == [30, 31, 32, 33]                       # lacuna interpolada
    b = limpo[limpo["sensor_id"] == "b"]["temperatura"].round(1).tolist()
    assert b == [30.0, 31.1]                           # °F -> °C


def test_indice_de_calor_bate_com_a_tabela_da_noaa():
    # Tabela NOAA: 86 °F (30 °C) com 70% de umidade -> 95 °F (35 °C)
    assert round(float(sensores.indice_calor(30, 70)), 0) == 35
    # Com tempo ameno o índice fica perto da temperatura
    assert abs(float(sensores.indice_calor(22, 50)) - 22) < 1.5


def test_onda_de_calor_exige_dias_seguidos():
    quente = pd.Series([True, True, False, True, True, True, False])
    assert clima._ondas(quente, 3).tolist() == [False, False, False, True, True, True, False]


def test_feriados_incluem_carnaval_e_fim_de_ano():
    datas = pd.Series(pd.to_datetime(["2024-02-13", "2024-12-26", "2024-03-05"]))
    assert cruzamento.feriados(datas).tolist() == [True, True, False]


def test_recortes_e_grupos_das_internacoes():
    bruto = pd.DataFrame({
        "N_AIH": ["1", "2", "3", "3"], "MUNIC_RES": ["355030"] * 4,
        "CEP": ["04230010", "04250000", "05010000", "05010000"],
        "DT_INTER": ["20240110"] * 4, "DIAG_PRINC": ["J189", "A09", "N179", "N179"],
        "IDADE": ["70", "5", "30", "30"], "COD_IDADE": ["4"] * 4, "MORTE": ["1", "0", "0", "0"]})
    t = saude.tratar(bruto)
    assert len(t) == 3                                         # AIH repetida
    assert t["heliopolis"].tolist() == [True, False, False]
    assert t["regiao"].tolist() == [True, True, False]         # região inclui Heliópolis
    assert t["cidade"].all()
    assert t["obitos"].tolist() == [True, False, False]
    assert t["criancas"].tolist() == [False, True, False]
    assert t["gastro"].tolist() == [False, True, False]


def _clima_teste():
    dias = pd.date_range("2024-11-01", "2025-04-30")
    t = pd.DataFrame({"data": dias, "tmax": 30.0, "tmin": 20.0, "tmedia": 25.0,
                      "sensacao_max": 32.0, "chuva": 5.0})
    t["ano"], t["mes"] = t["data"].dt.year, t["data"].dt.month
    return t


def test_placeholder_dos_sensores_e_calibracao():
    clima_t = _clima_teste()
    df, rel, simulado = sensores.obter(clima_t) if not sensores.arquivos() else (None, None, None)
    if df is None:            # há CSVs reais na pasta: o teste do placeholder não se aplica
        return
    assert simulado and rel["sensores_em_fahrenheit"] == 1 and rel["outliers_removidos"] == 12
    calib = sensores.calibrar(sensores.diario(df), clima_t)
    # sensores simulados de Heliópolis ficam ~2,5–3,5 °C acima na máxima e ~1,2–1,8 na mínima
    assert 2 < calib["delta_tmax"] < 4.5 and 0.8 < calib["delta_tmin"] < 2.5
    assert "ipiranga_controle_01" not in calib["sensores"]          # controle fica de fora
    corrigido = sensores.corrigir(clima_t, calib)
    assert np.allclose(corrigido["tmax"] - clima_t["tmax"], calib["delta_tmax"])


def test_grupo_arboviroses():
    bruto = pd.DataFrame({
        "N_AIH": ["1", "2", "3"], "MUNIC_RES": ["355030"] * 3, "CEP": ["04230010"] * 3,
        "DT_INTER": ["20240110"] * 3, "DIAG_PRINC": ["A90", "A920", "J189"],
        "IDADE": ["30"] * 3, "COD_IDADE": ["4"] * 3, "MORTE": ["0"] * 3})
    assert saude.tratar(bruto)["arboviroses"].tolist() == [True, True, False]
