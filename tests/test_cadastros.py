"""
test_cadastros.py

Testes das telas do dono para cadastrar, editar e desativar barbeiros,
serviços e usuários da própria barbearia.

Barbeiros, serviços e usuários nunca são apagados, só desativados: o
desativado some do formulário de atendimento (ou não consegue entrar, no
caso do usuário), mas continua no histórico e nos relatórios.
"""

import pytest

import database
import models
import reports
from conftest import BARBEARIA, BARBEIRO_JOAO, ID_DONO, ID_USUARIO_JOAO, logar
from database import get_connection

ROTAS_DE_CADASTRO = ["/barbeiros", "/servicos", "/usuarios"]


def _html(client, rota):
    resposta = client.get(rota)
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def _post(client, rota, **dados):
    """POST que segue o redirect e devolve o HTML da página final."""
    resposta = client.post(rota, data=dados, follow_redirects=True)
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def _barbeiro(nome):
    (barbeiro,) = [b for b in models.listar_barbeiros(BARBEARIA) if b["nome"] == nome]
    return barbeiro


def _servico(nome):
    (servico,) = [s for s in models.listar_servicos(BARBEARIA) if s["nome"] == nome]
    return servico


def _usuario(nome):
    (usuario,) = [u for u in models.listar_usuarios(BARBEARIA) if u["usuario"] == nome]
    return usuario


# ---------- PERMISSÕES ----------

@pytest.mark.parametrize("rota", ROTAS_DE_CADASTRO)
def test_dono_ve_as_telas_de_cadastro(client, rota):
    _html(client, rota)


def test_menu_do_dono_tem_os_cadastros(client):
    html = _html(client, "/")
    for texto in ("Barbeiros", "Serviços", "Usuários"):
        assert texto in html


def test_menu_do_barbeiro_nao_tem_os_cadastros(client_barbeiro):
    html = _html(client_barbeiro, "/")
    assert 'href="/barbeiros"' not in html
    assert 'href="/usuarios"' not in html


@pytest.mark.parametrize(
    "rota",
    ROTAS_DE_CADASTRO + ["/barbeiros/1/editar", "/servicos/1/editar", "/usuarios/1/editar"],
)
def test_barbeiro_nao_acessa_os_cadastros(client_barbeiro, rota):
    assert client_barbeiro.get(rota).status_code == 403


@pytest.mark.parametrize(
    "rota",
    [
        "/barbeiros/novo", "/barbeiros/1/editar", "/barbeiros/1/ativo",
        "/servicos/novo", "/servicos/1/editar", "/servicos/1/ativo",
        "/usuarios/novo", "/usuarios/1/editar", "/usuarios/1/ativo",
    ],
)
def test_barbeiro_nao_altera_os_cadastros(client_barbeiro, rota):
    dados = {
        "nome": "Intruso", "comissao_percentual": "99", "preco": "1",
        "duracao_minutos": "1", "usuario": "intruso", "senha": "senha-forte",
        "papel": "dono", "ativo": "0",
    }
    assert client_barbeiro.post(rota, data=dados).status_code == 403
    assert "Intruso" not in {b["nome"] for b in models.listar_barbeiros(BARBEARIA)}
    assert "Intruso" not in {s["nome"] for s in models.listar_servicos(BARBEARIA)}
    assert models.buscar_barbeiro(BARBEARIA, 1)["ativo"] == 1
    assert models.buscar_usuario(ID_DONO)["ativo"] == 1
    assert models.autenticar("intruso", "senha-forte") is None


@pytest.mark.parametrize("rota", ROTAS_DE_CADASTRO)
def test_cadastros_exigem_login(client_anonimo, rota):
    resposta = client_anonimo.get(rota)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")


def test_cadastros_exigem_csrf(client_csrf):
    resposta = client_csrf.post(
        "/barbeiros/novo", data={"nome": "Sem Token", "comissao_percentual": "40"}
    )
    assert resposta.status_code == 400
    assert "Sem Token" not in {b["nome"] for b in models.listar_barbeiros(BARBEARIA)}


# ---------- BARBEIROS ----------

