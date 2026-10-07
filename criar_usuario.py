"""
criar_usuario.py

Cadastra um usuário de login pela linha de comando. A senha é pedida no
terminal (não aparece na tela nem fica no histórico do shell).

Exemplos:
    python criar_usuario.py dono elenilton
    python criar_usuario.py barbeiro joao --barbeiro-id 2

Também cria a tabela de usuários em um banco antigo que ainda não a tem,
sem apagar nenhum dado.
"""

import argparse
import getpass
import sqlite3
import sys

import database
import models


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cadastra um usuário de login.")
    parser.add_argument("papel", choices=models.PAPEIS)
    parser.add_argument("usuario", help="nome usado para entrar no sistema")
    parser.add_argument(
        "--barbeiro-id",
        type=int,
        help="id do barbeiro vinculado (obrigatório para o papel barbeiro)",
    )
    args = parser.parse_args(argv)

    database.criar_tabela_usuarios()

    if args.papel == "barbeiro" and args.barbeiro_id is None:
        print("Informe --barbeiro-id. Barbeiros cadastrados:")
        for barbeiro in models.listar_barbeiros():
            print(f"  {barbeiro['id']}: {barbeiro['nome']}")
        return 1

    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        print("As senhas não conferem.")
        return 1

    try:
        models.criar_usuario(args.usuario, senha, args.papel, args.barbeiro_id)
    except ValueError as erro:
        print(erro)
        return 1
    except sqlite3.IntegrityError:
        print(f"Já existe um usuário chamado {args.usuario!r}.")
        return 1

    print(f"Usuário {args.usuario!r} ({args.papel}) criado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
