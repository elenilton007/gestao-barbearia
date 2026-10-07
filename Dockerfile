# Imagem de produção do Sistema de Gestão de Barbearia.
#
#   docker build -t gestao-barbearia .
#   docker run -p 8000:8000 -e SECRET_KEY=... -e DATABASE_URL=... gestao-barbearia
#
# Ao iniciar, cria as tabelas se o banco estiver vazio (sem apagar nada) e
# o primeiro dono (DONO_USUARIO/DONO_SENHA, veja preparar_banco.py), e
# sobe o Gunicorn na porta da variável PORT (o Render define a dele).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WEB_CONCURRENCY=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Sem root dentro do contêiner. A pasta /app fica do usuário app para o
# SQLite conseguir criar o barbearia.db quando não houver DATABASE_URL.
RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "python preparar_banco.py && exec gunicorn app:app --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY} --access-logfile -"]