def test_dono_cadastra_barbeiro(client):
    html = _post(client, "/barbeiros/novo", nome="  Pedro Navalha ", comissao_percentual="35,5")
    assert "Pedro Navalha" in html
    barbeiro = _barbeiro("Pedro Navalha")
    assert barbeiro["comissao_percentual"] == pytest.approx(35.5)
    assert barbeiro["ativo"] == 1


@pytest.mark.parametrize(
    "nome, comissao, mensagem",
    [
        ("", "40", "não pode ficar em branco"),
        ("   ", "40", "não pode ficar em branco"),
        ("Pedro", "abc", "entre 0 e 100"),
        ("Pedro", "-1", "entre 0 e 100"),
        ("Pedro", "100.01", "entre 0 e 100"),
        ("Pedro", "nan", "entre 0 e 100"),
        ("Pedro", "", "entre 0 e 100"),
    ],
)
def test_barbeiro_invalido_e_recusado(client, nome, comissao, mensagem):
    html = _post(client, "/barbeiros/novo", nome=nome, comissao_percentual=comissao)
    assert mensagem in html
    assert len(models.listar_barbeiros(BARBEARIA)) == 2


def test_dono_edita_barbeiro(client):
    html = _html(client, "/barbeiros/2/editar")
    assert 'value="João Pereira"' in html
    _post(client, "/barbeiros/2/editar", nome="João P. Silva", comissao_percentual="45")
    barbeiro = models.buscar_barbeiro(BARBEARIA, 2)
    assert barbeiro["nome"] == "João P. Silva"
    assert barbeiro["comissao_percentual"] == pytest.approx(45.0)


def test_edicao_invalida_de_barbeiro_nao_muda_nada(client):
    html = _post(client, "/barbeiros/2/editar", nome="", comissao_percentual="45")
    assert "não pode ficar em branco" in html
    assert 'value="João Pereira"' in html  # voltou para a tela de edição
    assert models.buscar_barbeiro(BARBEARIA, 2)["comissao_percentual"] == pytest.approx(40.0)


def test_barbeiro_inexistente_da_404(client):
    assert client.get("/barbeiros/99/editar").status_code == 404
    assert client.post("/barbeiros/99/ativo", data={"ativo": "0"}).status_code == 404


def test_barbeiro_desativado_some_do_atendimento_mas_fica_no_historico(client):
    models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, 35.00)
    html = _post(client, "/barbeiros/2/ativo", ativo="0")
    assert "Desativado" in html
    assert models.buscar_barbeiro(BARBEARIA, 2)["ativo"] == 0

    formulario = _html(client, "/atendimentos").split("Histórico")[0]
    assert "João Pereira" not in formulario
    assert "Elenilton Silveira" in formulario
    assert "João Pereira" in _html(client, "/atendimentos")  # no histórico
    assert "João Pereira" in _html(client, "/relatorios")
    assert [b["nome"] for b in models.listar_barbeiros(BARBEARIA, somente_ativos=True)] == [
        "Elenilton Silveira"
    ]


def test_desativar_barbeiro_avisa_que_o_login_continua(client):
    html = _post(client, "/barbeiros/2/ativo", ativo="0")
    assert "login deste barbeiro continua ativo" in html
    html = _post(client, "/barbeiros/1/ativo", ativo="0")  # Elenilton não tem login
    assert "login deste barbeiro continua ativo" not in html


def test_atendimento_com_barbeiro_desativado_e_recusado(client):
    models.definir_barbeiro_ativo(BARBEARIA, 2, False)
    with pytest.raises(ValueError, match="está desativado"):
        models.criar_atendimento(BARBEARIA, 1, 2, 1, 35.00)
    resposta = client.post(
        "/atendimentos/novo",
        data={"cliente_id": "1", "barbeiro_id": "2", "servico_id": "1", "valor_cobrado": "35"},
    )
    assert resposta.status_code == 400
    assert models.listar_atendimentos(BARBEARIA) == []


