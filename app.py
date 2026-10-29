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

from datetime import datetime, timedelta

from flask import (
    Flask,
    Response,
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
import assinatura
import cadastro
import database
import models
import publico
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

# No Render, o pedido chega por um proxy: ATRAS_DE_PROXY=1 faz o app ler o
# IP verdadeiro do cliente (X-Forwarded-For), usado no limite de pedidos
# das páginas públicas, e o https original.
if os.environ.get("ATRAS_DE_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

NOMES_PAGAMENTO = {"dinheiro": "Dinheiro", "cartao": "Cartão", "pix": "Pix"}
NOMES_STATUS = {"marcado": "Marcado", "concluido": "Concluído",
                "faltou": "Faltou", "cancelado": "Cancelado"}


@app.template_filter("brl")
def formatar_reais(valor):
    """1234.5 -> 'R$ 1.234,50' (formato brasileiro)."""
    texto = f"{float(valor or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


@app.template_filter("percentual")
def formatar_percentual(valor):
    """50.0 -> '50%'; 45.5 -> '45,5%'."""
    numero = round(float(valor or 0), 2)
    texto = f"{numero:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{texto}%"


@app.template_filter("data_br")
def formatar_data(texto):
    """'2030-01-07 10:00:00' -> '07/01/2030 10:00'; só a data se não tiver hora."""
    texto = str(texto or "")
    if len(texto) < 10:
        return texto
    data = f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}"
    return f"{data} {texto[11:16]}" if len(texto) >= 16 else data


@app.context_processor
def nomes_para_telas():
    return {
        "NOMES_PAGAMENTO": NOMES_PAGAMENTO,
        "NOMES_STATUS": NOMES_STATUS,
        "csp_nonce": _nonce(),
    }


# ---------- CABEÇALHOS DE SEGURANÇA ----------
# Valem para todas as páginas. A política de conteúdo (CSP) só deixa rodar
# scripts do próprio site e os blocos <script> que levam o nonce do pedido:
# um texto malicioso salvo num cadastro não consegue virar script.

def _nonce():
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


@app.after_request
def cabecalhos_de_seguranca(resposta):
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{_nonce()}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if app.config["SESSION_COOKIE_SECURE"]:
        resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resposta


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
    # Tinha sessão: se ela cair abaixo, "/" manda para o login, não para a vitrine.
    g.sessao_caiu = True
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
    g.sessao_caiu = False
    g.usuario = usuario
    g.barbearia = models.buscar_barbearia(usuario["barbearia_id"])


# Telas que continuam abertas com a assinatura vencida: pagar, sair, trocar
# senha, as páginas públicas (que se cuidam sozinhas) e o aviso do Asaas.
LIBERADAS_SEM_ASSINATURA = {
    "assinatura_pagina", "assinar", "logout", "trocar_senha", "static", "termos",
    "aviso_asaas", "pagina_publica", "horarios_publicos", "agendar_publico",
    "horario_publico", "cancelar_publico", "calendario_publico", "privacidade_publica",
    "robots",
}


@app.before_request
def conferir_assinatura():
    """Sem assinatura em dia (com COBRANCA_ATIVA=1), só dá para ir pagar."""
    g.situacao = None
    if g.get("barbearia") is None:
        return None
    g.situacao = assinatura.situacao(g.barbearia)
    if not g.situacao["liberado"] and request.endpoint not in LIBERADAS_SEM_ASSINATURA:
        return redirect(url_for("assinatura_pagina"))
    return None


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
        # Limite por aparelho também: impede testar uma senha comum em
        # muitos usuários diferentes.
        if not publico.pode_tentar(f"login:{_ip()}", 30, 15 * 60):
            flash("Muitas tentativas deste aparelho. Tente de novo em 15 minutos.")
            return render_template("login.html"), 429
        usuario = models.autenticar(nome, request.form.get("senha", ""))
        if usuario is None:
            models.registrar_falha_login(nome)
            if models.segundos_de_bloqueio(nome):
                return _login_bloqueado(nome)
            flash("Usuário ou senha inválidos.")
            return render_template("login.html"), 401
        models.limpar_falhas_login(nome)
        _iniciar_sessao(usuario)
        return redirect(url_for("agenda_dia"))
    if g.usuario is not None:
        return redirect(url_for("agenda_dia"))
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

def _whatsapp_de_vendas():
    """Número de vendas (CONTATO_WHATSAPP) só com dígitos, com DDI 55."""
    digitos = "".join(c for c in os.environ.get("CONTATO_WHATSAPP", "") if c.isdigit())
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos if len(digitos) in (12, 13) else ""


@app.route("/")
def dashboard():
    """
    Quem não entrou vê a página de vendas do MeuBarber. Logado, o dono vê o
    resumo da barbearia inteira e o barbeiro vê só a própria comissão.
    """
    if g.usuario is None:
        if g.get("sessao_caiu"):  # estava logado e a sessão caiu: volta ao login
            return redirect(url_for("login"))
        return render_template(
            "inicio.html",
            valor=assinatura.valor_plano(),
            dias=assinatura.dias_de_teste(),
            whatsapp=_whatsapp_de_vendas(),
        )
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
    """Lista os clientes da barbearia (com busca por nome ou WhatsApp)."""
    busca = request.args.get("busca", "").strip()
    return render_template(
        "clientes.html",
        clientes=models.listar_clientes(barbearia_logada(), busca),
        busca=busca,
        total=len(models.listar_clientes(barbearia_logada())) if busca else None,
    )


@app.route("/clientes/novo", methods=["POST"])
@login_obrigatorio
def novo_cliente():
    """Cadastra um novo cliente."""
    try:
        models.criar_cliente(
            barbearia_logada(), request.form.get("nome", ""), request.form.get("telefone")
        )
    except ValueError as erro:
        flash(str(erro))
    return redirect(url_for("clientes"))


@app.route("/clientes/<int:cliente_id>", methods=["GET", "POST"])
@login_obrigatorio
def cliente(cliente_id):
    """Ficha do cliente: dados, próximos horários e histórico de atendimentos."""
    barbearia_id = barbearia_logada()
    registro = _ou_404(models.buscar_cliente(barbearia_id, cliente_id))
    if request.method == "POST":
        try:
            models.editar_cliente(
                barbearia_id, cliente_id,
                request.form.get("nome", ""), request.form.get("telefone"),
            )
        except ValueError as erro:
            flash(str(erro))
            return redirect(url_for("cliente", cliente_id=cliente_id))
        flash("Cliente salvo.", "ok")
        return redirect(url_for("cliente", cliente_id=cliente_id))
    historico = models.historico_do_cliente(barbearia_id, cliente_id)
    return render_template(
        "cliente.html",
        cliente=registro,
        historico=historico,
        gasto=round(sum(a["valor_cobrado"] for a in historico), 2),
        proximos=agenda.proximos_do_cliente(barbearia_id, cliente_id),
    )


@app.route("/clientes/<int:cliente_id>/excluir", methods=["POST"])
@somente_dono
def excluir_cliente(cliente_id):
    barbearia_id = barbearia_logada()
    registro = _ou_404(models.buscar_cliente(barbearia_id, cliente_id))
    try:
        models.excluir_cliente(barbearia_id, cliente_id)
    except ValueError as erro:
        flash(str(erro))
        return redirect(url_for("cliente", cliente_id=cliente_id))
    flash(f"Cliente {registro['nome']} excluído.", "ok")
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

    # Quem tem horário marcado hoje com o barbeiro é concluído pela agenda;
    # registrar aqui também contaria o mesmo corte duas vezes no caixa.
    try:
        marcado = agenda.marcado_hoje(barbearia_logada(), int(cliente_id), int(barbeiro_id))
    except (TypeError, ValueError):
        marcado = None
    if marcado is not None:
        flash(
            f"{marcado['cliente']} tem horário marcado hoje às {marcado['hora']} com "
            f"{marcado['barbeiro']}. Conclua pela agenda para não contar duas vezes."
        )
        return redirect(url_for("agenda_dia", unidade=marcado["unidade_id"]))
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


def _minutos(momento, comeco):
    return int((momento - comeco).total_seconds() // 60)


def _faixa_do_quadro(dia, faixas, itens, bloqueios):
    """
    Começo e fim (datetime) do quadro do dia: o horário da unidade, aberto
    para caber horários marcados fora dele. Sempre em horas cheias.
    """
    base = datetime.combine(dia, datetime.min.time())
    momentos = []
    for abre, fecha in faixas:
        momentos += [base + timedelta(hours=int(abre[:2]), minutes=int(abre[3:])),
                     base + timedelta(hours=int(fecha[:2]), minutes=int(fecha[3:]))]
    for item in itens:
        momentos += [agenda.ler_momento(item["inicio"]), agenda.ler_momento(item["fim"])]
    for bloqueio in bloqueios:
        if faixas or itens:  # bloqueio sozinho não abre o quadro de madrugada
            momentos += [bloqueio["inicio"], bloqueio["fim"]]
    if not momentos:
        return base + timedelta(hours=9), base + timedelta(hours=19)
    comeco = min(momentos).replace(minute=0)
    final = max(momentos)
    if final.minute:
        final = final.replace(minute=0) + timedelta(hours=1)
    final = min(final, base + timedelta(days=1))
    if final <= comeco:
        final = comeco + timedelta(hours=1)
    return comeco, final


@app.route("/agenda")
@login_obrigatorio
def agenda_dia():
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    dia = _dia_da_agenda()
    hoje = agenda.hoje()
    unidades = agenda.listar_unidades(barbearia_id, somente_ativas=True)
    unidade = _unidade_da_agenda(unidades)
    unidade_id = unidade["id"] if unidade else None

    if barbeiro_id is not None:
        barbeiros = [models.buscar_barbeiro(barbearia_id, barbeiro_id)]
    else:
        barbeiros = agenda.barbeiros_da_unidade(barbearia_id, unidade_id) if unidade else []
    itens = agenda.listar_agenda(barbearia_id, dia, unidade_id, barbeiro_id) if unidade else []
    # Quem tem horário no dia aparece, mesmo desativado ou de outra unidade.
    colunas = {b["id"]: {"id": b["id"], "nome": b["nome"], "itens": [], "bloqueios": []}
               for b in barbeiros}
    for item in itens:
        colunas.setdefault(item["barbeiro_id"], {
            "id": item["barbeiro_id"], "nome": item["barbeiro"], "itens": [], "bloqueios": [],
        })["itens"].append(item)
    bloqueios = [b for b in agenda.bloqueios_do_dia(barbearia_id, dia, barbeiro_id)
                 if b["barbeiro_id"] in colunas]
    for bloqueio in bloqueios:
        colunas[bloqueio["barbeiro_id"]]["bloqueios"].append(bloqueio)

    horarios = agenda.horarios_da_unidade(barbearia_id, unidade_id) if unidade else {}
    faixas = horarios.get(dia.weekday(), [])
    comeco, final = _faixa_do_quadro(dia, faixas, itens, bloqueios)
    minutos_abertos = sum(
        (int(f[:2]) * 60 + int(f[3:])) - (int(a[:2]) * 60 + int(a[3:])) for a, f in faixas
    )
    for coluna in colunas.values():
        ocupado = 0
        for item in coluna["itens"]:
            inicio, fim = agenda.ler_momento(item["inicio"]), agenda.ler_momento(item["fim"])
            item["ini"], item["dur"] = _minutos(inicio, comeco), _minutos(fim, inicio)
            if item["status"] in ("marcado", "concluido"):
                ocupado += item["dur"]
        for bloqueio in coluna["bloqueios"]:
            bloqueio["ini"] = _minutos(bloqueio["inicio"], comeco)
            bloqueio["dur"] = _minutos(bloqueio["fim"], bloqueio["inicio"])
            bloqueio["hora"] = bloqueio["inicio"].strftime("%H:%M")
        coluna["ocupacao"] = round(100 * ocupado / minutos_abertos) if minutos_abertos else 0
        coluna["iniciais"] = "".join(p[0] for p in coluna["nome"].split()[:2]).upper()

    agora = agenda.agora()
    linha_agora = None
    if dia == hoje and comeco <= agora <= final:
        linha_agora = {"ini": _minutos(agora, comeco), "hora": agora.strftime("%H:%M")}

    def soma(status):
        return sum(i["total"] for i in itens if i["status"] == status)

    caixa = {"recebido": soma("concluido"), "a_receber": soma("marcado"), "perdido": soma("faltou")}
    caixa["previsto"] = caixa["recebido"] + caixa["a_receber"]
    escala = max(caixa["previsto"] + caixa["perdido"], 1)
    caixa["partes"] = {chave: round(100 * caixa[chave] / escala, 1)
                       for chave in ("recebido", "a_receber", "perdido")}
    marcados = [i for i in itens if i["status"] == "marcado"]
    if dia == hoje:
        marcados = [i for i in marcados if agenda.ler_momento(i["fim"]) > agora]

    segunda = dia - timedelta(days=dia.weekday())
    contagem = (
        agenda.contar_por_dia(barbearia_id, segunda, 7, unidade_id, barbeiro_id) if unidade else {}
    )
    semana = [
        {"data": d, "curto": agenda.DIAS_CURTOS[d.weekday()], "total": contagem.get(d, 0),
         "fechado": not horarios.get(d.weekday())}
        for d in (segunda + timedelta(days=i) for i in range(7))
    ]

    return render_template(
        "agenda.html",
        dia=dia,
        hoje=hoje,
        titulo_dia=(
            f"{agenda.DIAS_DA_SEMANA[dia.weekday()]}, {dia.day} de {agenda.MESES[dia.month - 1]}"
            + ("" if dia.year == hoje.year else f" de {dia.year}")
        ),
        semana=semana,
        semana_anterior=segunda - timedelta(days=7),
        semana_seguinte=segunda + timedelta(days=7),
        unidades=unidades,
        unidade=unidade,
        faixas=faixas,
        colunas=list(colunas.values()),
        itens=itens,
        comeco=comeco,
        minutos_quadro=_minutos(final, comeco),
        horas_quadro=[
            {"ini": _minutos(comeco + timedelta(hours=h), comeco),
             "texto": f"{(comeco + timedelta(hours=h)).hour}h"}
            for h in range(_minutos(final, comeco) // 60 + 1)
        ],
        linha_agora=linha_agora,
        caixa=caixa,
        a_seguir=marcados[:3],
        faltas=sum(1 for i in itens if i["status"] == "faltou"),
        cancelados=sum(1 for i in itens if i["status"] == "cancelado"),
        clientes=models.listar_clientes(barbearia_id),
        servicos=models.listar_servicos(barbearia_id, somente_ativos=True),
        barbeiros=barbeiros,
        bloqueios=agenda.listar_bloqueios(barbearia_id, agora, barbeiro_id),
        todos_barbeiros=(
            barbeiros if barbeiro_id is not None
            else models.listar_barbeiros(barbearia_id, somente_ativos=True)
        ),
        formas_pagamento=agenda.FORMAS_PAGAMENTO,
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
            telefone = request.form.get("novo_cliente_telefone", "").strip() or None
            existente = models.buscar_cliente_por_telefone(barbearia_id, telefone)
            if existente is not None:
                # Mesmo WhatsApp = mesmo cliente: não cria cadastro repetido.
                cliente_id = existente["id"]
                flash(f"Esse WhatsApp já era de {existente['nome']}; o horário ficou no cadastro dele.", "aviso")
            else:
                cliente_id = models.criar_cliente(barbearia_id, novo_nome, telefone)
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
    inicio, fim = request.form.get("inicio", ""), request.form.get("fim", "")
    try:
        bloqueio_id = agenda.criar_bloqueio(
            barbearia_logada(), barbeiro_id, inicio, fim, request.form.get("motivo"),
        )
    except ValueError as erro:
        flash(str(erro))
        return _voltar_para_agenda()
    bloqueio = agenda.buscar_bloqueio(barbearia_logada(), bloqueio_id)
    conflitos = agenda.marcados_no_periodo(
        barbearia_logada(), bloqueio["barbeiro_id"], bloqueio["inicio"], bloqueio["fim"]
    )
    if conflitos:
        flash(
            "Bloqueado. Atenção: continuam marcados neste período "
            + "; ".join(f"{c['cliente']} em {c['inicio'][8:10]}/{c['inicio'][5:7]} às {c['hora']}"
                        for c in conflitos)
            + ". Remarque ou cancele com o cliente.",
            "aviso",
        )
    else:
        flash("Horário bloqueado.", "ok")
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
        fora = agenda.marcados_fora_do_horario(barbearia_id, unidade_id)
        if fora:
            flash(
                "Unidade salva. Atenção: estes horários marcados ficaram fora do novo "
                "funcionamento: "
                + "; ".join(f"{f['cliente']} em {f['inicio'][8:10]}/{f['inicio'][5:7]} às {f['hora']}"
                            for f in fora)
                + ".",
                "aviso",
            )
        else:
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


# ---------- LINK DE AGENDAMENTO (CONFIGURAÇÃO, SÓ O DONO) ----------

@app.route("/configuracoes/link", methods=["GET", "POST"])
@somente_dono
def configurar_link():
    barbearia_id = barbearia_logada()
    if request.method == "POST":
        try:
            publico.salvar_configuracao(
                barbearia_id,
                request.form.get("slug", ""),
                request.form.get("whatsapp", ""),
                request.form.get("online_ativo") == "1",
                request.form.get("cancelamento_horas", ""),
                request.form.get("limite_por_cliente", ""),
                request.form.get("nome"),
            )
        except ValueError as erro:
            flash(str(erro))
        else:
            flash("Link de agendamento salvo.", "ok")
        return redirect(url_for("configurar_link"))
    return render_template(
        "configurar_link.html",
        barbearia=models.buscar_barbearia(barbearia_id),
        horas_cancelamento=publico.HORAS_CANCELAMENTO,
        limites=publico.LIMITES_POR_CLIENTE,
    )


@app.route("/configuracoes/link/qrcode.svg")
@somente_dono
def qrcode_do_link():
    """QR code do link, para imprimir e deixar no balcão ou no espelho."""
    import io

    import qrcode
    import qrcode.image.svg

    barbearia = models.buscar_barbearia(barbearia_logada())
    endereco = url_for("pagina_publica", slug=barbearia["slug"], _external=True)
    imagem = qrcode.make(endereco, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    saida = io.BytesIO()
    imagem.save(saida)
    return Response(saida.getvalue(), mimetype="image/svg+xml")


# ---------- PÁGINAS PÚBLICAS (CLIENTE DA BARBEARIA, SEM LOGIN) ----------

def _barbearia_publica(slug):
    barbearia = publico.buscar_por_slug(slug)
    if barbearia is None:
        abort(404)
    if not assinatura.situacao(barbearia)["liberado"]:
        # Assinatura vencida: a página aparece como pausada para o cliente.
        barbearia = dict(barbearia)
        barbearia["online_ativo"] = 0
    return barbearia


def _ip():
    return request.remote_addr or "desconhecido"


@app.route("/b/<slug>")
def pagina_publica(slug):
    barbearia = _barbearia_publica(slug)
    barbearia_id = barbearia["id"]
    hoje = agenda.hoje()
    unidades = agenda.listar_unidades(barbearia_id, somente_ativas=True)
    dias = [hoje + timedelta(days=i) for i in range(publico.DIAS_NA_FAIXA)]
    dados_unidades = []
    for unidade in unidades:
        horarios = agenda.horarios_da_unidade(barbearia_id, unidade["id"])
        dados_unidades.append({
            "id": unidade["id"],
            "nome": unidade["nome"],
            "endereco": unidade["endereco"],
            "dias_abertos": sorted(dia for dia, faixas in horarios.items() if faixas),
            "barbeiros": [
                {"id": b["id"], "nome": b["nome"]}
                for b in agenda.barbeiros_da_unidade(barbearia_id, unidade["id"])
            ],
        })
    return render_template(
        "publico_agendar.html",
        barbearia=barbearia,
        unidades=dados_unidades,
        servicos=models.listar_servicos(barbearia_id, somente_ativos=True),
        dias=[{"data": d, "curto": agenda.DIAS_CURTOS[d.weekday()], "semana": d.weekday()}
              for d in dias],
        hoje=hoje,
        ultimo_dia=hoje + timedelta(days=agenda.JANELA_DIAS),
        meses=agenda.MESES,
    )


@app.route("/b/<slug>/horarios")
def horarios_publicos(slug):
    barbearia = _barbearia_publica(slug)
    if not barbearia["online_ativo"]:
        return jsonify({"horarios": [], "erro": "Agendamento pelo link pausado."})
    if not publico.pode_tentar(f"horarios:{_ip()}", 120, 60):
        return jsonify({"horarios": [], "erro": "Muitas consultas seguidas. Espere um minuto."}), 429
    try:
        horarios = agenda.horarios_livres(
            barbearia["id"],
            request.args.get("unidade"),
            request.args.get("data"),
            [s for s in request.args.get("servicos", "").split(",") if s],
            request.args.get("barbeiro") or None,
        )
    except ValueError as erro:
        return jsonify({"horarios": [], "erro": str(erro)})
    # O cliente não precisa saber quais barbeiros estão livres, só o horário.
    return jsonify({"horarios": [{"hora": h["hora"]} for h in horarios]})


@app.route("/b/<slug>/agendar", methods=["POST"])
def agendar_publico(slug):
    barbearia = _barbearia_publica(slug)
    voltar = url_for("pagina_publica", slug=barbearia["slug"])
    if request.form.get("site"):  # campo escondido: só robô preenche
        abort(400)
    if request.form.get("aceite") != "1":
        flash("Para marcar, confirme que leu como seus dados são usados.")
        return redirect(voltar)
    if not publico.pode_tentar(f"agendar:{_ip()}", 10, 60 * 60):
        flash("Muitos agendamentos seguidos deste aparelho. Tente de novo mais tarde.")
        return redirect(voltar)
    try:
        token = publico.agendar(
            barbearia,
            request.form.get("unidade_id"),
            request.form.getlist("servico_id"),
            request.form.get("data", ""),
            request.form.get("hora", ""),
            request.form.get("barbeiro_id") or None,
            request.form.get("nome", ""),
            request.form.get("whatsapp", ""),
        )
    except ValueError as erro:
        flash(str(erro))
        return redirect(voltar)
    return redirect(url_for("horario_publico", slug=barbearia["slug"], token=token, novo=1))


def _agendamento_publico(slug, token):
    barbearia = _barbearia_publica(slug)
    agendamento = publico.buscar_por_token(barbearia["id"], token)
    if agendamento is None:
        abort(404)
    return barbearia, agendamento


@app.route("/b/<slug>/horario/<token>")
def horario_publico(slug, token):
    barbearia, agendamento = _agendamento_publico(slug, token)
    inicio = agenda.ler_momento(agendamento["inicio"])
    unidade = agenda.buscar_unidade(barbearia["id"], agendamento["unidade_id"])
    return render_template(
        "publico_horario.html",
        barbearia=barbearia,
        agendamento=agendamento,
        unidade=unidade,
        quando=(f"{agenda.DIAS_DA_SEMANA[inicio.weekday()]}, {inicio.day} de "
                f"{agenda.MESES[inicio.month - 1]}, às {agendamento['hora']}"),
        novo=request.args.get("novo") == "1",
        pode_cancelar=publico.pode_cancelar(barbearia, agendamento),
        prazo=publico.prazo_para_cancelar(barbearia, agendamento),
    )


@app.route("/b/<slug>/horario/<token>/cancelar", methods=["POST"])
def cancelar_publico(slug, token):
    barbearia, _ = _agendamento_publico(slug, token)
    try:
        publico.cancelar(barbearia, token)
    except ValueError as erro:
        flash(str(erro))
    else:
        flash("Horário cancelado. Se quiser, marque outro.", "ok")
    return redirect(url_for("horario_publico", slug=barbearia["slug"], token=token))


@app.route("/b/<slug>/horario/<token>/calendario.ics")
def calendario_publico(slug, token):
    barbearia, agendamento = _agendamento_publico(slug, token)
    endereco = url_for("horario_publico", slug=barbearia["slug"], token=token, _external=True)
    return Response(
        publico.arquivo_calendario(barbearia, agendamento, endereco),
        mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="horario-barbearia.ics"'},
    )


@app.route("/b/<slug>/privacidade")
def privacidade_publica(slug):
    return render_template("publico_privacidade.html", barbearia=_barbearia_publica(slug))


@app.after_request
def proteger_paginas_publicas(resposta):
    # O link do horário do cliente é secreto: não vai para outros sites
    # nem fica guardado em cache compartilhado.
    if request.path.startswith("/b/"):
        resposta.headers["Referrer-Policy"] = "no-referrer"
        if "/horario/" in request.path:
            resposta.headers["Cache-Control"] = "no-store"
    return resposta


# ---------- CADASTRO DE BARBEARIA (QUEM COMPRA O MEUBARBER) ----------

@app.route("/cadastro", methods=["GET", "POST"])
def cadastrar_barbearia():
    if g.usuario is not None:
        return redirect(url_for("agenda_dia"))
    if not cadastro.cadastro_aberto():
        return render_template("cadastro.html", fechado=True), 403
    if request.method == "POST":
        if request.form.get("site"):  # campo escondido: só robô preenche
            abort(400)
        if request.form.get("aceite") != "1":
            flash("Para criar a conta, aceite os termos de uso.")
            return render_template("cadastro.html", dados=request.form), 400
        if not publico.pode_tentar(f"cadastro:{_ip()}", 3, 60 * 60):
            flash("Muitas contas criadas deste aparelho. Tente de novo mais tarde.")
            return render_template("cadastro.html", dados=request.form), 429
        try:
            dono = cadastro.criar_conta(
                request.form.get("nome_barbearia", ""),
                request.form.get("usuario", ""),
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
                request.form.get("whatsapp", ""),
            )
        except ValueError as erro:
            flash(str(erro))
            return render_template("cadastro.html", dados=request.form), 400
        _iniciar_sessao(dono)
        barbearia = models.buscar_barbearia(dono["barbearia_id"])
        if not assinatura.situacao(barbearia)["liberado"]:
            flash("Conta criada. Agora é só pagar a primeira mensalidade para liberar o acesso.", "ok")
            return redirect(url_for("assinatura_pagina"))
        flash("Conta criada. Siga os primeiros passos abaixo para abrir a agenda.", "ok")
        return redirect(url_for("agenda_dia"))
    return render_template("cadastro.html", dados={})


@app.route("/robots.txt")
def robots():
    """Buscadores podem ler a página de vendas, o cadastro e os termos; o resto não."""
    texto = "User-agent: *\nAllow: /$\nAllow: /cadastro\nAllow: /termos\nAllow: /b/\nDisallow: /\n"
    return app.response_class(texto, mimetype="text/plain")


@app.route("/termos")
def termos():
    return render_template("termos.html")


# ---------- ASSINATURA DO MEUBARBER ----------

@app.route("/assinatura")
@login_obrigatorio
def assinatura_pagina():
    return render_template(
        "assinatura.html",
        situacao=assinatura.situacao(g.barbearia),
        valor=assinatura.valor_plano(),
        cobranca_ativa=assinatura.cobranca_ativa(),
    )


@app.route("/assinatura/assinar", methods=["POST"])
@somente_dono
def assinar():
    try:
        link = assinatura.assinar(
            g.barbearia, request.form.get("documento", ""), request.form.get("email", "")
        )
    except (ValueError, assinatura.ErroCobranca) as erro:
        flash(str(erro))
        return redirect(url_for("assinatura_pagina"))
    # Volta para a tela da assinatura, que mostra o botão da fatura (um link
    # comum: a política de segurança não deixa formulário redirecionar para
    # outro site).
    flash("Fatura gerada. Clique em Pagar agora e escolha Pix, boleto ou cartão.", "ok")
    return redirect(url_for("assinatura_pagina"))


@app.route("/webhooks/asaas", methods=["POST"])
@csrf.exempt
def aviso_asaas():
    """Avisos de pagamento do Asaas. Sem o token certo, é recusado."""
    if not assinatura.token_valido(request.headers.get("asaas-access-token")):
        abort(401)
    evento = request.get_json(silent=True)
    if not isinstance(evento, dict):
        abort(400)
    resultado = assinatura.processar_evento(evento)
    app.logger.info("Aviso do Asaas %s: %s", evento.get("event"), resultado)
    return jsonify({"received": True})


if __name__ == "__main__":
    database.preparar_banco()  # cria as tabelas ou atualiza um banco antigo
    app.run(debug=DEBUG)
