"""
database.py

Módulo responsável pela conexão com o banco de dados SQLite do
Sistema de Gestão de Barbearia.
"""

import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "barbearia.db")


def get_connection():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
    return conn


def init_db():
    """Inicializa o banco de dados executando o schema.sql."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = get_connection()
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("Banco de dados inicializado com sucesso.")


if __name__ == "__main__":
    init_db()
