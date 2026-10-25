"""Gravação das tabelas no PostgreSQL (DATABASE_URL)."""
import os

from sqlalchemy import create_engine


def salvar(df, tabela="medicoes_limpas"):
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida")
    df.to_sql(tabela, create_engine(url), if_exists="replace", index=False)
