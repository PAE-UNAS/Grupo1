"""Índices de estresse térmico calculados de temperatura e umidade."""
import numpy as np
import pandas as pd

# faixas do indice de calor: (limite superior, rotulo)
FAIXAS = [(27, "Sem alerta"), (32, "Atenção"), (41, "Cautela extrema"),
          (54, "Perigo"), (np.inf, "Perigo extremo")]


def indice_de_calor(temp_c, umid):
    # formula do NWS (Rothfusz), que usa Fahrenheit
    t = np.asarray(temp_c, dtype=float) * 9 / 5 + 32
    r = np.asarray(umid, dtype=float)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r
          - 6.83783e-3 * t**2 - 5.481717e-2 * r**2 + 1.22874e-3 * t**2 * r
          + 8.5282e-4 * t * r**2 - 1.99e-6 * t**2 * r**2)
    hi_c = (hi - 32) * 5 / 9
    # abaixo de 27 C a formula nao vale
    return np.where(np.asarray(temp_c) >= 27, hi_c, temp_c)


def wbgt_aproximado(temp_c, umid):
    # bulbo umido de Stull, globo igual a temperatura do ar
    t = np.asarray(temp_c, dtype=float)
    r = np.asarray(umid, dtype=float)
    tbu = (t * np.arctan(0.151977 * np.sqrt(r + 8.313659)) + np.arctan(t + r)
           - np.arctan(r - 1.676331) + 0.00391838 * r**1.5 * np.arctan(0.023101 * r)
           - 4.686035)
    return 0.7 * tbu + 0.3 * t


def classificar(hi_c):
    limites = [f[0] for f in FAIXAS]
    rotulos = [f[1] for f in FAIXAS]
    return pd.cut(hi_c, bins=[-np.inf] + limites, labels=rotulos, right=False)


def adicionar_indices(df):
    df = df.copy()
    df["indice_calor"] = indice_de_calor(df["temperatura"], df["umidade"])
    df["wbgt"] = wbgt_aproximado(df["temperatura"], df["umidade"])
    df["risco"] = classificar(df["indice_calor"])
    return df
