"""
criar_usuario.py

Cadastra um usuário de login pela linha de comando. A senha é pedida no
terminal (não aparece na tela nem fica no histórico do shell).

Exemplos:
    python criar_usuario.py dono elenilton
    python criar_usuario.py barbeiro joao --barbeiro-id 2
    python criar_usuario.py dono maria --nova-barbearia "Barbearia da Maria"
    python criar_usuario.py barbeiro pedro --barbearia-id 2 --barbeiro-id 5

Com uma barbearia só no banco, o usuário vai para ela. Com mais de uma,
informe --barbearia-id (ou --nova-barbearia para cadastrar a barbearia
junto com o dono dela).

Também atualiza um banco antigo (cria a tabela de usuários e separa os
dados por barbearia), sem apagar nenhum dado.
"""

import argparse
import getpass
import sqlite3
import sys

import database
import models


def _escolher_barbearia(barbearia_id):
    """id da barbearia a usar, ou None (depois de listar as opções)."""
    if barbearia_id is not None:
        return barbearia_id
    barbearias = models.listar_barbearias()
    if len(barbearias) == 1:
        return barbearias[0]["id"]
    print("Informe --barbearia-id ou --nova-barbearia. Barbearias cadastradas:")
    for barbearia in barbearias:
        print(f"  {barbearia['id']}: {barbearia['nome']}")
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cadastra um usuário de login.")
    parser.add_argument("papel", choices=models.PAPEIS)
    parser.add_argument("usuario", help="nome usado para entrar no sistema")
    parser.add_argument(
        "--barbeiro-id",
        type=int,
        help="id do barbeiro vinculado (obrigatório para o papel barbeiro)",
    )
    barbearia = parser.add_mutually_exclusive_group()
    barbearia.add_argument(
        "--barbearia-id",
        type=int,
        help="id da barbearia do usuário (obrigatório se houver mais de uma)",
    )
    barbearia.add_argument(
        "--nova-barbearia",
        metavar="NOME",
        help="cadastra uma barbearia nova com este nome (só para o papel dono)",
    )
    args = parser.parse_args(argv)

    database.atualizar_banco()

    if args.nova_barbearia is not None:
        if args.papel != "dono":
            print("Só o dono pode ser criado junto com uma barbearia nova.")
            return 1
        barbearia_id = None
    else:
        barbearia_id = _escolher_barbearia(args.barbearia_id)
        if barbearia_id is None:
            return 1

    if args.papel == "barbeiro" and args.barbeiro_id is None:
        print("Informe --barbeiro-id. Barbeiros cadastrados:")
        for barbeiro in models.listar_barbeiros(barbearia_id):
            print(f"  {barbeiro['id']}: {barbeiro['nome']}")
        return 1

    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        print("As senhas não conferem.")
        return 1

    try:
        if args.nova_barbearia is not None:
            barbearia_id = models.criar_barbearia_com_dono(
                args.nova_barbearia, args.usuario, senha
            )
        else:
            models.criar_usuario(
                barbearia_id, args.usuario, senha, args.papel, args.barbeiro_id
            )
    except ValueError as erro:
        print(erro)
        return 1
    except sqlite3.IntegrityError:
        print(f"Já existe um usuário chamado {args.usuario!r}.")
        return 1

    nome_barbearia = models.buscar_barbearia(barbearia_id)["nome"]
    print(f"Usuário {args.usuario!r} ({args.papel}) criado em {nome_barbearia!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
