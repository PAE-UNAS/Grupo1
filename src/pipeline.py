"""ETL completo por linha de comando: python -m src.pipeline [--db]."""
import json
import sys
from pathlib import Path

import pandas as pd

from src import banco, etl_api, indices, limpeza

BRUTO = Path("data/raw/sensores.csv")
SAIDA = Path("data/processed/medicoes_limpas.csv")
QUALIDADE = Path("data/processed/relatorio_qualidade.json")


def executar(gravar_banco=False):
    if BRUTO.exists():
        bruta = pd.read_csv(BRUTO)
    else:
        bruta = etl_api.base_referencia(*etl_api.PERIODO)

    limpa, relatorio = limpeza.limpar(bruta)
    final = indices.adicionar_indices(limpa)
    final["risco"] = final["risco"].astype(str)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(SAIDA, index=False)
    # registro de qualidade e origem de cada execucao
    fontes = sorted(final["fonte"].unique()) if "fonte" in final else [str(BRUTO)]
    relatorio["fontes"] = "; ".join(fontes)
    relatorio["gerado_em"] = pd.Timestamp.now().isoformat(timespec="seconds")
    QUALIDADE.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    if gravar_banco:
        banco.salvar(final)
        banco.salvar(pd.DataFrame([relatorio]), "relatorio_qualidade")
    return relatorio


if __name__ == "__main__":
    print(executar("--db" in sys.argv))
