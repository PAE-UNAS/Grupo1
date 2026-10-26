"""Índices de estresse térmico calculados de temperatura e umidade."""
import numpy as np
import pandas as pd

# Faixas do índice de calor (NOAA), em °C: (limite superior, rótulo)
FAIXAS = [(27, "Sem alerta"), (32, "Atenção"), (41, "Cautela extrema"),
          (54, "Perigo"), (np.inf, "Perigo extremo")]


def indice_calor(temp_c, umid):
    """Índice de calor da NOAA (Rothfusz, com os ajustes oficiais), em °C.

    Combina temperatura e umidade: com o ar úmido o suor evapora menos e o
    corpo sente mais calor. Abaixo de ~27 °C usa a fórmula simplificada.
    """
    t = np.asarray(temp_c, dtype=float) * 9 / 5 + 32
    rh = np.asarray(umid, dtype=float)
    simples = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - .22475541 * t * rh
          - .00683783 * t ** 2 - .05481717 * rh ** 2 + .00122874 * t ** 2 * rh
          + .00085282 * t * rh ** 2 - .00000199 * t ** 2 * rh ** 2)
    with np.errstate(invalid="ignore"):
        seco = (rh < 13) & (t >= 80) & (t <= 112)
        hi = np.where(seco, hi - ((13 - rh) / 4) * np.sqrt((17 - np.abs(t - 95)) / 17), hi)
    umido = (rh > 85) & (t >= 80) & (t <= 87)
    hi = np.where(umido, hi + ((rh - 85) / 10) * ((87 - t) / 5), hi)
    hi = np.where((simples + t) / 2 < 80, simples, hi)
    return (hi - 32) * 5 / 9


def wbgt_aproximado(temp_c, umid):
    # bulbo umido de Stull (2011), globo igual a temperatura do ar (sombra)
    t = np.asarray(temp_c, dtype=float)
    r = np.asarray(umid, dtype=float)
    tbu = (t * np.arctan(0.151977 * np.sqrt(r + 8.313659)) + np.arctan(t + r)
           - np.arctan(r - 1.676331) + 0.00391838 * r**1.5 * np.arctan(0.023101 * r)
           - 4.686035)
    return 0.7 * tbu + 0.3 * t


def classificar(ic):
    limites = [f[0] for f in FAIXAS]
    rotulos = [f[1] for f in FAIXAS]
    return pd.cut(ic, bins=[-np.inf] + limites, labels=rotulos, right=False)


def adicionar_indices(df):
    df = df.copy()
    df["indice_calor"] = indice_calor(df["temperatura"], df["umidade"])
    df["wbgt"] = wbgt_aproximado(df["temperatura"], df["umidade"])
    df["risco"] = classificar(df["indice_calor"])
    return df
