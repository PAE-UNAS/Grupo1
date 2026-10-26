"""ETL por linha de comando: python -m meteo.pipeline

Gera data/processed/medicoes_horarias.csv e relatorio_qualidade.json
(linhas, ausentes, outliers, fontes e data da execução).
"""
import json

import pandas as pd

from meteo import config, estacoes


def executar():
    base, relatorio = estacoes.carregar()
    config.PROCESSADOS.mkdir(parents=True, exist_ok=True)
    base.to_csv(config.PROCESSADOS / "medicoes_horarias.csv", index=False)
    relatorio["fontes"] = "; ".join(sorted(base["fonte"].unique()))
    relatorio["gerado_em"] = pd.Timestamp.now().isoformat(timespec="seconds")
    (config.PROCESSADOS / "relatorio_qualidade.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio


if __name__ == "__main__":
    print(executar())
