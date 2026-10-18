"""Parâmetros do projeto. Para mudar um critério, mude aqui."""
from pathlib import Path

# Território
LATITUDE = -23.6105          # ponto central de Heliópolis
LONGITUDE = -46.5925
FUSO = "America/Sao_Paulo"
MUNICIPIO_SP = "355030"      # código IBGE (6 dígitos) usado pelo DATASUS

# CEPs de Heliópolis (5 primeiros dígitos), segundo os Correios para os bairros
# Cidade Nova Heliópolis e Vila Heliópolis. Algumas ruas vizinhas do Sacomã
# compartilham esses prefixos: vale conferir com o Observatório De Olho na Quebrada.
CEPS_HELIOPOLIS = ["04229", "04230", "04231", "04233", "04235", "04236", "04239"]

# Pastas
RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "data" / "cache"

# Clima
CLIMATOLOGIA = (1991, 2020)  # período de referência (padrão da OMM)
# Dia de calor = sensação térmica máxima entre os 10% mais altos do período
PERCENTIL_DIA_CALOR = 90
MESES_QUENTES = [11, 12, 1, 2, 3]   # novembro a março

# População (Censo 2022, IBGE) — para calcular internações por 100 mil habitantes
POP_SP = 11_451_245
# 55.583 é a população da favela de Heliópolis no Censo 2022. A área dos CEPs
# pode ser maior (o Observatório estima até 200 mil). O app permite ajustar.
POP_HELIOPOLIS = 55_583

# Saúde
DIAS_DEPOIS = 2              # o efeito do calor aparece no dia e até ~2 dias depois
ANOS_PANDEMIA = [2020, 2021] # internações caíram/mudaram muito; ficam fora por padrão
