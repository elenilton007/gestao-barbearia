"""
app.py

Aplicação Flask do MeuBarber — rotas para login, agenda, dashboard,
clientes, atendimentos, relatórios financeiros e o cadastro de unidades,
barbeiros, serviços e usuários (só o dono).

Cada usuário pertence a uma barbearia e só vê os dados dela.

Papéis de acesso:
  dono     -> vê e faz tudo na própria barbearia
  barbeiro -> vê só a própria agenda, atendimentos e comissões
"""

import functools
import hashlib
import math
import os
import secrets
import time

from datetime import timedelta

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect

import agenda
import database
import models
import reports

DEBUG = os.environ.get("FLASK_DEBUG") == "1"

app = Flask(__name__)

# A SECRET_KEY assina a sessão e os tokens CSRF. Em produção ela é
# obrigatória; só no modo debug usamos uma chave aleatória temporária.
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if not DEBUG:
        raise RuntimeError(
            "Defina a variável de ambiente SECRET_KEY "
            "(ou FLASK_DEBUG=1 para desenvolvimento local)."
        )
    _secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = _secret_key
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Em produção (HTTPS), COOKIE_SEGURO=1 faz o navegador só mandar o cookie
# de login por conexão criptografada.
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SEGURO") == "1"
# Depois desse tempo sem usar o sistema, o login expira.
app.config["TEMPO_INATIVIDADE"] = 60 * int(
    os.environ.get("SESSAO_INATIVIDADE_MINUTOS", "30")
)

csrf = CSRFProtect(app)


# ---------- AUTENTICAÇÃO ----------

def _marca_da_senha(usuario):
    """
    Resumo da senha atual guardado na sessão: quando a senha muda, as
    sessões abertas com a senha antiga (em outros aparelhos) deixam de valer.
    """
    return hashlib.sha256(usuario["senha_hash"].encode()).hexdigest()[:16]


def _iniciar_sessao(usuario):
    session.clear()  # evita reaproveitar uma sessão anterior
    session["usuario_id"] = usuario["id"]
    session["senha"] = _marca_da_senha(usuario)
    session["ultimo_acesso"] = time.time()


@app.before_request
def carregar_usuario():
    """Coloca o usuário logado (ou None) em g.usuario, e a barbearia dele em g.barbearia."""
    g.usuario = g.barbearia = None
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return
    usuario = models.buscar_usuario(usuario_id)
    if (
        usuario is None
        or not usuario["ativo"]  # desativado com a sessão aberta: sai na hora
        or session.get("senha") != _marca_da_senha(usuario)
    ):
        session.clear()
        return
    agora = time.time()
    if agora - session.get("ultimo_acesso", 0) > app.config["TEMPO_INATIVIDADE"]:
        session.clear()
        flash("Sua sessão expirou por inatividade. Entre de novo.")
        return
    session["ultimo_acesso"] = agora
    g.usuario = usuario
    g.barbearia = models.buscar_barbearia(usuario["barbearia_id"])