def test_dono_reativa_barbeiro(client):
    models.definir_barbeiro_ativo(BARBEARIA, 2, False)
    _post(client, "/barbeiros/2/ativo", ativo="1")
    assert models.buscar_barbeiro(BARBEARIA, 2)["ativo"] == 1
    models.criar_atendimento(BARBEARIA, 1, 2, 1, 35.00)


@pytest.mark.parametrize("ativo", [None, "", "talvez"])
def test_ativo_invalido_da_400(client, ativo):
    dados = {} if ativo is None else {"ativo": ativo}
    assert client.post("/barbeiros/2/ativo", data=dados).status_code == 400
    assert models.buscar_barbeiro(BARBEARIA, 2)["ativo"] == 1


# ---------- SERVIÇOS ----------

def test_dono_cadastra_servico(client):
    html = _post(client, "/servicos/novo", nome="Platinado", preco="120,50", duracao_minutos="90")
    assert "Platinado" in html
    servico = _servico("Platinado")
    assert servico["preco"] == pytest.approx(120.50)
    assert servico["duracao_minutos"] == 90


@pytest.mark.parametrize(
    "nome, preco, duracao, mensagem",
    [
        ("", "10", "30", "não pode ficar em branco"),
        ("Platinado", "dez", "30", "preço precisa ser"),
        ("Platinado", "-0.01", "30", "preço precisa ser"),
        ("Platinado", "inf", "30", "preço precisa ser"),
        ("Platinado", "10", "0", "duração precisa ser"),
        ("Platinado", "10", "1.5", "duração precisa ser"),
        ("Platinado", "10", "", "duração precisa ser"),
    ],
)
def test_servico_invalido_e_recusado(client, nome, preco, duracao, mensagem):
    html = _post(client, "/servicos/novo", nome=nome, preco=preco, duracao_minutos=duracao)
    assert mensagem in html
    assert len(models.listar_servicos(BARBEARIA)) == 5


def test_servico_gratis_e_aceito(client):
    _post(client, "/servicos/novo", nome="Lavagem cortesia", preco="0", duracao_minutos="10")
    assert _servico("Lavagem cortesia")["preco"] == 0


def test_dono_edita_servico_sem_mudar_atendimentos_antigos(client):
    models.criar_atendimento(BARBEARIA, 1, 1, 1, 35.00)
    _post(client, "/servicos/1/editar", nome="Corte Social", preco="40", duracao_minutos="35")
    servico = models.buscar_servico(BARBEARIA, 1)
    assert (servico["nome"], servico["preco"], servico["duracao_minutos"]) == (
        "Corte Social", 40.0, 35
    )
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["valor_cobrado"] == pytest.approx(35.00)
    assert atendimento["servico"] == "Corte Social"


def test_edicao_invalida_de_servico_nao_muda_nada(client):
    html = _post(client, "/servicos/1/editar", nome="Corte", preco="-5", duracao_minutos="30")
    assert "preço precisa ser" in html
    assert models.buscar_servico(BARBEARIA, 1)["preco"] == pytest.approx(35.00)


def test_servico_desativado_some_do_atendimento_mas_fica_no_relatorio(client):
    models.criar_atendimento(BARBEARIA, 1, 1, 5, 60.00)  # Coloração
    _post(client, "/servicos/5/ativo", ativo="0")
    formulario = _html(client, "/atendimentos").split("Histórico")[0]
    assert "Coloração" not in formulario
    assert "Corte Masculino" in formulario
    assert "Coloração" in _html(client, "/relatorios")
    with pytest.raises(ValueError, match="está desativado"):
        models.criar_atendimento(BARBEARIA, 1, 1, 5, 60.00)

    _post(client, "/servicos/5/ativo", ativo="1")
    assert "Coloração" in _html(client, "/atendimentos").split("Histórico")[0]


def test_servico_inexistente_da_404(client):
    assert client.get("/servicos/99/editar").status_code == 404
    assert client.post("/servicos/99/editar", data={"nome": "X"}).status_code == 404


# ---------- USUÁRIOS ----------

