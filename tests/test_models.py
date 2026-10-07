"""
test_models.py

Testes das operações de cadastro e listagem (models.py).
"""

import models


def test_dados_de_exemplo_carregados():
    assert len(models.listar_clientes()) == 3
    assert len(models.listar_barbeiros()) == 2
    assert len(models.listar_servicos()) == 5
    assert models.listar_atendimentos() == []


def test_criar_cliente():
    models.criar_cliente("Ana Costa", "(71) 98888-7777")
    clientes = {c["nome"]: c for c in models.listar_clientes()}
    assert clientes["Ana Costa"]["telefone"] == "(71) 98888-7777"
    assert clientes["Ana Costa"]["criado_em"]


def test_criar_cliente_sem_telefone():
    models.criar_cliente("Pedro Alves")
    clientes = {c["nome"]: c for c in models.listar_clientes()}
    assert clientes["Pedro Alves"]["telefone"] is None


def test_clientes_listados_em_ordem_alfabetica():
    models.criar_cliente("Abel Ramos")
    nomes = [c["nome"] for c in models.listar_clientes()]
    assert nomes == sorted(nomes)
    assert nomes[0] == "Abel Ramos"


def test_criar_atendimento_traz_nomes_relacionados():
    models.criar_atendimento(1, 2, 3, 55.00, "pix")
    (atendimento,) = models.listar_atendimentos()
    assert atendimento["cliente"] == "Carlos Souza"
    assert atendimento["barbeiro"] == "João Pereira"
    assert atendimento["servico"] == "Corte + Barba"
    assert atendimento["valor_cobrado"] == 55.00
    assert atendimento["forma_pagamento"] == "pix"
    assert atendimento["data_hora"]


def test_forma_pagamento_padrao_e_dinheiro():
    models.criar_atendimento(1, 1, 1, 35.00)
    (atendimento,) = models.listar_atendimentos()
    assert atendimento["forma_pagamento"] == "dinheiro"
