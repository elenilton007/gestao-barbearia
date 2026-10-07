"""
database.py

Módulo responsável pela conexão com o banco de dados SQLite do
Sistema de Gestão de Barbearia.
"""

import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "barbearia.db")


def get_database_path():
    """Caminho do banco: variável de ambiente BARBEARIA_DB ou o padrão."""
    return os.environ.get("BARBEARIA_DB", DATABASE_PATH)


def get_connection():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(get_database_path())
    conn.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
    return conn


def _executar_script(nome_arquivo):
    caminho = os.path.join(os.path.dirname(__file__), nome_arquivo)
    conn = get_connection()
    with open(caminho, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def criar_tabela_usuarios():
    """
    Cria a tabela de usuários se ela ainda não existir. Não apaga nada,
    então serve para atualizar um banco antigo que já tem dados.
    """
    _executar_script("schema_usuarios.sql")


def init_db():
    """Inicializa o banco de dados executando o schema.sql."""
    _executar_script("schema.sql")
    criar_tabela_usuarios()
    print("Banco de dados inicializado com sucesso.")


if __name__ == "__main__":
    init_db()