def test_lista_de_usuarios(client):
    html = _html(client, "/usuarios")
    assert "dono" in html
    assert "joao" in html
    assert "João Pereira" in html  # barbeiro vinculado ao joao
    assert "senha_hash" not in html and "pbkdf2" not in html and "scrypt" not in html


def test_dono_cadastra_usuario_barbeiro_que_consegue_entrar(client_anonimo):
    logar(client_anonimo, ID_DONO)
    _post(
        client_anonimo, "/usuarios/novo",
        usuario="elenilton", senha="senha-do-elenilton", papel="barbeiro", barbeiro_id="1",
    )
    assert _usuario("elenilton")["barbeiro_id"] == 1

    client_anonimo.post("/logout")
    client_anonimo.post("/login", data={"usuario": "elenilton", "senha": "senha-do-elenilton"})
    html = _html(client_anonimo, "/")
    assert "elenilton (barbeiro)" in html
    assert client_anonimo.get("/relatorios").status_code == 403


def test_dono_cadastra_outro_dono(client):
    _post(client, "/usuarios/novo", usuario="socia", senha="senha-da-socia", papel="dono", barbeiro_id="1")
    socia = _usuario("socia")
    assert socia["papel"] == "dono"
    assert socia["barbeiro_id"] is None  # dono não fica vinculado a barbeiro
    assert socia["barbearia_id"] == BARBEARIA


@pytest.mark.parametrize(
    "dados, mensagem",
    [
        ({"usuario": "", "senha": "senha-forte", "papel": "dono"}, "não pode ficar em branco"),
        ({"usuario": "novo", "senha": "curta", "papel": "dono"}, "pelo menos 8"),
        ({"usuario": "novo", "senha": "senha-forte", "papel": "admin"}, "Papel inválido"),
        ({"usuario": "novo", "senha": "senha-forte", "papel": "barbeiro"}, "precisa de um barbeiro_id"),
        ({"usuario": "novo", "senha": "senha-forte", "papel": "barbeiro", "barbeiro_id": "99"},
         "não existe nesta barbearia"),
        ({"usuario": "joao", "senha": "senha-forte", "papel": "dono"}, "Já existe um usuário chamado"),
    ],
)
def test_usuario_invalido_e_recusado(client, dados, mensagem):
    html = _post(client, "/usuarios/novo", **dados)
    assert mensagem in html
    assert len(models.listar_usuarios(BARBEARIA)) == 2


def test_dono_troca_a_senha_de_um_usuario(client):
    _post(client, f"/usuarios/{ID_USUARIO_JOAO}/editar",
          papel="barbeiro", barbeiro_id=str(BARBEIRO_JOAO), nova_senha="senha-nova-do-joao")
    assert models.autenticar("joao", "senha-do-joao") is None
    assert models.autenticar("joao", "senha-nova-do-joao") is not None


def test_trocar_a_senha_do_barbeiro_encerra_a_sessao_dele(client_anonimo):
    logar(client_anonimo, ID_USUARIO_JOAO)
    assert client_anonimo.get("/").status_code == 200
    models.editar_usuario(BARBEARIA, ID_USUARIO_JOAO, "barbeiro", BARBEIRO_JOAO, "senha-nova-do-joao")
    assert client_anonimo.get("/").status_code == 302


def test_dono_troca_a_propria_senha_pela_tela_e_continua_logado(client):
    _post(client, f"/usuarios/{ID_DONO}/editar", papel="dono", nova_senha="senha-nova-do-dono")
    assert models.autenticar("dono", "senha-nova-do-dono") is not None
    assert client.get("/usuarios").status_code == 200


def test_editar_sem_senha_mantem_a_senha(client):
    _post(client, f"/usuarios/{ID_USUARIO_JOAO}/editar",
          papel="barbeiro", barbeiro_id="1", nova_senha="")
    joao = models.autenticar("joao", "senha-do-joao")
    assert joao["barbeiro_id"] == 1


def test_senha_nova_curta_e_recusada(client):
    html = _post(client, f"/usuarios/{ID_USUARIO_JOAO}/editar",
                 papel="barbeiro", barbeiro_id=str(BARBEIRO_JOAO), nova_senha="curta")
    assert "pelo menos 8" in html
    assert models.autenticar("joao", "senha-do-joao") is not None


