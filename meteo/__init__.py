"""Calor e saúde em Heliópolis: clima (Open-Meteo) × internações no SUS (DATASUS/SIH).

Módulos:
    config      parâmetros e critérios (tudo que é escolha da equipe)
    clima       download, tratamento e indicadores de calor (Open-Meteo)
    saude       download e tratamento das internações (DATASUS/SIH)
    cruzamento  clima × internações: normal esperado, comparações e conclusões
    limpeza     limpeza de séries de sensores (temperatura e umidade)
    sensores    sensores da UNAS: leitura, simulação (placeholder), índice de calor, calibração
"""
