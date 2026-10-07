"""
database.py

Módulo responsável pela conexão com o banco de dados do Sistema de
Gestão de Barbearia.

Sem a variável de ambiente DATABASE_URL, usa um arquivo SQLite (o padrão
para desenvolvimento local). Com DATABASE_URL apontando para um
PostgreSQL (por exemplo, o do Neon, em produção), usa o PostgreSQL.

O resto do sistema escreve o SQL do jeito do SQLite (parâmetros com ?,
INTEGER PRIMARY KEY AUTOINCREMENT, datetime('now')). A conexão com o
PostgreSQL traduz essas poucas diferenças antes de enviar cada comando.
"""

import os
import re
import sqlite3

try:
    import psycopg
except ImportError:  # sem o psycopg, só o SQLite funciona
    psycopg = None

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "barbearia.db")

# Nome usuário repetido e outras violações de restrição, nos dois bancos.
IntegrityError = (sqlite3.IntegrityError,) + (
    (psycopg.IntegrityError,) if psycopg else ()
)


def get_database_path():
    """Caminho do banco: variável de ambiente BARBEARIA_DB ou o padrão."""
    return os.environ.get("BARBEARIA_DB", DATABASE_PATH)


def get_database_url():
    """URL do PostgreSQL (variável DATABASE_URL), ou None para usar o SQLite."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return None
    if not url.startswith(("postgres://", "postgresql://")):
        raise RuntimeError(
            "DATABASE_URL precisa começar com postgresql:// "
            "(copie a connection string do Neon)."
        )
    return url


def usando_postgres():
    return get_database_url() is not None


# ---------- POSTGRESQL ----------

_TRADUCOES_POSTGRES = (
    (re.compile(r"INTEGER PRIMARY KEY AUTOINCREMENT", re.I), "SERIAL PRIMARY KEY"),
    # Mesmo formato de texto do SQLite (UTC): 'AAAA-MM-DD HH:MM:SS'.
    (
        re.compile(r"datetime\('now'\)", re.I),
        "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')",
    ),
    # REAL no PostgreSQL tem só 6 dígitos de precisão: dinheiro e horários
    # (segundos desde 1970) precisam de DOUBLE PRECISION.
    (re.compile(r"\bREAL\b", re.I), "DOUBLE PRECISION"),
)


def para_postgres(sql, com_parametros=False):
    """Traduz um comando escrito para o SQLite para o PostgreSQL."""
    for padrao, troca in _TRADUCOES_POSTGRES:
        sql = padrao.sub(troca, sql)
    if com_parametros:
        # O psycopg usa %s nos parâmetros; um % de verdade vira %%.
        sql = sql.replace("%", "%%").replace("?", "%s")
    return sql


class Linha:
    """
    Linha de resultado que funciona como a sqlite3.Row: linha["nome"],
    linha[0], linha.keys() e dict(linha).
    """

    __slots__ = ("_nomes", "_valores")

    def __init__(self, nomes, valores):
        self._nomes = nomes
        self._valores = tuple(valores)

    def keys(self):
        return list(self._nomes)

    def __getitem__(self, chave):
        if isinstance(chave, str):
            return self._valores[self._nomes.index(chave)]
        return self._valores[chave]

    def __iter__(self):
        return iter(self._valores)

    def __len__(self):
        return len(self._valores)

    def __repr__(self):
        return f"Linha({dict(zip(self._nomes, self._valores))!r})"


def _fabrica_de_linhas(cursor):
    nomes = [coluna.name for coluna in cursor.description or ()]
    return lambda valores: Linha(nomes, valores)


class ConexaoPostgres:
    """Conexão com o PostgreSQL com a mesma interface usada da sqlite3."""

    def __init__(self, url):
        if psycopg is None:
            raise RuntimeError(
                "Para usar DATABASE_URL instale o psycopg: pip install -r requirements.txt"
            )
        self._conn = psycopg.connect(url, row_factory=_fabrica_de_linhas)

    def execute(self, sql, parametros=()):
        cursor = self._conn.cursor()
        if parametros:
            cursor.execute(para_postgres(sql, com_parametros=True), parametros)
        else:
            cursor.execute(para_postgres(sql))
        return cursor

    def executescript(self, script):
        # Sem parâmetros, o psycopg aceita vários comandos separados por ;
        self._conn.execute(para_postgres(script))

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ---------- CONEXÃO ----------

def get_connection():
    """Cria e retorna uma conexão com o banco (PostgreSQL ou SQLite)."""
    url = get_database_url()
    if url:
        return ConexaoPostgres(url)
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
    """Nomes das colunas da tabela (conjunto vazio se ela não existir)."""
    if isinstance(conn, ConexaoPostgres):
        linhas = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            (tabela,),
        )
        return {linha[0] for linha in linhas}
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
            "INSERT INTO barbearias (nome) VALUES ('Minha Barbearia') RETURNING id"
        ).fetchone()[0]
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


def banco_vazio():
    """True se o banco ainda não tem as tabelas do sistema."""
    conn = get_connection()
    try:
        return not _colunas(conn, "clientes")
    finally:
        conn.close()


def preparar_banco():
    """
    Deixa o banco pronto para uso SEM apagar nada (usado a cada deploy):
    banco vazio ganha as tabelas (sem dados de exemplo); banco que já
    existe só é atualizado. Retorna True se as tabelas foram criadas agora.
    """
    criado = banco_vazio()
    if criado:
        _executar_script("schema.sql")
    atualizar_banco()
    return criado


def init_db():
    """
    Recria o banco do zero (APAGA tudo) com os dados de exemplo
    (dados_exemplo.sql).
    """
    _executar_script("schema.sql")
    _executar_script("dados_exemplo.sql")
    atualizar_banco()
    print("Banco de dados inicializado com sucesso.")


if __name__ == "__main__":
    init_db()
