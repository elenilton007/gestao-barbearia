"""
preparar_banco.py

Roda a cada deploy (no Render, antes do Gunicorn) e deixa o banco pronto
SEM apagar nenhum dado:

  - banco vazio (primeiro deploy): cria as tabelas, sem dados de exemplo;
  - banco que já existe: só aplica as atualizações (database.atualizar_banco).

Primeiro dono: se o banco ainda não tem nenhum usuário e as variáveis
DONO_USUARIO e DONO_SENHA estiverem definidas, cadastra a barbearia
(nome em BARBEARIA_NOME, padrão "Minha Barbearia") junto com o dono.
Depois que houver um usuário, essas variáveis são ignoradas.

Uso:
    python preparar_banco.py
"""

import os
import sys

import database
import models


def _tem_usuario():
    conn = database.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] > 0
    finally:
        conn.close()


def main():
    destino = "PostgreSQL (DATABASE_URL)" if database.usando_postgres() else (
        f"SQLite ({database.get_database_path()})"
    )
    if database.preparar_banco():
        print(f"Tabelas criadas no {destino}.")
    else:
        print(f"Banco {destino} atualizado; nenhum dado foi apagado.")

    if _tem_usuario():
        return 0

    usuario = os.environ.get("DONO_USUARIO", "").strip()
    senha = os.environ.get("DONO_SENHA", "")
    if not (usuario and senha):
        print(
            "Ainda não há nenhum usuário. Defina DONO_USUARIO e DONO_SENHA "
            "e faça o deploy de novo para criar o primeiro dono."
        )
        return 0

    nome = os.environ.get("BARBEARIA_NOME", "").strip() or "Minha Barbearia"
    try:
        models.criar_barbearia_com_dono(nome, usuario, senha)
    except ValueError as erro:
        print(f"Primeiro dono não criado: {erro}")
        return 1
    print(f"Barbearia {nome!r} criada com o dono {usuario!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
