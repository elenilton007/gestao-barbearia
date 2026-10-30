"""
test_agenda.py

Testes da agenda: unidades e horário de funcionamento, horários livres,
agendamento com um ou vários serviços (comanda), "sem preferência",
bloqueios, conflitos, conclusão virando atendimento na gestão, falta,
cancelamento, permissões do barbeiro e separação entre barbearias.

O relógio fica parado na segunda-feira 07/01/2030 às 08:00 (fixture
relogio), antes de a unidade abrir.

Dados de exemplo (conftest / dados_exemplo.sql), barbearia 1:
  barbeiros 1 Elenilton (50%), 2 João (40%)
  serviços  1 Corte 35,00/30 min, 2 Barba 25,00/20 min, 4 Sobrancelha 15,00/10 min
  clientes  1 Carlos, 2 Rafael, 3 Bruno
  unidade   1 Principal, segunda a sábado das 9h às 19h
"""

from datetime import date, datetime

import pytest

import agenda
import models
import reports
from conftest import BARBEARIA, BARBEIRO_JOAO, ID_USUARIO_JOAO, logar
from database import get_connection

ELENILTON = 1
JOAO = BARBEIRO_JOAO
CORTE, BARBA, SOBRANCELHA = 1, 2, 4
CARLOS, RAFAEL, BRUNO = 1, 2, 3
PRINCIPAL = 1

SEGUNDA = "2030-01-07"
TERCA = "2030-01-08"
DOMINGO = "2030-01-13"


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    """Para o relógio da agenda. Devolve uma função para mudar a hora."""
    atual = {"agora": datetime(2030, 1, 7, 8, 0)}
    monkeypatch.setattr(agenda, "agora", lambda: atual["agora"])

    def ajustar(texto):
        atual["agora"] = datetime.strptime(texto, "%Y-%m-%d %H:%M")

    return ajustar


def _horas(livres):
    return [h["hora"] for h in livres]


def _marcar(hora, servicos=(CORTE,), barbeiro=ELENILTON, dia=SEGUNDA, cliente=CARLOS,
            unidade=PRINCIPAL, barbearia=BARBEARIA):
    return agenda.criar_agendamento(
        barbearia, unidade, cliente, list(servicos), dia, hora, barbeiro
    )


# ---------- UNIDADES E HORÁRIO ----------

def test_barbearia_comeca_com_a_unidade_principal_e_horario_padrao():
    (unidade,) = agenda.listar_unidades(BARBEARIA)
    assert unidade["nome"] == "Principal"
    horarios = agenda.horarios_da_unidade(BARBEARIA, unidade["id"])
    assert all(horarios[dia] == [("09:00", "19:00")] for dia in range(6))
    assert horarios[6] == []  # domingo fechado


def test_barbearia_nova_tambem_ganha_unidade(outra_barbearia):
    (unidade,) = agenda.listar_unidades(outra_barbearia.id)
    assert unidade["nome"] == "Principal"
    assert agenda.buscar_unidade(BARBEARIA, unidade["id"]) is None


def test_salvar_horarios_com_almoco():
    agenda.salvar_horarios(BARBEARIA, PRINCIPAL, {0: [("13:00", "18:00"), ("08:00", "12:00")]})
    horarios = agenda.horarios_da_unidade(BARBEARIA, PRINCIPAL)
    assert horarios[0] == [("08:00", "12:00"), ("13:00", "18:00")]
    assert horarios[1] == []
    horas = _horas(agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE]))
    assert "11:30" in horas and "11:45" not in horas and "12:00" not in horas
    assert "13:00" in horas and horas[-1] == "17:30"


