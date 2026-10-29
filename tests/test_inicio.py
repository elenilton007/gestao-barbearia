"""Página de vendas em / para quem não entrou."""


def test_visitante_ve_a_pagina_de_vendas(client_anonimo):
    resposta = client_anonimo.get("/")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert "Começar 7 dias grátis" in html
    assert "/cadastro" in html and "/login" in html
    assert "R$ 49,90" in html
    assert 'name="description"' in html
    # Nada do painel aparece para o visitante.
    assert "Faturamento" not in html and "Sair" not in html


def test_preco_e_teste_vem_da_configuracao(client_anonimo, monkeypatch):
    monkeypatch.setenv("PLANO_VALOR", "59.90")
    monkeypatch.setenv("TESTE_DIAS", "7")
    html = client_anonimo.get("/").get_data(as_text=True)
    assert "R$ 59,90" in html and "7 dias grátis" in html


def test_botao_de_whatsapp_so_com_numero_configurado(client_anonimo, monkeypatch):
    monkeypatch.delenv("CONTATO_WHATSAPP", raising=False)
    assert "wa.me" not in client_anonimo.get("/").get_data(as_text=True)
    monkeypatch.setenv("CONTATO_WHATSAPP", "(71) 98811-2040")
    html = client_anonimo.get("/").get_data(as_text=True)
    assert "https://wa.me/5571988112040?text=" in html


def test_logado_continua_vendo_o_painel(client):
    html = client.get("/").get_data(as_text=True)
    assert "Começar 7 dias grátis" not in html
    assert "Sair" in html


def test_robots_libera_so_as_paginas_publicas(client_anonimo):
    resposta = client_anonimo.get("/robots.txt")
    assert resposta.status_code == 200
    texto = resposta.get_data(as_text=True)
    assert "Allow: /$" in texto and "Allow: /cadastro" in texto and "Disallow: /" in texto


def test_pagina_de_vendas_respeita_a_csp(client_anonimo):
    resposta = client_anonimo.get("/")
    html = resposta.get_data(as_text=True)
    assert "<script>" not in html and "onclick" not in html
    assert "frame-ancestors 'none'" in resposta.headers["Content-Security-Policy"]


def test_sem_teste_gratis_a_pagina_chama_para_assinar(client_anonimo, monkeypatch):
    monkeypatch.setenv("TESTE_DIAS", "0")
    html = client_anonimo.get("/").get_data(as_text=True)
    assert "Assinar por R$ 49,90/mês" in html
    assert "dias grátis" not in html
    assert "Quando o acesso é liberado?" in html
