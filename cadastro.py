"""
cadastro.py

Cadastro de barbearia pela internet: o dono que compra o MeuBarber cria a
própria conta sozinho, sem ninguém rodar script no servidor. Cria a
barbearia, a unidade "Principal" com o horário padrão e o usuário dono, e
já deixa o endereço do link público pronto.

A variável CADASTRO_ABERTO=0 fecha o cadastro (por exemplo, se aparecer
abuso); o padrão é aberto.
"""

import os
import re

import database
import models
import publico
import telefones

USUARIO_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")


def cadastro_aberto():
    return os.environ.get("CADASTRO_ABERTO", "1") != "0"


def criar_conta(nome_barbearia, usuario, senha, confirmacao, whatsapp):
    """
    Cria a barbearia com o dono e devolve o usuário dono (linha do banco).
    ValueError com uma mensagem clara se algo não servir; nada é gravado.
    """
    nome_barbearia = (nome_barbearia or "").strip()
    if not nome_barbearia:
        raise ValueError("Informe o nome da barbearia.")
    if len(nome_barbearia) > 80:
        raise ValueError("O nome da barbearia pode ter até 80 letras.")
    usuario = (usuario or "").strip().lower()
    if not USUARIO_VALIDO.match(usuario):
        raise ValueError(
            "Usuário inválido. Use de 3 a 30 letras minúsculas, números, ponto, "
            "hífen ou sublinhado, sem espaço e sem acento (exemplo: joao.silva)."
        )
    if senha != confirmacao:
        raise ValueError("As senhas não conferem.")
    telefone = telefones.normalizar(whatsapp)
    if telefone is None:
        raise ValueError("Informe o WhatsApp da barbearia, com DDD.")
    if models.autenticar_existe(usuario):
        raise ValueError(f"O usuário {usuario!r} já existe. Escolha outro.")

    try:
        barbearia_id = models.criar_barbearia_com_dono(nome_barbearia, usuario, senha)
    except database.IntegrityError:
        # Dois cadastros ao mesmo tempo com o mesmo usuário.
        raise ValueError(f"O usuário {usuario!r} já existe. Escolha outro.") from None
    barbearia = models.buscar_barbearia(barbearia_id)
    publico.salvar_configuracao(
        barbearia_id, barbearia["slug"], telefone, True,
        barbearia["cancelamento_horas"], barbearia["limite_por_cliente"],
    )
    return models.buscar_usuario_por_nome(usuario)
