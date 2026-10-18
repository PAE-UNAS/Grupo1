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
DIA_MUITO_QUENTE = 32.0      # °C de máxima
ONDA_PERCENTIL = 90          # onda de calor: máxima acima do P90 do mês...
ONDA_DIAS = 3                # ...por pelo menos 3 dias seguidos
MESES_QUENTES = [11, 12, 1, 2, 3]   # novembro a março

# Saúde
DIAS_DEPOIS = 2              # o efeito do calor aparece no dia e até ~2 dias depois
ANOS_PANDEMIA = [2020, 2021] # internações caíram/mudaram muito; ficam fora por padrão