@pytest.mark.parametrize("faixas, mensagem", [
    ([("10:00", "09:00")], "antes"),
    ([("09:00", "13:00"), ("12:00", "18:00")], "sobrepõem"),
    ([("9h", "18:00")], "inválido"),
])
def test_salvar_horarios_recusa_faixas_erradas(faixas, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        agenda.salvar_horarios(BARBEARIA, PRINCIPAL, {0: faixas})
    assert agenda.horarios_da_unidade(BARBEARIA, PRINCIPAL)[0] == [("09:00", "19:00")]


def test_nao_desativa_a_ultima_unidade():
    with pytest.raises(ValueError, match="pelo menos uma unidade"):
        agenda.definir_unidade_ativa(BARBEARIA, PRINCIPAL, False)
    nova = agenda.criar_unidade(BARBEARIA, "Shopping", "Av. Central, 100")
    agenda.definir_unidade_ativa(BARBEARIA, PRINCIPAL, False)
    assert [u["id"] for u in agenda.listar_unidades(BARBEARIA, somente_ativas=True)] == [nova]
    with pytest.raises(ValueError, match="Unidade não disponível"):
        _marcar("10:00")


def test_barbeiro_preso_a_uma_unidade_so_aparece_nela():
    shopping = agenda.criar_unidade(BARBEARIA, "Shopping")
    agenda.definir_unidade_do_barbeiro(BARBEARIA, JOAO, shopping)
    assert [b["id"] for b in agenda.barbeiros_da_unidade(BARBEARIA, PRINCIPAL)] == [ELENILTON]
    assert {b["id"] for b in agenda.barbeiros_da_unidade(BARBEARIA, shopping)} == {ELENILTON, JOAO}
    with pytest.raises(ValueError, match="não atende nesta unidade"):
        _marcar("10:00", barbeiro=JOAO)
    agenda.definir_unidade_do_barbeiro(BARBEARIA, JOAO, "")  # volta a atender em todas
    _marcar("10:00", barbeiro=JOAO)


# ---------- HORÁRIOS LIVRES ----------

def test_horarios_livres_do_dia_inteiro():
    livres = agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE])
    horas = _horas(livres)
    assert horas[0] == "09:00" and horas[-1] == "18:30"  # corte de 30 min até 19h
    assert len(horas) == 39  # de 15 em 15 minutos
    assert set(livres[0]["barbeiros"]) == {ELENILTON, JOAO}


def test_domingo_fechado_nao_tem_horario():
    assert agenda.horarios_livres(BARBEARIA, PRINCIPAL, DOMINGO, [CORTE]) == []


def test_horario_que_ja_passou_some(relogio):
    relogio(f"{SEGUNDA} 10:07")
    assert _horas(agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE]))[0] == "10:15"
    assert agenda.horarios_livres(BARBEARIA, PRINCIPAL, "2030-01-05", [CORTE]) == []


def test_comanda_soma_as_duracoes():
    horas = _horas(agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE, BARBA]))
    assert horas[-1] == "18:00"  # 50 minutos: 18:15 passaria das 19h


def test_horario_ocupado_some_so_para_aquele_barbeiro():
    _marcar("10:00")  # Elenilton 10:00-10:30
    so_ele = _horas(agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE], ELENILTON))
    assert "09:30" in so_ele and "09:45" not in so_ele and "10:00" not in so_ele
    assert "10:15" not in so_ele and "10:30" in so_ele
    qualquer = agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE])
    assert {"hora": "10:00", "barbeiros": [JOAO]} in qualquer


@pytest.mark.parametrize("servicos", [[], [CORTE, CORTE], [999], ["x"]])
def test_horarios_livres_recusa_servicos_errados(servicos):
    with pytest.raises(ValueError):
        agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, servicos)


# ---------- MARCAR ----------

def test_marcar_com_varios_servicos():
    agendamento_id = _marcar("10:00", servicos=[CORTE, BARBA, SOBRANCELHA])
    agendamento = agenda.buscar_agendamento(BARBEARIA, agendamento_id)
    assert agendamento["inicio"] == f"{SEGUNDA} 10:00"
    assert agendamento["fim"] == f"{SEGUNDA} 11:00"  # 30 + 20 + 10
    assert agendamento["servicos"] == ["Corte Masculino", "Barba", "Sobrancelha"]
    assert agendamento["total"] == pytest.approx(75.0)
    assert agendamento["status"] == "marcado"
    assert agendamento["cliente"] == "Carlos Souza"


