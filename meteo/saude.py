"""Saúde — DATASUS, Sistema de Informações Hospitalares do SUS (SIH).

Cada internação paga pelo SUS gera uma AIH (Autorização de Internação
Hospitalar) com: data de entrada, diagnóstico (CID-10), idade e o CEP DE
RESIDÊNCIA do paciente. É o CEP que permite separar os moradores de Heliópolis.

O DATASUS publica um arquivo por estado e por mês de processamento:
    ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RDSP2401.dbc

Cuidados:
- O mês do arquivo é o mês em que o hospital COBROU, não o da internação.
  Uma internação de dezembro pode aparecer no arquivo de fevereiro. Por isso
  baixamos os meses do ano e mais 3 meses seguintes, e usamos DT_INTER.
- Só entram internações de URGÊNCIA (CAR_INT = 02). Cirurgias marcadas
  (eletivas) não têm relação com o calor e variam com o dia da semana.
- Só a AIH principal (IDENT = 1), para não contar a mesma pessoa duas vezes.
"""
# ↑ Docstring do módulo: explica o arquivo. Não executa nada.

# Permite dicas de tipo modernas (ex.: "list[str]") em qualquer versão do Python 3.
from __future__ import annotations

import ftplib              # Biblioteca padrão para acessar servidores FTP (é onde o DATASUS publica os arquivos).
import re                  # Expressões regulares: procurar padrões em textos (ex.: "RDSP" + 4 dígitos).
from pathlib import Path   # Path: representa caminhos de arquivos/pastas de forma prática.

import numpy as np         # NumPy: contas e escolhas condicionais em listas de números.
import pandas as pd        # Pandas: tabelas (DataFrames).
from dbfread import DBF    # Lê arquivos .dbf (formato de tabela antigo usado pelo DATASUS).
from pyreaddbc import dbc2dbf   # Converte .dbc (formato compactado do DATASUS) para .dbf.

from meteo import config   # Configurações do projeto (CEPs, municípios, pasta de cache…).

SERVIDOR = "ftp.datasus.gov.br"                     # Endereço do servidor FTP do DATASUS.
PASTA = "/dissemin/publicos/SIHSUS/200801_/Dados"   # Pasta onde ficam os arquivos de internações.
# Colunas que vamos guardar de cada internação (o arquivo original tem ~100):
#   N_AIH      → número da internação (identificador único)
#   MUNIC_RES  → código do município onde o paciente mora
#   CEP        → CEP de residência do paciente
#   DT_INTER   → data da internação (AAAAMMDD)
#   DIAG_PRINC → diagnóstico principal (código CID-10)
#   IDADE e COD_IDADE → idade e a unidade dela (anos, meses, dias…)
#   MORTE      → 1 se o paciente morreu no hospital, 0 se não
COLUNAS = ["N_AIH", "MUNIC_RES", "CEP", "DT_INTER", "DIAG_PRINC", "IDADE", "COD_IDADE",
           "MORTE"]
# Quantos meses DEPOIS do fim do ano ainda podem chegar internações daquele ano (atraso de cobrança).
MESES_DE_ATRASO = 3

# Grupos escolhidos a partir do que a literatura encontra no Brasil: o estudo
# Fiocruz/UFBA (2026) sobre ondas de calor de 2000 a 2019 achou mais
# internações respiratórias e renais, gastroenterite em crianças e maior
# sensibilidade de idosos.
# Dicionário: código interno do grupo → nome mostrado no painel.
GRUPOS = {
    "todas": "Todas as internações de urgência",
    "respiratorio": "Doenças respiratórias",
    "circulatorio": "Coração e circulação",
    "rins_desidratacao": "Rins, desidratação e insolação",
    "gastro": "Diarreia e gastroenterite",
    # Grupos por idade e desfecho (definidos na função tratar, mais abaixo):
    "idosos": "Pessoas com 65 anos ou mais",
    "criancas": "Crianças de 0 a 9 anos",
    "obitos": "Internações que terminaram em morte",
    # Arboviroses respondem à temperatura MÉDIA e à chuva com semanas de atraso
    # (ciclo do mosquito), não ao dia quente. Por isso têm análise mensal própria
    # (cruzamento.arboviroses_mensal) e não aparecem no seletor de grupos do app.
    "arboviroses": "Dengue, chikungunya e zika (arboviroses)",
}
# Lista dos grupos que aparecem no seletor do painel: todos menos "arboviroses".
GRUPOS_DIARIOS = [g for g in GRUPOS if g != "arboviroses"]
# Os lugares analisados (heliopolis, regiao, cidade) vêm do config; aqui só criamos um atalho.
RECORTES = config.RECORTES


