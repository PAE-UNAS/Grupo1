"""Testes dos tratamentos de dados. Rodar:  python -m pytest"""
import numpy as np
import pandas as pd

from meteo import clima, cruzamento, indices, saude
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
    assert round(float(indices.indice_calor(30, 70)), 0) == 35
    # Com tempo ameno o índice fica perto da temperatura
    assert abs(float(indices.indice_calor(22, 50)) - 22) < 1.5


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


def test_wbgt_fica_abaixo_da_temperatura_com_ar_seco():
    assert float(indices.wbgt_aproximado(30, 40)) < 30


def test_faixas_de_risco():
    assert indices.classificar(pd.Series([25, 30, 35])).tolist() == [
        "Sem alerta", "Atenção", "Cautela extrema"]