def test_dono_promove_barbeiro_a_dono(client):
    _post(client, f"/usuarios/{ID_USUARIO_JOAO}/editar", papel="dono", barbeiro_id="2")
    joao = models.buscar_usuario(ID_USUARIO_JOAO)
    assert (joao["papel"], joao["barbeiro_id"]) == ("dono", None)


def test_dono_nao_tira_o_proprio_papel(client):
    html = _post(client, f"/usuarios/{ID_DONO}/editar", papel="barbeiro", barbeiro_id="1")
    assert "seu próprio papel de dono" in html
    assert models.buscar_usuario(ID_DONO)["papel"] == "dono"


def test_dono_nao_se_desativa(client):
    assert f"/usuarios/{ID_DONO}/ativo" not in _html(client, "/usuarios")  # sem o botão
    html = _post(client, f"/usuarios/{ID_DONO}/ativo", ativo="0")
    assert "desativar o seu próprio usuário" in html
    assert models.buscar_usuario(ID_DONO)["ativo"] == 1


def test_barbearia_nao_fica_sem_dono_ativo():
    with pytest.raises(ValueError, match="pelo menos um dono ativo"):
        models.definir_usuario_ativo(BARBEARIA, ID_DONO, False)
    with pytest.raises(ValueError, match="pelo menos um dono ativo"):
        models.editar_usuario(BARBEARIA, ID_DONO, "barbeiro", 1)

    models.criar_usuario(BARBEARIA, "socia", "senha-da-socia", "dono")
    models.definir_usuario_ativo(BARBEARIA, ID_DONO, False)  # agora pode
    socia = models.autenticar("socia", "senha-da-socia")["id"]
    with pytest.raises(ValueError, match="pelo menos um dono ativo"):
        models.definir_usuario_ativo(BARBEARIA, socia, False)


def test_usuario_desativado_nao_entra(client_anonimo):
    logar(client_anonimo, ID_DONO)
    _post(client_anonimo, f"/usuarios/{ID_USUARIO_JOAO}/ativo", ativo="0")
    assert models.autenticar("joao", "senha-do-joao") is None

    client_anonimo.post("/logout")
    resposta = client_anonimo.post("/login", data={"usuario": "joao", "senha": "senha-do-joao"})
    assert resposta.status_code == 401


def test_usuario_desativado_perde_a_sessao_aberta(client_barbeiro):
    assert client_barbeiro.get("/").status_code == 200
    models.definir_usuario_ativo(BARBEARIA, ID_USUARIO_JOAO, False)
    resposta = client_barbeiro.get("/")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")


def test_usuario_reativado_volta_a_entrar(client):
    models.definir_usuario_ativo(BARBEARIA, ID_USUARIO_JOAO, False)
    _post(client, f"/usuarios/{ID_USUARIO_JOAO}/ativo", ativo="1")
    assert models.autenticar("joao", "senha-do-joao") is not None


def test_usuario_inexistente_da_404(client):
    assert client.get("/usuarios/99/editar").status_code == 404
    assert client.post("/usuarios/99/ativo", data={"ativo": "0"}).status_code == 404


# ---------- OUTRA BARBEARIA ----------

@pytest.mark.parametrize("rota", ROTAS_DE_CADASTRO)
def test_cadastros_nao_mostram_a_outra_barbearia(client, outra_barbearia, rota):
    html = _html(client, rota)
    for dado in ("Marcos Tesoura", "Pigmentação", "dona-ouro", "marcos"):
        assert dado not in html


