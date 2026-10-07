# 💈 Sistema de Gestão de Barbearia

[![Testes](https://github.com/elenilton007/gestao-barbearia/actions/workflows/testes.yml/badge.svg)](https://github.com/elenilton007/gestao-barbearia/actions/workflows/testes.yml)

Aplicação web full-stack (Python + Flask + SQL) para gestão de clientes, atendimentos, comissões de barbeiros e relatórios financeiros — inspirada em 21 anos de experiência real administrando uma barbearia.

## 📋 Sobre o projeto

Depois de duas décadas gerindo um negócio próprio (fluxo de caixa, comissão de equipe, controle de clientes), este projeto transforma essa vivência prática em um sistema de gestão real, aplicando conceitos de:

- Modelagem de banco de dados relacional (SQL)
- Desenvolvimento web com Flask (Python)
- Consultas SQL avançadas para relatórios gerenciais
- Arquitetura em camadas (banco de dados / regras de negócio / interface)
- Testes automatizados

## 🧠 Arquitetura

| Arquivo/Pasta | Responsabilidade |
|---|---|
| `schema.sql` | Estrutura do banco de dados (clientes, barbeiros, serviços, atendimentos) |
| `schema_usuarios.sql` | Tabela de usuários de login (aplicada sem apagar dados) |
| `database.py` | Camada de conexão e inicialização do banco (SQLite) |
| `models.py` | Operações de CRUD das entidades e autenticação de usuários |
| `criar_usuario.py` | Linha de comando para cadastrar usuários (dono ou barbeiro) |
| `reports.py` | Consultas SQL avançadas: faturamento, comissões, ranking de serviços/clientes |
| `app.py` | Aplicação web Flask (rotas, páginas, login e permissões) |
| `templates/` | Páginas HTML (login, dashboard, clientes, atendimentos, relatórios) |
| `static/style.css` | Estilo visual da aplicação |
| `tests/` | Testes automatizados (models, relatórios e rotas Flask) |

## 📊 Funcionalidades

- **Login com dois papéis**:
  - **dono** — acesso total: faturamento, comissões de todos, relatórios
  - **barbeiro** — vê só os próprios atendimentos e a própria comissão;
    registra atendimentos apenas em seu nome e não acessa os relatórios
- **Dashboard gerencial**: faturamento do mês, ticket médio, top serviços, top clientes, comissões
- **Cadastro de clientes**
- **Registro de atendimentos**: vincula cliente, barbeiro, serviço e forma de pagamento
- **Relatórios**: faturamento mensal histórico, ranking de serviços e clientes
- **Cálculo automático de comissão** por barbeiro, baseado em percentual individual

## ▶️ Instalação e execução

### Pré-requisitos

- Python 3.10 ou superior
- Git

### 1. Clonar o repositório

```bash
git clone https://github.com/elenilton007/gestao-barbearia.git
cd gestao-barbearia
```

### 2. Criar e ativar um ambiente virtual

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt        # só para rodar a aplicação
pip install -r requirements-dev.txt    # inclui o pytest, para rodar os testes
```

### 4. Inicializar o banco de dados

```bash
python database.py
```

Cria o arquivo `barbearia.db` com barbeiros, serviços e clientes de exemplo.

> ⚠️ Este comando **recria o banco do zero e apaga todos os dados**
> existentes. Rode-o apenas na primeira instalação.

Para usar outro arquivo de banco, defina a variável de ambiente
`BARBEARIA_DB` (vale tanto para `database.py` quanto para `app.py`):

```bash
BARBEARIA_DB=/caminho/para/minha.db python database.py
```

### 5. Criar os usuários de login

Todas as páginas exigem login. Crie primeiro o usuário dono (a senha é
pedida no terminal e precisa ter pelo menos 8 caracteres):

```bash
python criar_usuario.py dono elenilton
```

Para cada barbeiro, crie um usuário vinculado ao id dele na tabela
`barbeiros` (rode sem `--barbeiro-id` para ver a lista de ids):

```bash
python criar_usuario.py barbeiro joao --barbeiro-id 2
```

> 💡 **Já tem um `barbearia.db` com dados?** Não rode `python database.py`
> de novo. O `criar_usuario.py` cria a tabela de usuários no banco
> existente sem apagar nada.

### 6. Rodar a aplicação

Para desenvolvimento local, ligue o modo debug (ele gera uma `SECRET_KEY`
temporária automaticamente):

Linux/macOS:

```bash
FLASK_DEBUG=1 python app.py
```

Windows (PowerShell):

```powershell
$env:FLASK_DEBUG="1"; python app.py
```

Acesse **http://127.0.0.1:5000** no navegador e entre com o usuário
criado no passo 5.

### Variáveis de ambiente

| Variável | Para que serve |
|---|---|
| `SECRET_KEY` | Assina a sessão de login e os tokens CSRF dos formulários. **Obrigatória** fora do modo debug — o app não inicia sem ela. |
| `FLASK_DEBUG` | `1` liga o modo debug. Desligado por padrão. |
| `BARBEARIA_DB` | Caminho do arquivo do banco SQLite (padrão: `barbearia.db`). |

Para gerar uma `SECRET_KEY` forte:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> ⚠️ Nunca use `FLASK_DEBUG=1` em um servidor exposto na internet: o
> debugger do Werkzeug permite executar código remotamente. O servidor
> embutido do Flask serve apenas para desenvolvimento.

Os formulários são protegidos contra CSRF com o Flask-WTF.

## 🧪 Testes

```bash
pytest -v
```

Os testes ficam em `tests/` e cobrem:

| Arquivo | O que testa |
|---|---|
| `test_models.py` | Cadastro e listagem de clientes e atendimentos |
| `test_reports.py` | Faturamento total, cálculo/arredondamento de comissões e ranking de serviços |
| `test_app.py` | Rotas Flask: páginas carregam, formulários cadastram e redirecionam |
| `test_auth.py` | Login/logout, páginas bloqueadas sem login, dono vê tudo, barbeiro vê só as próprias comissões e atendimentos |
| `test_criar_usuario.py` | Script `criar_usuario.py`: validações e criação da tabela em banco antigo sem perder dados |
| `test_security.py` | `SECRET_KEY` obrigatória, debug desligado por padrão e proteção CSRF |

O GitHub Actions roda esses testes a cada push e pull request
(`.github/workflows/testes.yml`). O selo no topo deste README mostra
o resultado da última execução na `main`.

Cada teste roda em um banco SQLite temporário (veja `tests/conftest.py`),
então o seu `barbearia.db` nunca é alterado pelos testes.

## 🔧 Tecnologias

- Python 3
- Flask
- SQLite (SQL puro, sem ORM — para deixar as queries explícitas)
- Jinja2 (templates HTML)
- Pytest (testes automatizados)

## 🚀 Próximos passos

Veja **[SAAS_ROADMAP.md](SAAS_ROADMAP.md)** para a lista completa do que falta
para oferecer o sistema como SaaS (multi-barbearia, login, agenda online,
cobrança, LGPD, deploy). Destaques:

- Tela para o dono cadastrar usuários e barbeiros (hoje é pela linha de comando)
- Agenda e agendamento online
- Exportação de relatórios em PDF/Excel
- Gráficos interativos no dashboard

## 👤 Autor

**Elenilton Santos da Silveira**
Técnico em Desenvolvimento de Sistemas | Técnico em Automação Industrial
[LinkedIn](https://www.linkedin.com/in/elenilton-santos-da-silveira-450952285)
