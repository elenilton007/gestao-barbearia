"""
telefones.py

Padroniza telefones brasileiros para "(71) 98811-2040" (celular) ou
"(71) 3311-2040" (fixo). Assim o mesmo número, digitado de jeitos
diferentes ("71988112040", "+55 71 98811-2040"), vira um cliente só.
"""

import re

MENSAGEM = "WhatsApp inválido. Use DDD e número, como (71) 98811-2040."


def so_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def normalizar(texto):
    """Telefone padronizado, None se estiver em branco, ValueError se não servir."""
    digitos = so_digitos(texto)
    if not digitos:
        return None
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if digitos.startswith("0") and len(digitos) in (11, 12):
        digitos = digitos[1:]  # 0 de discagem antes do DDD
    if len(digitos) not in (10, 11) or digitos[0] == "0" or digitos[1] == "0":
        raise ValueError(MENSAGEM)
    ddd, numero = digitos[:2], digitos[2:]
    if len(numero) == 9:
        if numero[0] != "9":
            raise ValueError(MENSAGEM)
        return f"({ddd}) {numero[:5]}-{numero[5:]}"
    return f"({ddd}) {numero[:4]}-{numero[4:]}"
