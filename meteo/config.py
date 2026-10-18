"""Parâmetros do projeto. Para mudar um critério, mude aqui.

Tudo que é uma ESCOLHA da equipe (limiares, recortes, populações, períodos)
fica neste arquivo, com a justificativa ao lado. O resto do código só lê
estes valores.
"""
from pathlib import Path

# ----------------------------------------------------------------- território
LATITUDE = -23.6105          # ponto central de Heliópolis
LONGITUDE = -46.5925
FUSO = "America/Sao_Paulo"
MUNICIPIO_SP = "355030"      # código IBGE (6 dígitos) usado pelo DATASUS
# Municípios de residência lidos dos arquivos do SIH. Para incluir São Caetano
# do Sul, acrescente "354880" e crie um recorte para ele em RECORTES (abaixo).
# Atenção: mudar esta lista exige apagar data/cache/internacoes_*.parquet,
# porque o filtro é aplicado na hora do download.
MUNICIPIOS = [MUNICIPIO_SP]

# CEPs de Heliópolis (5 primeiros dígitos), segundo os Correios para os bairros
# Cidade Nova Heliópolis e Vila Heliópolis. Algumas ruas vizinhas do Sacomã
# compartilham esses prefixos: vale conferir com o Observatório De Olho na Quebrada.
CEPS_HELIOPOLIS = ["04229", "04230", "04231", "04233", "04235", "04236", "04239"]

# Região do Ipiranga = CEPs que começam com 042 (setor postal que cobre os
# bairros do Ipiranga e do Sacomã, onde fica Heliópolis). Heliópolis tem poucas
# internações por dia, o que deixa os resultados instáveis. A região tem ~10×
# mais casos, inclui Heliópolis e vive o mesmo clima: se as internações sobem na
# região nos dias de calor, é provável que subam também em Heliópolis.
CEPS_REGIAO = ["042"]

# Recortes usados nas análises (um paciente pode estar em mais de um:
# Heliópolis está dentro da região, que está dentro da cidade).
RECORTES = {
    "heliopolis": "Heliópolis",
    "regiao": "Região do Ipiranga",
    "cidade": "Cidade de SP",
}

# ------------------------------------------------------------------- pastas
RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "data" / "cache"
SENSORES = RAIZ / "data" / "sensores"   # CSVs dos sensores da UNAS (quando houver)

# ------------------------------------------------------- sensores da UNAS
# >>> PARA USAR OS DADOS REAIS: basta colocar os CSVs em data/sensores/.
#     Os dados simulados abaixo deixam de ser usados automaticamente.
#     Na versão final (sem nenhuma simulação), mude para False. <<<
SENSORES_PLACEHOLDER = True
# Sensores cujo nome começa com este prefixo contam como DENTRO de Heliópolis
# (são os únicos usados para calibrar a Open-Meteo). Os demais são controle.
PREFIXO_SENSOR_HELIOPOLIS = "heliopolis"
# Só usado pela SIMULAÇÃO: quantos °C cada sensor fictício fica acima da
# Open-Meteo (na hora mais quente, na madrugada). Valores INVENTADOS para
# ilustrar; apague quando houver dados reais.
PLACEHOLDER_EXCESSO = {
    "heliopolis_viela_01": (2.5, 1.8),
    "heliopolis_laje_02": (3.5, 1.2),
    "ipiranga_controle_01": (0.4, 0.3),
}

# -------------------------------------------------------------------- clima
CLIMATOLOGIA = (1991, 2020)  # período de referência para definir "calor" (padrão da OMM)
# Limiares = percentil 90 do período de referência, só nos meses quentes.
# Assim "dia de calor" quer dizer a mesma coisa em qualquer ano analisado.
PERCENTIL_DIA_CALOR = 90
MESES_QUENTES = [11, 12, 1, 2, 3]   # novembro a março
DIAS_ONDA = 3                        # onda de calor = 3+ dias quentes seguidos

# Formas de medir o calor. "var" = coluna da tabela de clima.
CRITERIOS = {
    "dia_quente": {"nome": "Dia quente", "plural": "Dias quentes", "var": "sensacao_max",
                   "texto": "sensação térmica máxima"},
    "noite_quente": {"nome": "Noite quente", "plural": "Noites quentes", "var": "tmin",
                     "texto": "temperatura mínima (madrugada)"},
    "onda_calor": {"nome": f"Onda de calor ({DIAS_ONDA}+ dias)",
                   "plural": "Dias em onda de calor", "var": "sensacao_max",
                   "texto": f"sensação térmica máxima por {DIAS_ONDA} dias seguidos ou mais"},
}

# --------------------------------------------------------------- população
# Censo 2022 (IBGE) — para calcular internações por 100 mil habitantes
POP_SP = 11_451_245
# 55.583 é a população da favela de Heliópolis no Censo 2022. A área dos CEPs
# pode ser maior (o Observatório estima até 200 mil). O app permite ajustar.
POP_HELIOPOLIS = 55_583
# A população exata dos CEPs 042 não é publicada, por isso a região não
# aparece no gráfico de taxa por 100 mil (só nos gráficos de variação %).

# ------------------------------------------------------------------- saúde
DIAS_DEPOIS = 2              # o efeito do calor aparece no dia e até ~2 dias depois
MAX_DEFASAGEM = 7            # gráfico "quando o efeito aparece": 0 a 7 dias
ANOS_PANDEMIA = [2020, 2021] # internações caíram/mudaram muito; ficam fora por padrão