def test_preco_combinado_nao_muda_se_o_servico_mudar():
    agendamento_id = _marcar("10:00")
    models.editar_servico(BARBEARIA, CORTE, "Corte Masculino", "50", "30")
    assert agenda.buscar_agendamento(BARBEARIA, agendamento_id)["total"] == pytest.approx(35.0)


def test_nao_marca_dois_no_mesmo_horario_do_barbeiro():
    _marcar("10:00")
    with pytest.raises(ValueError, match="já tem compromisso"):
        _marcar("10:15", cliente=RAFAEL)
    _marcar("10:30", cliente=RAFAEL)  # encostado, sem sobrepor


def test_sem_preferencia_divide_entre_os_barbeiros():
    primeiro = _marcar("10:00", barbeiro=None)
    segundo = _marcar("10:00", barbeiro=None, cliente=RAFAEL)
    barbeiros = {
        agenda.buscar_agendamento(BARBEARIA, i)["barbeiro_id"] for i in (primeiro, segundo)
    }
    assert barbeiros == {ELENILTON, JOAO}
    with pytest.raises(ValueError, match="Nenhum barbeiro livre"):
        _marcar("10:00", barbeiro=None, cliente=BRUNO)


def test_sem_preferencia_escolhe_o_menos_ocupado_do_dia():
    _marcar("09:00", barbeiro=ELENILTON)
    _marcar("11:00", barbeiro=ELENILTON, cliente=RAFAEL)
    novo = _marcar("15:00", barbeiro=None, cliente=BRUNO)
    assert agenda.buscar_agendamento(BARBEARIA, novo)["barbeiro_id"] == JOAO