def login_obrigatorio(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.usuario is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def somente_dono(view):
    @functools.wraps(view)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if g.usuario["papel"] != "dono":
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def barbearia_logada():
    """id da barbearia do usuário logado; todas as consultas filtram por ele."""
    return g.usuario["barbearia_id"]


def barbeiro_logado():
    """id do barbeiro se o usuário logado for barbeiro; None para o dono."""
    if g.usuario["papel"] == "barbeiro":
        return g.usuario["barbeiro_id"]
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form.get("usuario", "")
        # Bloqueado: nem confere a senha, para não dar chance de adivinhar.
        if models.segundos_de_bloqueio(nome):
            return _login_bloqueado(nome)
        usuario = models.autenticar(nome, request.form.get("senha", ""))
        if usuario is None:
            models.registrar_falha_login(nome)
            if models.segundos_de_bloqueio(nome):
                return _login_bloqueado(nome)
            flash("Usuário ou senha inválidos.")
            return render_template("login.html"), 401
        models.limpar_falhas_login(nome)
        _iniciar_sessao(usuario)
        return redirect(url_for("dashboard"))
    if g.usuario is not None:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


def _login_bloqueado(nome):
    minutos = math.ceil(models.segundos_de_bloqueio(nome) / 60)
    flash(
        f"Muitas tentativas erradas. Tente de novo em {minutos} "
        f"minuto{'s' if minutos > 1 else ''}."
    )
    return render_template("login.html"), 429


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/conta/senha", methods=["GET", "POST"])
@login_obrigatorio
def trocar_senha():
    """Tela para o usuário logado (dono ou barbeiro) trocar a própria senha."""
    if request.method == "POST":
        nova_senha = request.form.get("nova_senha", "")
        if nova_senha != request.form.get("confirmacao", ""):
            flash("A confirmação não é igual à nova senha.")
            return render_template("trocar_senha.html"), 400
        try:
            models.trocar_senha(
                g.usuario["id"], request.form.get("senha_atual", ""), nova_senha
            )
        except ValueError as erro:
            flash(str(erro))
            return render_template("trocar_senha.html"), 400
        # Continua logado aqui; as sessões de outros aparelhos são encerradas.
        _iniciar_sessao(models.buscar_usuario(g.usuario["id"]))
        flash("Senha alterada.")
        return redirect(url_for("dashboard"))
    return render_template("trocar_senha.html")


# ---------- PÁGINAS ----------

@app.route("/")
@login_obrigatorio
def dashboard():
    """
    Página inicial. O dono vê o resumo da barbearia inteira; o barbeiro
    vê só a própria comissão.
    """
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is not None:
        return render_template(
            "dashboard.html",
            comissoes=reports.comissoes_por_barbeiro(barbearia_id, barbeiro_id),
        )

    total = reports.faturamento_total(barbearia_id)
    comissoes = reports.comissoes_por_barbeiro(barbearia_id)
    servicos = reports.servicos_mais_vendidos(barbearia_id)
    return render_template(
        "dashboard.html",
        total=total,
        comissoes=comissoes,
        servicos=servicos,
    )


@app.route("/clientes")
@login_obrigatorio
def clientes():
    """Lista os clientes da barbearia."""
    lista = models.listar_clientes(barbearia_logada())
    return render_template("clientes.html", clientes=lista)


@app.route("/clientes/novo", methods=["POST"])
@login_obrigatorio
def novo_cliente():
    """Cadastra um novo cliente."""
    nome = request.form["nome"]
    telefone = request.form.get("telefone")
    models.criar_cliente(barbearia_logada(), nome, telefone)
    return redirect(url_for("clientes"))


@app.route("/atendimentos")
@login_obrigatorio
def atendimentos():
    """Lista os atendimentos (o barbeiro vê só os dele)."""
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    lista = models.listar_atendimentos(barbearia_id, barbeiro_id)
    clientes = models.listar_clientes(barbearia_id)
    if barbeiro_id is not None:
        barbeiros = [models.buscar_barbeiro(barbearia_id, barbeiro_id)]
    else:
        barbeiros = models.listar_barbeiros(barbearia_id, somente_ativos=True)
    servicos = models.listar_servicos(barbearia_id, somente_ativos=True)
    return render_template(
        "atendimentos.html",
        atendimentos=lista,
        clientes=clientes,
        barbeiros=barbeiros,
        servicos=servicos,
    )


@app.route("/atendimentos/novo", methods=["POST"])
@login_obrigatorio
def novo_atendimento():
    """
    Registra um novo atendimento (o barbeiro só registra em seu nome).
    Cliente, barbeiro ou serviço de outra barbearia, ou barbeiro ou serviço
    desativado, dá erro 400.
    """
    cliente_id = request.form["cliente_id"]
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is None:
        barbeiro_id = request.form["barbeiro_id"]
    servico_id = request.form["servico_id"]
    valor_cobrado = request.form["valor_cobrado"]
    forma_pagamento = request.form.get("forma_pagamento", "dinheiro")

    try:
        models.criar_atendimento(
            barbearia_logada(), cliente_id, barbeiro_id, servico_id,
            valor_cobrado, forma_pagamento,
        )
    except ValueError:
        abort(400)
    return redirect(url_for("atendimentos"))


@app.route("/relatorios")
@somente_dono
def relatorios():
    """Exibe relatórios financeiros detalhados da barbearia."""
    barbearia_id = barbearia_logada()
    total = reports.faturamento_total(barbearia_id)
    comissoes = reports.comissoes_por_barbeiro(barbearia_id)
    servicos = reports.servicos_mais_vendidos(barbearia_id)
    return render_template(
        "relatorios.html",
        total=total,
        comissoes=comissoes,
        servicos=servicos,
    )


# ---------- CADASTROS (SÓ O DONO) ----------
# Barbeiros, serviços e usuários não são apagados, só desativados: os
# atendimentos antigos continuam apontando para eles.

def _ativo_do_formulario():
    """Campo ativo dos botões Desativar/Reativar: '1' reativa, '0' desativa."""
    valor = request.form.get("ativo")
    if valor not in ("0", "1"):
        abort(400)
    return valor == "1"


def _ou_404(registro):
    if registro is None:
        abort(404)  # não existe ou é de outra barbearia
    return registro


@app.route("/barbeiros")
@somente_dono
def barbeiros():
    lista = models.listar_barbeiros(barbearia_logada())
    return render_template("barbeiros.html", barbeiros=lista)


@app.route("/barbeiros/novo", methods=["POST"])
@somente_dono
def novo_barbeiro():
    try:
        models.criar_barbeiro(
            barbearia_logada(),
            request.form.get("nome"),
            request.form.get("comissao_percentual", ""),
        )
    except ValueError as erro:
        flash(str(erro))
    return redirect(url_for("barbeiros"))


@app.route("/barbeiros/<int:barbeiro_id>/editar", methods=["GET", "POST"])
@somente_dono
def editar_barbeiro(barbeiro_id):
    barbearia_id = barbearia_logada()
    barbeiro = _ou_404(models.buscar_barbeiro(barbearia_id, barbeiro_id))
    if request.method == "POST":
        try:
            models.editar_barbeiro(
                barbearia_id,
                barbeiro_id,
                request.form.get("nome"),
                request.form.get("comissao_percentual", ""),
            )
            if "unidade_id" in request.form:
                agenda.definir_unidade_do_barbeiro(
                    barbearia_id, barbeiro_id, request.form.get("unidade_id")
                )
        except ValueError as erro:
            flash(str(erro))
            return redirect(url_for("editar_barbeiro", barbeiro_id=barbeiro_id))
        return redirect(url_for("barbeiros"))
    return render_template(
        "editar_barbeiro.html",
        barbeiro=barbeiro,
        unidades=agenda.listar_unidades(barbearia_id),
    )


@app.route("/barbeiros/<int:barbeiro_id>/ativo", methods=["POST"])
@somente_dono
def ativar_barbeiro(barbeiro_id):
    barbearia_id = barbearia_logada()
    _ou_404(models.buscar_barbeiro(barbearia_id, barbeiro_id))
    ativo = _ativo_do_formulario()
    models.definir_barbeiro_ativo(barbearia_id, barbeiro_id, ativo)
    if not ativo and any(
        u["barbeiro_id"] == barbeiro_id and u["ativo"]
        for u in models.listar_usuarios(barbearia_id)
    ):
        flash(
            "O login deste barbeiro continua ativo. Se ele saiu da barbearia, "
            "desative-o também em Usuários."
        )
    return redirect(url_for("barbeiros"))


@app.route("/servicos")
@somente_dono
def servicos():
    lista = models.listar_servicos(barbearia_logada())
    return render_template("servicos.html", servicos=lista)


@app.route("/servicos/novo", methods=["POST"])
@somente_dono
def novo_servico():
    try:
        models.criar_servico(
            barbearia_logada(),
            request.form.get("nome"),
            request.form.get("preco", ""),
            request.form.get("duracao_minutos", ""),
        )
    except ValueError as erro:
        flash(str(erro))
    return redirect(url_for("servicos"))


@app.route("/servicos/<int:servico_id>/editar", methods=["GET", "POST"])
@somente_dono
def editar_servico(servico_id):
    barbearia_id = barbearia_logada()
    servico = _ou_404(models.buscar_servico(barbearia_id, servico_id))
    if request.method == "POST":
        try:
            models.editar_servico(
                barbearia_id,
                servico_id,
                request.form.get("nome"),
                request.form.get("preco", ""),
                request.form.get("duracao_minutos", ""),
            )
        except ValueError as erro:
            flash(str(erro))
            return redirect(url_for("editar_servico", servico_id=servico_id))
        return redirect(url_for("servicos"))
    return render_template("editar_servico.html", servico=servico)


@app.route("/servicos/<int:servico_id>/ativo", methods=["POST"])
@somente_dono
def ativar_servico(servico_id):
    barbearia_id = barbearia_logada()
    _ou_404(models.buscar_servico(barbearia_id, servico_id))
    models.definir_servico_ativo(barbearia_id, servico_id, _ativo_do_formulario())
    return redirect(url_for("servicos"))


@app.route("/usuarios")
@somente_dono
def usuarios():
    barbearia_id = barbearia_logada()
    return render_template(
        "usuarios.html",
        usuarios=models.listar_usuarios(barbearia_id),
        barbeiros=models.listar_barbeiros(barbearia_id, somente_ativos=True),
        papeis=models.PAPEIS,
    )


@app.route("/usuarios/novo", methods=["POST"])
@somente_dono
def novo_usuario():
    usuario = request.form.get("usuario", "")
    try:
        models.criar_usuario(
            barbearia_logada(),
            usuario,
            request.form.get("senha", ""),
            request.form.get("papel", ""),
            request.form.get("barbeiro_id") or None,
        )
    except ValueError as erro:
        flash(str(erro))
    except database.IntegrityError:
        flash(f"Já existe um usuário chamado {usuario.strip()!r}.")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@somente_dono
def editar_usuario(usuario_id):
    barbearia_id = barbearia_logada()
    usuario = _ou_404(models.buscar_usuario_da_barbearia(barbearia_id, usuario_id))
    if request.method == "POST":
        papel = request.form.get("papel", "")
        try:
            if usuario_id == g.usuario["id"] and papel != "dono":
                raise ValueError("Você não pode tirar o seu próprio papel de dono.")
            nova_senha = request.form.get("nova_senha", "")
            models.editar_usuario(
                barbearia_id,
                usuario_id,
                papel,
                request.form.get("barbeiro_id") or None,
                nova_senha,
            )
        except ValueError as erro:
            flash(str(erro))
            return redirect(url_for("editar_usuario", usuario_id=usuario_id))
        if nova_senha and usuario_id == g.usuario["id"]:
            # Como em trocar_senha: continua logado aqui, os outros aparelhos saem.
            _iniciar_sessao(models.buscar_usuario(usuario_id))
        return redirect(url_for("usuarios"))
    return render_template(
        "editar_usuario.html",
        usuario=usuario,
        barbeiros=models.listar_barbeiros(barbearia_id),
        papeis=models.PAPEIS,
    )


@app.route("/usuarios/<int:usuario_id>/ativo", methods=["POST"])
@somente_dono
def ativar_usuario(usuario_id):
    barbearia_id = barbearia_logada()
    _ou_404(models.buscar_usuario_da_barbearia(barbearia_id, usuario_id))
    ativo = _ativo_do_formulario()
    try:
        if usuario_id == g.usuario["id"] and not ativo:
            raise ValueError("Você não pode desativar o seu próprio usuário.")
        models.definir_usuario_ativo(barbearia_id, usuario_id, ativo)
    except ValueError as erro:
        flash(str(erro))
    return redirect(url_for("usuarios"))


# ---------- AGENDA ----------
# O dono vê e mexe na agenda de todos; o barbeiro, só na dele.

def _dia_da_agenda():
    try:
        return agenda.ler_data(request.args.get("data") or agenda.hoje())
    except ValueError:
        return agenda.hoje()


def _unidade_da_agenda(unidades):
    """Unidade escolhida (?unidade=), ou a primeira ativa."""
    escolhida = request.args.get("unidade", type=int)
    for unidade in unidades:
        if unidade["id"] == escolhida:
            return unidade
    return unidades[0] if unidades else None


def _agendamento_permitido(agendamento_id):
    """O agendamento da barbearia; para o barbeiro, só se for dele (senão 404)."""
    agendamento = _ou_404(agenda.buscar_agendamento(barbearia_logada(), agendamento_id))
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is not None and agendamento["barbeiro_id"] != barbeiro_id:
        abort(404)
    return agendamento


def _voltar_para_agenda(agendamento=None):
    destino = request.form.get("voltar", "")
    if destino.startswith("/agenda"):  # só volta para dentro da agenda
        return redirect(destino)
    if agendamento is not None:
        return redirect(url_for(
            "agenda_dia", data=agendamento["inicio"][:10], unidade=agendamento["unidade_id"]
        ))
    return redirect(url_for("agenda_dia"))


@app.route("/agenda")
@login_obrigatorio
def agenda_dia():
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    dia = _dia_da_agenda()
    unidades = agenda.listar_unidades(barbearia_id, somente_ativas=True)
    unidade = _unidade_da_agenda(unidades)
    unidade_id = unidade["id"] if unidade else None

    if barbeiro_id is not None:
        barbeiros = [models.buscar_barbeiro(barbearia_id, barbeiro_id)]
    else:
        barbeiros = agenda.barbeiros_da_unidade(barbearia_id, unidade_id) if unidade else []
    agendamentos = (
        agenda.listar_agenda(barbearia_id, dia, unidade_id, barbeiro_id) if unidade else []
    )
    por_barbeiro = {b["id"]: [] for b in barbeiros}
    for item in agendamentos:
        por_barbeiro.setdefault(item["barbeiro_id"], []).append(item)
    nomes = {b["id"]: b["nome"] for b in barbeiros}
    for item in agendamentos:
        nomes.setdefault(item["barbeiro_id"], item["barbeiro"])

    return render_template(
        "agenda.html",
        dia=dia,
        hoje=agenda.hoje(),
        anterior=dia - timedelta(days=1),
        seguinte=dia + timedelta(days=1),
        dia_da_semana=agenda.DIAS_DA_SEMANA[dia.weekday()],
        unidades=unidades,
        unidade=unidade,
        barbeiros=barbeiros,
        por_barbeiro=por_barbeiro,
        nomes=nomes,
        marcados=sum(1 for a in agendamentos if a["status"] == "marcado"),
        previsto=sum(a["total"] for a in agendamentos if a["status"] in ("marcado", "concluido")),
        clientes=models.listar_clientes(barbearia_id),
        servicos=models.listar_servicos(barbearia_id, somente_ativos=True),
        bloqueios=agenda.listar_bloqueios(barbearia_id, agenda.agora(), barbeiro_id),
        todos_barbeiros=(
            barbeiros if barbeiro_id is not None
            else models.listar_barbeiros(barbearia_id, somente_ativos=True)
        ),
        formas_pagamento=agenda.FORMAS_PAGAMENTO,
        horario_unidade=(
            agenda.horarios_da_unidade(barbearia_id, unidade_id)[dia.weekday()]
            if unidade else []
        ),
    )


@app.route("/agenda/horarios")
@login_obrigatorio
def agenda_horarios():
    """Horários livres em JSON, para o formulário de novo agendamento."""
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is None:
        barbeiro_id = request.args.get("barbeiro") or None
    try:
        horarios = agenda.horarios_livres(
            barbearia_logada(),
            request.args.get("unidade"),
            request.args.get("data"),
            [s for s in request.args.get("servicos", "").split(",") if s],
            barbeiro_id,
        )
    except ValueError as erro:
        return jsonify({"horarios": [], "erro": str(erro)})
    return jsonify({"horarios": horarios})


@app.route("/agenda/novo", methods=["POST"])
@login_obrigatorio
def novo_agendamento():
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is None:
        barbeiro_id = request.form.get("barbeiro_id") or None
    dia = request.form.get("data", "")
    unidade_id = request.form.get("unidade_id", "")
    voltar = url_for("agenda_dia", data=dia, unidade=unidade_id)
    try:
        cliente_id = request.form.get("cliente_id") or None
        novo_nome = request.form.get("novo_cliente_nome", "").strip()
        if cliente_id is None and not novo_nome:
            raise ValueError("Escolha um cliente ou cadastre um novo.")
        # Confere o horário antes de cadastrar o cliente novo, para não
        # deixar cliente sobrando quando o horário não serve.
        servico_ids = request.form.getlist("servico_id")
        livres = agenda.horarios_livres(barbearia_id, unidade_id, dia, servico_ids, barbeiro_id)
        if request.form.get("hora") not in [h["hora"] for h in livres]:
            raise ValueError("Esse horário não está livre. Escolha outro.")
        if cliente_id is None:
            cliente_id = models.criar_cliente(
                barbearia_id, novo_nome,
                request.form.get("novo_cliente_telefone", "").strip() or None,
            )
        agenda.criar_agendamento(
            barbearia_id, unidade_id, cliente_id, servico_ids, dia,
            request.form.get("hora", ""), barbeiro_id,
            request.form.get("observacao"),
        )
    except ValueError as erro:
        flash(str(erro))
        return redirect(voltar)
    flash("Horário marcado.", "ok")
    return redirect(voltar)


@app.route("/agenda/<int:agendamento_id>/concluir", methods=["POST"])
@login_obrigatorio
def concluir_agendamento(agendamento_id):
    agendamento = _agendamento_permitido(agendamento_id)
    try:
        agenda.concluir_agendamento(
            barbearia_logada(), agendamento_id, request.form.get("forma_pagamento", "")
        )
    except ValueError as erro:
        flash(str(erro))
    return _voltar_para_agenda(agendamento)


@app.route("/agenda/<int:agendamento_id>/faltou", methods=["POST"])
@login_obrigatorio
def falta_agendamento(agendamento_id):
    agendamento = _agendamento_permitido(agendamento_id)
    try:
        agenda.marcar_falta(barbearia_logada(), agendamento_id)
    except ValueError as erro:
        flash(str(erro))
    return _voltar_para_agenda(agendamento)


@app.route("/agenda/<int:agendamento_id>/cancelar", methods=["POST"])
@login_obrigatorio
def cancelar_agendamento(agendamento_id):
    agendamento = _agendamento_permitido(agendamento_id)
    try:
        agenda.cancelar_agendamento(barbearia_logada(), agendamento_id)
    except ValueError as erro:
        flash(str(erro))
    return _voltar_para_agenda(agendamento)


@app.route("/agenda/bloqueios/novo", methods=["POST"])
@login_obrigatorio
def novo_bloqueio():
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is None:
        barbeiro_id = request.form.get("barbeiro_id", "")
    try:
        agenda.criar_bloqueio(
            barbearia_logada(), barbeiro_id,
            request.form.get("inicio", ""), request.form.get("fim", ""),
            request.form.get("motivo"),
        )
    except ValueError as erro:
        flash(str(erro))
    return _voltar_para_agenda()


@app.route("/agenda/bloqueios/<int:bloqueio_id>/remover", methods=["POST"])
@login_obrigatorio
def remover_bloqueio(bloqueio_id):
    barbearia_id = barbearia_logada()
    bloqueio = _ou_404(agenda.buscar_bloqueio(barbearia_id, bloqueio_id))
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is not None and bloqueio["barbeiro_id"] != barbeiro_id:
        abort(404)
    agenda.remover_bloqueio(barbearia_id, bloqueio_id)
    return _voltar_para_agenda()


# ---------- UNIDADES (SÓ O DONO) ----------

@app.route("/unidades")
@somente_dono
def unidades():
    return render_template(
        "unidades.html", unidades=agenda.listar_unidades(barbearia_logada())
    )


@app.route("/unidades/novo", methods=["POST"])
@somente_dono
def nova_unidade():
    try:
        unidade_id = agenda.criar_unidade(
            barbearia_logada(), request.form.get("nome"), request.form.get("endereco")
        )
    except ValueError as erro:
        flash(str(erro))
        return redirect(url_for("unidades"))
    flash("Unidade criada com o horário padrão (segunda a sábado, 9h às 19h). Ajuste abaixo.", "ok")
    return redirect(url_for("editar_unidade", unidade_id=unidade_id))


def _horarios_do_formulario():
    """Campos abre_<dia>_<faixa> / fecha_<dia>_<faixa> -> {dia: [(abre, fecha)]}."""
    horarios = {}
    for dia in range(7):
        faixas = []
        for faixa in (1, 2):
            abre = request.form.get(f"abre_{dia}_{faixa}", "").strip()
            fecha = request.form.get(f"fecha_{dia}_{faixa}", "").strip()
            if abre or fecha:
                if not (abre and fecha):
                    raise ValueError(
                        f"{agenda.DIAS_DA_SEMANA[dia]}: preencha abrir e fechar."
                    )
                faixas.append((abre, fecha))
        horarios[dia] = faixas
    return horarios


@app.route("/unidades/<int:unidade_id>/editar", methods=["GET", "POST"])
@somente_dono
def editar_unidade(unidade_id):
    barbearia_id = barbearia_logada()
    unidade = _ou_404(agenda.buscar_unidade(barbearia_id, unidade_id))
    if request.method == "POST":
        try:
            agenda.editar_unidade(
                barbearia_id, unidade_id,
                request.form.get("nome"), request.form.get("endereco"),
            )
            agenda.salvar_horarios(barbearia_id, unidade_id, _horarios_do_formulario())
        except ValueError as erro:
            flash(str(erro))
            return redirect(url_for("editar_unidade", unidade_id=unidade_id))
        flash("Unidade salva.", "ok")
        return redirect(url_for("unidades"))
    return render_template(
        "editar_unidade.html",
        unidade=unidade,
        horarios=agenda.horarios_da_unidade(barbearia_id, unidade_id),
        dias=agenda.DIAS_DA_SEMANA,
    )


@app.route("/unidades/<int:unidade_id>/ativo", methods=["POST"])
@somente_dono
def ativar_unidade(unidade_id):
    barbearia_id = barbearia_logada()
    _ou_404(agenda.buscar_unidade(barbearia_id, unidade_id))
    try:
        agenda.definir_unidade_ativa(barbearia_id, unidade_id, _ativo_do_formulario())
    except ValueError as erro:
        flash(str(erro))
    return redirect(url_for("unidades"))


if __name__ == "__main__":
    database.preparar_banco()  # cria as tabelas ou atualiza um banco antigo
    app.run(debug=DEBUG)
