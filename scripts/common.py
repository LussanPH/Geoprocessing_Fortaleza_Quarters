"""Configuração compartilhada pelos scripts.

Os valores padrão batem com o docker-compose.yml. Para mudar, defina as variáveis
de ambiente PGHOST, PGPORT, PGUSER, PGPASSWORD e PGDATABASE.
"""
import os

import psycopg2

# CRS de trabalho: SIRGAS 2000 / UTM zona 24S (projetado, unidade = metro).
TARGET_EPSG = 31984


def _cfg() -> dict:
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5434")),
        "user": os.environ.get("PGUSER", "geing"),
        "password": os.environ.get("PGPASSWORD", "geing"),
        "dbname": os.environ.get("PGDATABASE", "geing"),
    }


def connect():
    return psycopg2.connect(**_cfg())


def sqlalchemy_url() -> str:
    c = _cfg()
    return f"postgresql+psycopg2://{c['user']}:{c['password']}@{c['host']}:{c['port']}/{c['dbname']}"
