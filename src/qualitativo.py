"""Registro anônimo de entrevistas e questionários."""
import re
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

ARQUIVO = Path("data/raw/qualitativo.csv")

COLUNAS = ["participante_id", "data_registro", "zona", "sente_calor_dentro_casa",
           "horas_calor_insuportavel", "problema_saude_calor", "usa_ventilador_ar",
           "relato"]

PADROES = {
    "[TELEFONE]": re.compile(r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"),
    "[CPF]": re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
    "[EMAIL]": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "[ENDERECO]": re.compile(
        r"\b(?:rua|r\.|av\.?|avenida|travessa|beco|alameda|estrada)\s+"
        r"(?:[^\W\d_]+\s+){0,3}[^\W\d_]+(?:[,\s]+(?:n[º°.]?\s*)?\d+)?", re.IGNORECASE),
}


def anonimizar_texto(texto):
    for marcador, padrao in PADROES.items():
        texto = padrao.sub(marcador, texto)
    return texto


def registrar(resposta, arquivo=ARQUIVO):
    pid = "P-" + uuid.uuid4().hex[:6].upper()
    linha = {c: resposta.get(c) for c in COLUNAS}
    linha["participante_id"] = pid
    linha["data_registro"] = datetime.now().isoformat(timespec="minutes")
    linha["relato"] = anonimizar_texto(str(resposta.get("relato") or ""))
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([linha], columns=COLUNAS).to_csv(
        arquivo, mode="a", header=not arquivo.exists(), index=False)
    return pid


def carregar(arquivo=ARQUIVO):
    return pd.read_csv(arquivo) if arquivo.exists() else pd.DataFrame(columns=COLUNAS)