# ------------------------------------------------------------------ download
def meses_disponiveis() -> list[str]:   # Devolve uma lista de textos no formato "AAMM", ex.: ["2301", "2302"].
    """Lista 'AAMM' dos arquivos RDSP no FTP (sem internet: os que estão no cache)."""
    try:
        # "with ... as ftp" abre a conexão e garante que ela será fechada no fim do bloco.
        # timeout=60 → desiste se o servidor não responder em 60 segundos.
        with ftplib.FTP(SERVIDOR, timeout=60) as ftp:
            ftp.login()                # Entra como usuário anônimo (o FTP do DATASUS é público).
            nomes = ftp.nlst(PASTA)    # Lista os nomes de todos os arquivos da pasta.
        # Para cada nome n (em maiúsculas), procura o padrão "RDSP" + 4 dígitos + ".DBC" no final.
        #   \d{4}  = exatamente 4 dígitos (ex.: 2401); os parênteses "capturam" esse pedaço.
        #   $      = fim do texto.
        # "m := ..." (operador "morsa") guarda o resultado da busca em m e já testa se achou.
        # m.group(1) = o pedaço capturado (os 4 dígitos). RDSP = Reduzida, São Paulo.
        meses = [m.group(1) for n in nomes if (m := re.search(r"RDSP(\d{4})\.DBC$", n.upper()))]
    except (OSError, ftplib.Error):    # Sem internet ou erro no FTP…
        # …usa os meses que já estão salvos no cache. p.stem = nome do arquivo sem extensão
        # (ex.: "internacoes_2401"); [-4:] = os 4 últimos caracteres ("2401").
        meses = [p.stem[-4:] for p in config.CACHE.glob("internacoes_*.parquet")]
    # set(...) remove repetidos; sorted(...) ordena; devolve como lista.
    return sorted(set(meses))


# Define anos_completos(): recebe a lista de meses "AAMM" e devolve a lista de anos completos.
def anos_completos(meses: list[str]) -> list[int]:
    """Anos cujos 12 meses + 3 meses de atraso já foram publicados."""
    disponiveis = set(meses)           # Conjunto: buscar "x in conjunto" é muito rápido.
    # Para cada "AAMM", os 2 primeiros dígitos são o ano: 2000 + 23 = 2023. Conjunto ordenado.
    anos = sorted({2000 + int(m[:2]) for m in meses})
    # Mantém só os anos em que TODOS (all) os 15 arquivos necessários estão disponíveis.
    return [a for a in anos if all(m in disponiveis for m in _meses_do_ano(a))]


def _meses_do_ano(ano: int) -> list[str]:   # Quais arquivos mensais são necessários para um ano?
    # period_range cria uma sequência de meses: começa em janeiro do ano e segue por 15 meses
    # (12 do ano + 3 de atraso). freq="M" = mensal.
    datas = pd.period_range(f"{ano}-01", periods=12 + MESES_DE_ATRASO, freq="M")
    # Converte cada mês para "AAMM". strftime("%y%m"): %y = ano com 2 dígitos, %m = mês com 2 dígitos.
    return [p.strftime("%y%m") for p in datas]


# Define _ler_dbf(): recebe o caminho do arquivo .dbf e devolve uma tabela filtrada.
def _ler_dbf(caminho: Path) -> pd.DataFrame:
    """Lê só as linhas de residentes dos municípios escolhidos (urgência, AIH principal).

    `raw=True` evita decodificar as ~100 colunas de cada linha: o filtro é feito
    nos bytes e só as linhas que interessam são convertidas. Bem mais rápido.
    """
    # Conjunto com os códigos dos municípios em "bytes" (m.encode()), para comparar direto com o arquivo.
    municipios = {m.encode() for m in config.MUNICIPIOS}
    linhas = []                        # Aqui vamos guardar as internações que passarem no filtro.
    # DBF(...) abre o arquivo; o "for" percorre registro por registro (cada registro = 1 internação).
    for reg in DBF(str(caminho), raw=True):
        # Filtro (as três condições precisam ser verdadeiras, "and"):
        #   1) os 6 primeiros caracteres do município de residência estão na lista;
        #   2) caráter da internação = "02" (urgência). O "b" antes das aspas indica bytes;
        #   3) IDENT = "1" (AIH principal, não a de continuação).
        # .strip() remove espaços em branco nas pontas.
        if (reg["MUNIC_RES"].strip()[:6] in municipios and reg["CAR_INT"].strip() == b"02"
                and reg["IDENT"].strip() == b"1"):
            # Converte só as colunas que interessam de bytes para texto (latin-1 = codificação do arquivo)
            # e guarda como dicionário {coluna: valor}.
            linhas.append({c: reg[c].decode("latin-1").strip() for c in COLUNAS})
    # Transforma a lista de dicionários em tabela, com as colunas na ordem de COLUNAS.
    return pd.DataFrame(linhas, columns=COLUNAS)