@pytest.mark.parametrize("dia, hora, mensagem", [
    (SEGUNDA, "08:30", "Fora do horário"),
    (SEGUNDA, "18:45", "Fora do horário"),  # 30 min passaria das 19h
    (DOMINGO, "10:00", "Fora do horário"),
    ("2030-01-05", "10:00", "já passou"),
    ("2030-06-01", "10:00", "dias à frente"),
    ("07/01/2030", "10:00", "Data inválida"),
    (SEGUNDA, "10h", "Horário inválido"),
])
def test_recusa_dia_e_hora_que_nao_servem(dia, hora, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        _marcar(hora, dia=dia)
    assert agenda.listar_agenda(BARBEARIA, SEGUNDA) == []


def test_recusa_servico_ou_barbeiro_desativado():
    models.definir_servico_ativo(BARBEARIA, BARBA, False)
    with pytest.raises(ValueError, match="não está disponível"):
        _marcar("10:00", servicos=[BARBA])
    models.definir_barbeiro_ativo(BARBEARIA, JOAO, False)
    with pytest.raises(ValueError, match="não atende"):
        _marcar("10:00", barbeiro=JOAO)
    assert agenda.barbeiros_da_unidade(BARBEARIA, PRINCIPAL)[0]["id"] == ELENILTON


# ---------- BLOQUEIOS ----------

def test_bloqueio_tira_os_horarios_do_barbeiro():
    agenda.criar_bloqueio(BARBEARIA, ELENILTON, f"{SEGUNDA}T12:00", f"{SEGUNDA}T13:00", "Almoço")
    so_ele = _horas(agenda.horarios_livres(BARBEARIA, PRINCIPAL, SEGUNDA, [CORTE], ELENILTON))
    assert "11:30" in so_ele and "11:45" not in so_ele and "12:30" not in so_ele
    assert "13:00" in so_ele
    with pytest.raises(ValueError, match="já tem compromisso"):
        _marcar("12:00")
    # Sem preferência, o João pega.
    novo = _marcar("12:00", barbeiro=None)
    assert agenda.buscar_agendamento(BARBEARIA, novo)["barbeiro_id"] == JOAO


def test_ferias_de_varios_dias():
    agenda.criar_bloqueio(BARBEARIA, ELENILTON, f"{SEGUNDA} 00:00", "2030-01-10 00:00", "Férias")
    assert agenda.horarios_livres(BARBEARIA, PRINCIPAL, TERCA, [CORTE], ELENILTON) == []
    assert agenda.horarios_livres(BARBEARIA, PRINCIPAL, "2030-01-10", [CORTE], ELENILTON)


def test_bloqueio_recusa_fim_antes_do_inicio_e_barbeiro_de_fora(outra_barbearia):
    with pytest.raises(ValueError, match="depois do início"):
        agenda.criar_bloqueio(BARBEARIA, ELENILTON, f"{SEGUNDA} 13:00", f"{SEGUNDA} 12:00")
    with pytest.raises(ValueError, match="Barbeiro não encontrado"):
        agenda.criar_bloqueio(
            BARBEARIA, outra_barbearia.barbeiro_id, f"{SEGUNDA} 12:00", f"{SEGUNDA} 13:00"
        )


def test_listar_e_remover_bloqueios():
    bloqueio_id = agenda.criar_bloqueio(BARBEARIA, JOAO, f"{SEGUNDA} 12:00", f"{SEGUNDA} 13:00")
    (bloqueio,) = agenda.listar_bloqueios(BARBEARIA, date(2030, 1, 7))
    assert bloqueio["barbeiro"] == "João Pereira"
    assert agenda.listar_bloqueios(BARBEARIA, date(2030, 1, 7), ELENILTON) == []
    agenda.remover_bloqueio(BARBEARIA, bloqueio_id)
    assert agenda.listar_bloqueios(BARBEARIA, date(2030, 1, 7)) == []


# ---------- CONCLUIR, FALTA E CANCELAR ----------

def test_concluir_vira_atendimento_na_gestao(relogio):
    agendamento_id = _marcar("10:00", servicos=[CORTE, BARBA])
    relogio(f"{SEGUNDA} 10:40")
    antes = reports.faturamento_total(BARBEARIA)

    agenda.concluir_agendamento(BARBEARIA, agendamento_id, "pix")

    assert agenda.buscar_agendamento(BARBEARIA, agendamento_id)["status"] == "concluido"
    assert reports.faturamento_total(BARBEARIA) == pytest.approx(antes + 60.0)
    conn = get_connection()
    atendimentos = conn.execute(
        "SELECT * FROM atendimentos WHERE agendamento_id = ? ORDER BY id", (agendamento_id,)
    ).fetchall()
    conn.close()
    assert [a["servico_id"] for a in atendimentos] == [CORTE, BARBA]
    assert [a["valor_cobrado"] for a in atendimentos] == [35.0, 25.0]
    assert {a["forma_pagamento"] for a in atendimentos} == {"pix"}
    assert {a["comissao_percentual"] for a in atendimentos} == {50.0}
    assert {a["data_hora"] for a in atendimentos} == {f"{SEGUNDA} 10:00:00"}
    assert {a["cliente_id"] for a in atendimentos} == {CARLOS}

    with pytest.raises(ValueError, match="ainda está marcado"):
        agenda.concluir_agendamento(BARBEARIA, agendamento_id, "pix")


def test_nao_conclui_antes_do_dia_nem_com_pagamento_invalido():
    agendamento_id = _marcar("10:00", dia=TERCA)
    with pytest.raises(ValueError, match="no dia do atendimento"):
        agenda.concluir_agendamento(BARBEARIA, agendamento_id, "pix")
    with pytest.raises(ValueError, match="Forma de pagamento"):
        agenda.concluir_agendamento(BARBEARIA, agendamento_id, "fiado")


def test_falta_so_depois_do_horario(relogio):
    agendamento_id = _marcar("10:00")
    with pytest.raises(ValueError, match="depois do horário"):
        agenda.marcar_falta(BARBEARIA, agendamento_id)
    relogio(f"{SEGUNDA} 10:20")
    agenda.marcar_falta(BARBEARIA, agendamento_id)
    assert agenda.buscar_agendamento(BARBEARIA, agendamento_id)["status"] == "faltou"


def test_cancelar_libera_o_horario():
    agendamento_id = _marcar("10:00")
    agenda.cancelar_agendamento(BARBEARIA, agendamento_id)
    assert agenda.buscar_agendamento(BARBEARIA, agendamento_id)["status"] == "cancelado"
    _marcar("10:00", cliente=RAFAEL)
    with pytest.raises(ValueError, match="ainda está marcado"):
        agenda.cancelar_agendamento(BARBEARIA, agendamento_id)


def test_listar_agenda_do_dia_por_horario():
    _marcar("11:00", barbeiro=JOAO)
    _marcar("09:00", cliente=RAFAEL)
    _marcar("09:00", dia=TERCA, cliente=BRUNO)
    assert [a["hora"] for a in agenda.listar_agenda(BARBEARIA, SEGUNDA)] == ["09:00", "11:00"]
    assert [a["cliente"] for a in agenda.listar_agenda(BARBEARIA, SEGUNDA, barbeiro_id=JOAO)] == [
        "Carlos Souza"
    ]


# ---------- SEPARAÇÃO ENTRE BARBEARIAS ----------

def test_nao_marca_com_dados_de_outra_barbearia(outra_barbearia):
    (unidade_de_fora,) = agenda.listar_unidades(outra_barbearia.id)
    for kwargs, mensagem in (
        ({"cliente": outra_barbearia.cliente_id}, "Cliente não encontrado"),
        ({"servicos": [outra_barbearia.servico_id]}, "não está disponível"),
        ({"barbeiro": outra_barbearia.barbeiro_id}, "não atende"),
        ({"unidade": unidade_de_fora["id"]}, "Unidade não disponível"),
    ):
        with pytest.raises(ValueError, match=mensagem):
            _marcar("10:00", **kwargs)


def test_agenda_de_uma_barbearia_nao_aparece_na_outra(outra_barbearia):
    agendamento_id = _marcar("10:00")
    assert agenda.buscar_agendamento(outra_barbearia.id, agendamento_id) is None
    assert agenda.listar_agenda(outra_barbearia.id, SEGUNDA) == []
    with pytest.raises(ValueError):
        agenda.cancelar_agendamento(outra_barbearia.id, agendamento_id)
    assert agenda.buscar_agendamento(BARBEARIA, agendamento_id)["status"] == "marcado"
    # O barbeiro da outra barbearia está livre no mesmo horário.
    (unidade,) = agenda.listar_unidades(outra_barbearia.id)
    agenda.criar_agendamento(
        outra_barbearia.id, unidade["id"], outra_barbearia.cliente_id,
        [outra_barbearia.servico_id], SEGUNDA, "10:00", outra_barbearia.barbeiro_id,
    )


# ---------- TELAS ----------

def _quadro(html):
    """Só a agenda do dia (sem o formulário, que lista todos os clientes)."""
    return html.split('aria-label="Agenda do dia por barbeiro"')[1].split("Caixa do dia")[0]


def _post(client, rota, dados):
    return client.post(rota, data=dados, follow_redirects=True)


def test_dono_ve_a_agenda_do_dia(client):
    _marcar("10:00", servicos=[CORTE, BARBA])
    html = client.get(f"/agenda?data={SEGUNDA}").get_data(as_text=True)
    assert "Novo agendamento" in html
    assert "Carlos Souza" in html and "Corte Masculino, Barba" in html
    assert "Elenilton Silveira" in html and "João Pereira" in html
    assert "Sem preferência" in html


def test_menu_tem_agenda_e_unidades(client, client_anonimo):
    html = client.get("/").get_data(as_text=True)
    assert "/agenda" in html and "/unidades" in html


def test_horarios_em_json(client):
    resposta = client.get(f"/agenda/horarios?unidade=1&data={SEGUNDA}&servicos=1,2")
    dados = resposta.get_json()
    assert dados["horarios"][0] == {"hora": "09:00", "barbeiros": [ELENILTON, JOAO]}
    erro = client.get(f"/agenda/horarios?unidade=1&data={SEGUNDA}&servicos=").get_json()
    assert erro["horarios"] == [] and "serviço" in erro["erro"]


def test_marcar_pela_tela_com_cliente_novo(client):
    html = _post(client, "/agenda/novo", {
        "unidade_id": "1", "data": SEGUNDA, "hora": "10:00",
        "servico_id": ["1", "4"], "barbeiro_id": "",
        "novo_cliente_nome": "Pedro Novo", "novo_cliente_telefone": "(71) 98888-0000",
    }).get_data(as_text=True)
    assert "Horário marcado" in html
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["cliente"] == "Pedro Novo" and item["telefone"] == "(71) 98888-0000"
    assert item["servicos"] == ["Corte Masculino", "Sobrancelha"]


def test_horario_ocupado_pela_tela_nao_cria_cliente_sobrando(client):
    _marcar("10:00", barbeiro=ELENILTON)
    _marcar("10:00", barbeiro=JOAO, cliente=RAFAEL)
    clientes_antes = len(models.listar_clientes(BARBEARIA))
    html = _post(client, "/agenda/novo", {
        "unidade_id": "1", "data": SEGUNDA, "hora": "10:00", "servico_id": "1",
        "barbeiro_id": "", "novo_cliente_nome": "Sobrando",
    }).get_data(as_text=True)
    assert "não está livre" in html
    assert len(models.listar_clientes(BARBEARIA)) == clientes_antes


def test_concluir_falta_e_cancelar_pela_tela(client, relogio):
    um, dois, tres = _marcar("09:00"), _marcar("09:30"), _marcar("10:00")
    relogio(f"{SEGUNDA} 10:05")
    _post(client, f"/agenda/{um}/concluir", {"forma_pagamento": "cartao"})
    _post(client, f"/agenda/{dois}/faltou", {})
    _post(client, f"/agenda/{tres}/cancelar", {})
    status = [a["status"] for a in agenda.listar_agenda(BARBEARIA, SEGUNDA)]
    assert status == ["concluido", "faltou", "cancelado"]
    assert "Corte Masculino" in client.get("/atendimentos").get_data(as_text=True)


def test_voltar_so_aceita_endereco_da_agenda(client):
    agendamento_id = _marcar("10:00")
    resposta = client.post(
        f"/agenda/{agendamento_id}/cancelar", data={"voltar": "https://golpe.example/"}
    )
    assert resposta.status_code == 302
    assert "golpe" not in resposta.headers["Location"]
    assert "/agenda" in resposta.headers["Location"]


def test_nome_do_cliente_nao_quebra_o_html(client):
    cliente_id = models.criar_cliente(BARBEARIA, "Zé <b>'Aspas\"</b>")
    _marcar("10:00", cliente=cliente_id)
    html = client.get(f"/agenda?data={SEGUNDA}").get_data(as_text=True)
    assert "<b>'Aspas" not in html


def test_csrf_protege_marcar(client_csrf):
    resposta = client_csrf.post("/agenda/novo", data={"unidade_id": "1"})
    assert resposta.status_code == 302
    assert "ficou aberta por muito tempo" in client_csrf.get("/agenda").get_data(as_text=True)


def test_anonimo_vai_para_o_login(client_anonimo):
    assert client_anonimo.get("/agenda").status_code == 302


# ---------- BARBEIRO ----------

def test_barbeiro_ve_so_a_propria_agenda(client_barbeiro):
    _marcar("10:00", barbeiro=ELENILTON, cliente=RAFAEL)
    _marcar("11:00", barbeiro=JOAO, cliente=BRUNO)
    html = client_barbeiro.get(f"/agenda?data={SEGUNDA}").get_data(as_text=True)
    assert "Sem preferência" not in html
    assert "Bruno Andrade" in _quadro(html) and "Rafael Lima" not in _quadro(html)


def test_barbeiro_marca_sempre_para_si(client_barbeiro):
    _post(client_barbeiro, "/agenda/novo", {
        "unidade_id": "1", "data": SEGUNDA, "hora": "10:00", "servico_id": "1",
        "barbeiro_id": str(ELENILTON), "cliente_id": str(CARLOS),
    })
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["barbeiro_id"] == JOAO


def test_barbeiro_nao_mexe_no_agendamento_de_outro(client_barbeiro):
    agendamento_id = _marcar("10:00", barbeiro=ELENILTON)
    assert client_barbeiro.post(f"/agenda/{agendamento_id}/cancelar").status_code == 404
    assert agenda.buscar_agendamento(BARBEARIA, agendamento_id)["status"] == "marcado"


def test_barbeiro_bloqueia_so_a_propria_agenda(client_barbeiro):
    _post(client_barbeiro, "/agenda/bloqueios/novo", {
        "barbeiro_id": str(ELENILTON), "inicio": f"{SEGUNDA}T12:00", "fim": f"{SEGUNDA}T13:00",
    })
    (bloqueio,) = agenda.listar_bloqueios(BARBEARIA, date(2030, 1, 7))
    assert bloqueio["barbeiro_id"] == JOAO
    outro = agenda.criar_bloqueio(BARBEARIA, ELENILTON, f"{SEGUNDA} 14:00", f"{SEGUNDA} 15:00")
    assert client_barbeiro.post(f"/agenda/bloqueios/{outro}/remover").status_code == 404
    assert client_barbeiro.post(f"/agenda/bloqueios/{bloqueio['id']}/remover").status_code == 302


def test_barbeiro_nao_ve_unidades(client_barbeiro):
    assert client_barbeiro.get("/unidades").status_code == 403


# ---------- TELAS DE UNIDADES ----------

def test_dono_cria_unidade_e_muda_horario(client):
    html = _post(client, "/unidades/novo", {"nome": "Shopping", "endereco": "Av. 1"}).get_data(as_text=True)
    assert "horário padrão" in html
    shopping = [u for u in agenda.listar_unidades(BARBEARIA) if u["nome"] == "Shopping"][0]
    dados = {"nome": "Shopping Center", "endereco": "Av. 1"}
    dados.update({"abre_0_1": "10:00", "fecha_0_1": "14:00",
                  "abre_0_2": "15:00", "fecha_0_2": "22:00",
                  "abre_6_1": "10:00", "fecha_6_1": "16:00"})
    _post(client, f"/unidades/{shopping['id']}/editar", dados)
    horarios = agenda.horarios_da_unidade(BARBEARIA, shopping["id"])
    assert horarios[0] == [("10:00", "14:00"), ("15:00", "22:00")]
    assert horarios[1] == [] and horarios[6] == [("10:00", "16:00")]
    assert agenda.buscar_unidade(BARBEARIA, shopping["id"])["nome"] == "Shopping Center"


def test_horario_pela_metade_e_recusado(client):
    html = _post(client, "/unidades/1/editar", {
        "nome": "Principal", "abre_2_1": "09:00",
    }).get_data(as_text=True)
    assert "preencha abrir e fechar" in html
    assert agenda.horarios_da_unidade(BARBEARIA, PRINCIPAL)[2] == [("09:00", "19:00")]


def test_unidade_de_outra_barbearia_da_404(client, outra_barbearia):
    (unidade,) = agenda.listar_unidades(outra_barbearia.id)
    assert client.get(f"/unidades/{unidade['id']}/editar").status_code == 404


def test_dono_escolhe_a_unidade_do_barbeiro(client):
    shopping = agenda.criar_unidade(BARBEARIA, "Shopping")
    _post(client, f"/barbeiros/{JOAO}/editar", {
        "nome": "João Pereira", "comissao_percentual": "40", "unidade_id": str(shopping),
    })
    assert models.buscar_barbeiro(BARBEARIA, JOAO)["unidade_id"] == shopping
    html = client.get(f"/agenda?data={SEGUNDA}&unidade=1").get_data(as_text=True)
    assert "João Pereira" not in _quadro(html)