def test_dono_nao_mexe_nos_cadastros_da_outra_barbearia(client, outra_barbearia):
    ouro = outra_barbearia
    rotas = [
        f"/barbeiros/{ouro.barbeiro_id}/editar",
        f"/servicos/{ouro.servico_id}/editar",
        f"/usuarios/{ouro.id_barbeiro}/editar",
    ]
    for rota in rotas:
        assert client.get(rota).status_code == 404
        assert client.post(
            rota,
            data={"nome": "Hackeado", "comissao_percentual": "1", "preco": "1",
                  "duracao_minutos": "1", "papel": "dono", "nova_senha": "senha-hackeada"},
        ).status_code == 404
    for rota in (
        f"/barbeiros/{ouro.barbeiro_id}/ativo",
        f"/servicos/{ouro.servico_id}/ativo",
        f"/usuarios/{ouro.id_barbeiro}/ativo",
        f"/usuarios/{ouro.id_dono}/ativo",
    ):
        assert client.post(rota, data={"ativo": "0"}).status_code == 404

    assert models.buscar_barbeiro(ouro.id, ouro.barbeiro_id)["nome"] == "Marcos Tesoura"
    assert models.buscar_barbeiro(ouro.id, ouro.barbeiro_id)["ativo"] == 1
    assert models.buscar_servico(ouro.id, ouro.servico_id)["preco"] == pytest.approx(123.45)
    assert models.autenticar("marcos", "senha-do-marcos")["papel"] == "barbeiro"
    assert models.autenticar("dona-ouro", "senha-da-dona") is not None


def test_dono_nao_vincula_usuario_a_barbeiro_da_outra_barbearia(client, outra_barbearia):
    html = _post(client, "/usuarios/novo", usuario="espiao", senha="senha-forte",
                 papel="barbeiro", barbeiro_id=str(outra_barbearia.barbeiro_id))
    assert "não existe nesta barbearia" in html
    html = _post(client, f"/usuarios/{ID_USUARIO_JOAO}/editar",
                 papel="barbeiro", barbeiro_id=str(outra_barbearia.barbeiro_id))
    assert "não existe nesta barbearia" in html
    assert models.buscar_usuario(ID_USUARIO_JOAO)["barbeiro_id"] == BARBEIRO_JOAO


def test_barbearia_nova_se_monta_pelas_telas(client_anonimo):
    """O caso que faltava: uma barbearia nova começa vazia e o dono a preenche."""
    barbearia_id = models.criar_barbearia_com_dono("Barbearia da Maria", "maria", "senha-da-maria")
    client_anonimo.post("/login", data={"usuario": "maria", "senha": "senha-da-maria"})

    _post(client_anonimo, "/barbeiros/novo", nome="Ana Tesoura", comissao_percentual="50")
    _post(client_anonimo, "/servicos/novo", nome="Corte", preco="40", duracao_minutos="30")
    (barbeiro,) = models.listar_barbeiros(barbearia_id)
    _post(client_anonimo, "/usuarios/novo", usuario="ana", senha="senha-da-ana",
          papel="barbeiro", barbeiro_id=str(barbeiro["id"]))
    _post(client_anonimo, "/clientes/novo", nome="Primeiro Cliente")

    (servico,) = models.listar_servicos(barbearia_id)
    (cliente,) = models.listar_clientes(barbearia_id)
    _post(client_anonimo, "/atendimentos/novo", cliente_id=str(cliente["id"]),
          barbeiro_id=str(barbeiro["id"]), servico_id=str(servico["id"]), valor_cobrado="40")

    assert reports.faturamento_total(barbearia_id) == pytest.approx(40.0)
    assert models.autenticar("ana", "senha-da-ana")["barbearia_id"] == barbearia_id
    assert [b["nome"] for b in models.listar_barbeiros(BARBEARIA)] == [
        "Elenilton Silveira", "João Pereira"
    ]


# ---------- BANCO ANTIGO ----------

def test_atualizar_banco_cria_a_coluna_ativo_sem_perder_dados():
    conn = get_connection()
    for tabela in database.TABELAS_COM_ATIVO:
        conn.execute(f"ALTER TABLE {tabela} DROP COLUMN ativo")
    conn.commit()
    conn.close()

    database.atualizar_banco()
    database.atualizar_banco()  # pode rodar de novo

    assert all(b["ativo"] == 1 for b in models.listar_barbeiros(BARBEARIA))
    assert len(models.listar_servicos(BARBEARIA, somente_ativos=True)) == 5
    assert models.autenticar("dono", "senha-do-dono") is not None
