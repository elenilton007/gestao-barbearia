"""
database.py

Módulo responsável pela conexão com o banco de dados do Sistema de
Gestão de Barbearia.

Dois bancos são aceitos, com o mesmo SQL:
  - SQLite (padrão, para desenvolvimento local): arquivo barbearia.db, ou
    o caminho da variável BARBEARIA_DB;
  - PostgreSQL (deploy, por exemplo no Neon): usado quando a variável
    DATABASE_URL está definida (postgresql://usuario:senha@host/banco).

O resto do sistema escreve SQL do SQLite (parâmetros com ?) e lê as
linhas pelo nome da coluna; no PostgreSQL, _ConexaoPostgres faz as
adaptações (veja _sql_postgres).
"""

import os
import re
import sqlite3
import sys

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "barbearia.db")

try:
    import psycopg
except ImportError:  # só é preciso com DATABASE_URL
    psycopg = None

# Nome de usuário repetido e outras regras do banco violadas, nos dois
# bancos. Use em except e em pytest.raises.
IntegrityError = (sqlite3.IntegrityError,)
if psycopg is not None:
    IntegrityError += (psycopg.IntegrityError,)


def get_database_path():
    """Caminho do banco SQLite: variável de ambiente BARBEARIA_DB ou o padrão."""
    return os.environ.get("BARBEARIA_DB", DATABASE_PATH)


def get_database_url():
    """Endereço do PostgreSQL (variável DATABASE_URL), ou None para usar o SQLite."""
    return os.environ.get("DATABASE_URL") or None


def usando_postgres():
    return get_database_url() is not None


def get_connection():
    """
    Cria e retorna uma conexão com o banco: PostgreSQL se DATABASE_URL
    estiver definida, senão SQLite.
    """
    url = get_database_url()
    if url is not None:
        return _ConexaoPostgres(url)
    conn = sqlite3.connect(get_database_path())
    conn.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
    return conn


# ---------- POSTGRESQL ----------

# O que muda do SQL do SQLite para o do PostgreSQL. REAL no PostgreSQL tem
# só 6 dígitos de precisão (123.45 viraria 123.449997), por isso vira
# DOUBLE PRECISION, igual ao REAL do SQLite.
_TRADUCOES_POSTGRES = (
    (re.compile(r"INTEGER PRIMARY KEY AUTOINCREMENT", re.I), "SERIAL PRIMARY KEY"),
    (re.compile(r"\bREAL\b", re.I), "DOUBLE PRECISION"),
    (
        re.compile(r"datetime\('now'\)", re.I),
        "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')",
    ),
)


def _sql_postgres(sql, com_parametros):
    for padrao, troca in _TRADUCOES_POSTGRES:
        sql = padrao.sub(troca, sql)
    if com_parametros:
        # O psycopg usa %s nos parâmetros; um % de verdade vira %%.
        sql = sql.replace("%", "%%").replace("?", "%s")
    return sql


class Linha(dict):
    """
    Linha do PostgreSQL que se comporta como sqlite3.Row: linha["nome"],
    linha[0] e linha.keys().
    """

    def __getitem__(self, chave):
        if isinstance(chave, int):
            return list(self.values())[chave]
        return super().__getitem__(chave)


def _fabrica_de_linhas(cursor):
    if cursor.description is None:
        return None
    nomes = [coluna.name for coluna in cursor.description]
    return lambda valores: Linha(zip(nomes, valores))


class _CursorPostgres:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class _ConexaoPostgres:
    """Conexão com o PostgreSQL com a mesma interface usada do sqlite3."""

    def __init__(self, url):
        if psycopg is None:
            raise RuntimeError(
                "DATABASE_URL está definida, mas o psycopg não está instalado. "
                "Rode: pip install -r requirements.txt"
            )
        self._conn = psycopg.connect(url, row_factory=_fabrica_de_linhas)

    def execute(self, sql, parametros=()):
        sql = _sql_postgres(sql, bool(parametros))
        insert = sql.lstrip().upper().startswith("INSERT")
        if insert and "RETURNING" not in sql.upper():
            # O PostgreSQL não tem lastrowid: pede a linha inserida de volta.
            sql += " RETURNING *"
        cursor = self._conn.execute(sql, parametros or None)
        lastrowid = None
        if insert:
            linha = cursor.fetchone()
            if linha is not None:
                lastrowid = linha.get("id")
        return _CursorPostgres(cursor, lastrowid)

    def executescript(self, script):
        # Sem parâmetros, o psycopg aceita vários comandos de uma vez.
        self._conn.execute(_sql_postgres(script, com_parametros=False))
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ---------- CRIAÇÃO E ATUALIZAÇÃO DO BANCO ----------

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
    """Nomes das colunas da tabela (vazio se a tabela não existe)."""
    if isinstance(conn, _ConexaoPostgres):
        linhas = conn.execute(
            """
            SELECT column_name AS name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            (tabela,),
        )
    else:
        linhas = conn.execute(f"PRAGMA table_info({tabela})")
    return {linha["name"] for linha in linhas}


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


def _gravar_comissao_nos_atendimentos(conn):
    """
    Banco criado antes de o atendimento guardar o percentual de comissão:
    cria a coluna e preenche os atendimentos antigos com o percentual
    atual do barbeiro (o único que se conhece).
    """
    colunas = _colunas(conn, "atendimentos")
    if not colunas or "comissao_percentual" in colunas:
        return
    conn.execute(
        "ALTER TABLE atendimentos ADD COLUMN comissao_percentual REAL NOT NULL DEFAULT 0"
    )
    conn.execute(
        """
        UPDATE atendimentos SET comissao_percentual = COALESCE(
            (SELECT barbeiros.comissao_percentual FROM barbeiros
             WHERE barbeiros.id = atendimentos.barbeiro_id), 0)
        """
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
    barbearia, grava a comissão em cada atendimento e cria a tabela de
    usuários e a coluna ativo, se ainda não existirem. Pode ser executada
    várias vezes.
    """
    conn = get_connection()
    _separar_por_barbearia(conn)
    _gravar_comissao_nos_atendimentos(conn)
    conn.commit()
    conn.close()
    _executar_script("schema_usuarios.sql")
    conn = get_connection()
    _adicionar_coluna_ativo(conn)
    conn.commit()
    conn.close()


def init_db():
    """
    Recria o banco do zero (apaga tudo!) com o schema.sql e os dados de
    exemplo de dados_exemplo.sql.
    """
    _executar_script("schema.sql")
    _executar_script("dados_exemplo.sql")
    atualizar_banco()
    print("Banco de dados inicializado com sucesso.")


def preparar_banco():
    """
    Usado no deploy, a cada vez que o servidor sobe: num banco vazio, cria
    as tabelas (sem dados de exemplo); num banco que já tem tabelas, só o
    atualiza com atualizar_banco. Nunca apaga dados.
    """
    conn = get_connection()
    vazio = not _colunas(conn, "clientes")  # tabela que existe desde a 1ª versão
    conn.close()
    if vazio:
        _executar_script("schema.sql")
        print("Tabelas criadas.")
    atualizar_banco()
    print("Banco de dados pronto.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--preparar"]:
        preparar_banco()
    else:
        init_db()
