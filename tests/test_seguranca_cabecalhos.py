"""
test_seguranca_cabecalhos.py

Cabeçalhos de segurança em todas as páginas (contra clickjacking, scripts
injetados e farejamento de tipo), JavaScript sem eventos inline e limite de
tentativas de login por aparelho.
"""

import os
import re

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..", "templates")


@pytest.mark.parametrize("rota", ["/login", "/cadastro", "/b/barbearia-exemplo", "/termos"])
def test_paginas_publicas_tem_cabecalhos(client_anonimo, rota):
    resposta = client_anonimo.get(rota)
    csp = resposta.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "script-src 'self' 'nonce-" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert resposta.headers["X-Frame-Options"] == "DENY"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"


def test_paginas_logadas_tem_cabecalhos(client):
    resposta = client.get("/agenda")
    assert "Content-Security-Policy" in resposta.headers
    assert resposta.headers["X-Frame-Options"] == "DENY"


def test_scripts_da_pagina_levam_o_nonce_do_pedido(client):
    resposta = client.get("/agenda")
    nonce = re.search(r"'nonce-([^']+)'", resposta.headers["Content-Security-Policy"]).group(1)
    html = resposta.get_data(as_text=True)
    scripts = re.findall(r"<script([^>]*)>", html)
    assert scripts
    for atributos in scripts:
        assert f'nonce="{nonce}"' in atributos or "src=" in atributos


def test_nonce_muda_a_cada_pedido(client):
    a = client.get("/agenda").headers["Content-Security-Policy"]
    b = client.get("/agenda").headers["Content-Security-Policy"]
    assert a != b


def test_nenhum_template_usa_evento_inline():
    for nome in os.listdir(RAIZ):
        texto = open(os.path.join(RAIZ, nome), encoding="utf-8").read()
        assert not re.search(r"\son(click|submit|change|load|input)=", texto), nome


def test_hsts_so_com_cookie_seguro(client_anonimo):
    from app import app

    assert "Strict-Transport-Security" not in client_anonimo.get("/login").headers
    app.config["SESSION_COOKIE_SECURE"] = True
    try:
        assert "max-age" in client_anonimo.get("/login").headers["Strict-Transport-Security"]
    finally:
        app.config["SESSION_COOKIE_SECURE"] = False


def test_cookie_de_sessao_nao_e_lido_por_javascript(client_anonimo):
    cabecalho = client_anonimo.get("/login").headers.get("Set-Cookie", "")
    assert "HttpOnly" in cabecalho and "SameSite=Lax" in cabecalho


def test_limite_de_login_por_aparelho(client_anonimo):
    for i in range(30):
        client_anonimo.post("/login", data={"usuario": f"chute{i}", "senha": "123456789"})
    resposta = client_anonimo.post("/login", data={"usuario": "dono", "senha": "senha-do-dono"})
    assert resposta.status_code == 429
    assert "Muitas tentativas deste aparelho" in resposta.get_data(as_text=True)
