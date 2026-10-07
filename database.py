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


# Tabelas cujos dados pertencem a uma barbearia.
TABELAS_COM_BARBEARIA = ("clientes", "barbeiros", "servicos", "atendimentos", "usuarios")


def _colunas(conn, tabela):
    return {linha["name"] for linha in conn.execute(f"PRAGMA table_info({tabela})")}


def _separar_por_barbearia(conn):
    """
    Banco criado antes de existir a tabela barbearias: cria a tabela e
    coloca todos os dados que já existem numa barbearia só.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS barbearias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now'))
        )
        """
    )
    sem_coluna = [
        tabela for tabela in TABELAS_COM_BARBEARIA
        if _colunas(conn, tabela) and "barbearia_id" not in _colunas(conn, tabela)
    ]
    if not sem_coluna:
        return

    barbearia_id = conn.execute("SELECT MIN(id) FROM barbearias").fetchone()[0]
    if barbearia_id is None:
        barbearia_id = conn.execute(
            "INSERT INTO barbearias (nome) VALUES ('Minha Barbearia')"
        ).lastrowid
    for tabela in sem_coluna:
        # O SQLite só aceita ADD COLUMN NOT NULL com um DEFAULT; ele preenche
        # as linhas antigas. As inserções de models.py sempre informam a
        # barbearia, então o DEFAULT não é usado depois disso.
        conn.execute(
            f"ALTER TABLE {tabela} ADD COLUMN barbearia_id INTEGER NOT NULL "
            f"DEFAULT {int(barbearia_id)} REFERENCES barbearias (id)"
        )


# Tabelas cujos registros são desativados em vez de apagados.
TABELAS_COM_ATIVO = ("barbeiros", "servicos", "usuarios")


def _adicionar_coluna_ativo(conn):
    """Banco criado antes das telas de cadastro: todos começam ativos."""
    for tabela in TABELAS_COM_ATIVO:
        if "ativo" not in _colunas(conn, tabela):
            conn.execute(
                f"ALTER TABLE {tabela} ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1"
            )


def atualizar_banco():
    """
    Atualiza um banco antigo sem apagar nada: separa os dados por
    barbearia, cria a tabela de usuários e a coluna ativo, se ainda não
    existirem. Pode ser executada várias vezes.
    """
    conn = get_connection()
    _separar_por_barbearia(conn)
    conn.commit()
    conn.close()
    _executar_script("schema_usuarios.sql")
    conn = get_connection()
    _adicionar_coluna_ativo(conn)
    conn.commit()
    conn.close()


def init_db():
    """Inicializa o banco de dados executando o schema.sql."""
    _executar_script("schema.sql")
    atualizar_banco()
    print("Banco de dados inicializado com sucesso.")


if __name__ == "__main__":
    init_db()