# Define baixar_mes(): recebe um mês "AAMM" e devolve a tabela de internações daquele arquivo.
def baixar_mes(aamm: str) -> pd.DataFrame:
    """Internações de urgência dos residentes em um arquivo mensal (com cache)."""
    arquivo = config.CACHE / f"internacoes_{aamm}.parquet"   # Onde o resultado fica salvo.
    if arquivo.exists():               # Já baixou antes?
        return pd.read_parquet(arquivo)   # Então só lê do disco (rápido).

    config.CACHE.mkdir(parents=True, exist_ok=True)   # Cria a pasta de cache, se ainda não existir.
    dbc = config.CACHE / f"RDSP{aamm}.dbc"            # Caminho onde o arquivo bruto será salvo.
    with ftplib.FTP(SERVIDOR, timeout=300) as ftp:    # Conecta ao FTP (até 5 minutos de espera).
        ftp.login()                    # Login anônimo.
        ftp.cwd(PASTA)                 # "cwd" = change working directory: entra na pasta dos dados.
        # Procura o nome exato do arquivo (pode estar em maiúsculas ou minúsculas no servidor).
        # next(...) devolve o primeiro nome que bate.
        nome = next(n for n in ftp.nlst() if n.upper() == f"RDSP{aamm}.DBC")
        with open(dbc, "wb") as f:     # Abre o arquivo local para escrita binária ("wb" = write binary).
            # RETR = comando FTP para baixar. Cada pedaço recebido é escrito no arquivo (f.write).
            ftp.retrbinary(f"RETR {nome}", f.write)
    dbf = dbc.with_suffix(".dbf")      # Mesmo caminho, mas terminando em .dbf.
    dbc2dbf(str(dbc), str(dbf))        # Descompacta o .dbc em .dbf.
    df = _ler_dbf(dbf)                 # Lê e filtra só as internações que interessam.
    df.to_parquet(arquivo)             # Salva o resultado pequeno no cache.
    dbc.unlink(missing_ok=True)       # apaga os arquivos grandes do estado
    dbf.unlink(missing_ok=True)       # (missing_ok=True: não reclama se o arquivo já não existir)
    return df


# ---------------------------------------------------------------- tratamento
def tratar(df: pd.DataFrame) -> pd.DataFrame:
    """Datas, idade, recortes (Heliópolis, região, cidade) e grupos de diagnóstico."""
    # Remove internações repetidas (mesmo número de AIH) e faz uma cópia.
    df = df.drop_duplicates("N_AIH").copy()
    # Converte "20240115" em data. format="%Y%m%d" diz o formato (ano 4 dígitos, mês, dia).
    # errors="coerce" → datas inválidas viram vazio (NaT).
    df["data"] = pd.to_datetime(df["DT_INTER"], format="%Y%m%d", errors="coerce")

    # COD_IDADE: 4 = anos, 5 = 100 + anos; 1–3 = horas/dias/meses (bebês)
    cod = pd.to_numeric(df["COD_IDADE"], errors="coerce")   # Unidade da idade, como número.
    valor = pd.to_numeric(df["IDADE"], errors="coerce")     # Valor da idade, como número.
    # np.select escolhe um valor para cada linha conforme a PRIMEIRA condição verdadeira:
    #   se cod == 4        → idade = valor (anos)
    #   se cod == 5        → idade = 100 + valor (centenários)
    #   se cod entre 1 e 3 → idade = 0 (bebês com horas, dias ou meses de vida)
    #   nenhuma das três   → vazio (np.nan)
    df["idade"] = np.select([cod == 4, cod == 5, cod.between(1, 3)],
                            [valor, 100 + valor, 0], default=np.nan)

    # Recortes (não excludentes: Heliópolis ⊂ região do Ipiranga ⊂ cidade)
    # Limpa o CEP: troca vazio por "", remove tudo que não é dígito (\D = "não dígito")
    # e completa com zeros à esquerda até 8 dígitos (zfill(8)), ex.: "4235250" → "04235250".
    cep = df["CEP"].fillna("").str.replace(r"\D", "", regex=True).str.zfill(8)
    # Código do município (6 primeiros dígitos). Arquivos de cache antigos não tinham essa coluna:
    # nesse caso, assume que todos são do município de São Paulo.
    munic = (df["MUNIC_RES"].fillna("").str[:6] if "MUNIC_RES" in df   # caches antigos
             else pd.Series(config.MUNICIPIO_SP, index=df.index))
    em_sp = munic == config.MUNICIPIO_SP   # True se o paciente mora no município de São Paulo.
    # Heliópolis = mora em SP E o CEP começa com algum dos prefixos de Heliópolis.
    # startswith aceita uma TUPLA de prefixos (testa todos de uma vez).
    df["heliopolis"] = em_sp & cep.str.startswith(tuple(config.CEPS_HELIOPOLIS))
    # Região do Ipiranga = mora em SP E CEP com os prefixos da região.
    df["regiao"] = em_sp & cep.str.startswith(tuple(config.CEPS_REGIAO))
    df["cidade"] = em_sp               # Cidade = qualquer morador de SP.

    # Limpa o código do diagnóstico: maiúsculas e só letras/números (remove pontos, espaços…).
    # [^A-Z0-9] = "qualquer coisa que NÃO seja letra maiúscula ou número".
    cid = df["DIAG_PRINC"].fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    df["todas"] = True                             # Toda internação entra no grupo "todas".
    df["respiratorio"] = cid.str.startswith("J")   # CID-10 capítulo J = doenças respiratórias.
    df["circulatorio"] = cid.str.startswith("I")   # Capítulo I = doenças do aparelho circulatório.
    # Efeitos mais diretos do calor: insuficiência renal aguda, desidratação,
    # distúrbios de sais minerais, efeitos do calor e da luz (insolação)
    # Expressão regular: começa (^) com N17, N18 ou N19, OU (|) E86 ou E87, OU T67, OU X30.
    df["rins_desidratacao"] = cid.str.match(r"^(N1[7-9]|E8[67]|T67|X30)")
    df["gastro"] = cid.str.match(r"^A0\d")            # A00–A09: infecções intestinais
    df["idosos"] = df["idade"] >= 65                  # 65 anos ou mais.
    df["criancas"] = df["idade"] <= 9                 # 9 anos ou menos.
    # MORTE = 1 → o paciente morreu no hospital.
    df["obitos"] = pd.to_numeric(df["MORTE"], errors="coerce") == 1
    df["arboviroses"] = cid.str.match(r"^A9[0-2]")    # A90 dengue, A91 dengue grave, A92 chikungunya/zika
    return df.dropna(subset=["data"])  # Remove internações sem data válida e devolve.


# Define internacoes_diarias(): recebe as internações tratadas e os anos; devolve a contagem por dia.
def internacoes_diarias(df: pd.DataFrame, anos: list[int]) -> pd.DataFrame:
    """Uma linha por dia; colunas '<recorte>__<grupo>' com o número de internações."""
    df = df[df["data"].dt.year.isin(anos)]   # Mantém só as internações dos anos pedidos.
    # Cria a lista de TODOS os dias dos anos pedidos (1º/jan a 31/dez de cada um) e junta
    # (np.concatenate). Assim, dias sem nenhuma internação também aparecem (com 0).
    grade = pd.DatetimeIndex(np.concatenate(
        [pd.date_range(f"{a}-01-01", f"{a}-12-31") for a in sorted(anos)]))
    partes = []                        # Uma tabela de contagem por lugar.
    for recorte in RECORTES:           # Para cada lugar…
        # …filtra as internações daquele lugar (df[df[recorte]] = linhas onde a coluna é True),
        # agrupa por data e soma cada coluna de grupo (True conta 1) → nº de internações por dia e grupo.
        contagem = df[df[recorte]].groupby("data")[list(GRUPOS)].sum()
        # Renomeia as colunas para "<lugar>__<grupo>", ex.: "regiao__idosos".
        contagem.columns = [f"{recorte}__{g}" for g in GRUPOS]
        partes.append(contagem)
    # Junta as tabelas dos 3 lugares lado a lado (axis=1), coloca todos os dias da grade (reindex),
    # troca vazios por 0 (dias sem internação) e converte para número inteiro.
    diario = pd.concat(partes, axis=1).reindex(grade).fillna(0).astype(int)
    # Dá o nome "data" ao índice e transforma em coluna normal.
    return diario.rename_axis("data").reset_index()


# "progresso=None": parâmetro opcional. Se vier uma função, ela é chamada para atualizar uma barra.
def carregar(anos: list[int], progresso=None) -> pd.DataFrame:
    """Baixa (se preciso) e conta as internações por dia nos anos pedidos.

    `progresso(i, total, aamm)` é chamado a cada arquivo (para a barra do app).
    """
    # Todos os arquivos mensais necessários para os anos pedidos, sem repetir, em ordem.
    meses = sorted({m for a in anos for m in _meses_do_ano(a)})
    partes = []                        # Uma tabela por mês.
    for i, aamm in enumerate(meses):   # i = número da volta (0, 1, 2…); aamm = o mês.
        if progresso:                  # Se recebemos uma função de progresso…
            progresso(i, len(meses), aamm)   # …avisa em que arquivo estamos.
        partes.append(baixar_mes(aamm))      # Baixa (ou lê do cache) o mês e guarda.
    # Junta todos os meses numa tabela só (ignore_index renumera as linhas), trata e conta por dia.
    return internacoes_diarias(tratar(pd.concat(partes, ignore_index=True)), anos)
