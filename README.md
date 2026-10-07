# 💈 Sistema de Gestão de Barbearia

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
| `database.py` | Camada de conexão e inicialização do banco (SQLite) |
| `models.py` | Operações de CRUD das entidades |
| `reports.py` | Consultas SQL avançadas: faturamento, comissões, ranking de serviços/clientes |
| `app.py` | Aplicação web Flask (rotas e páginas) |
| `templates/` | Páginas HTML (dashboard, clientes, atendimentos, relatórios) |
| `static/style.css` | Estilo visual da aplicação |
| `tests/` | Testes automatizados (models, relatórios e rotas Flask) |

## 📊 Funcionalidades

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

### 5. Rodar a aplicação

```bash
python app.py
```

Acesse **http://127.0.0.1:5000** no navegador.

> O servidor embutido do Flask roda em modo debug e serve apenas para
> desenvolvimento — não o exponha na internet.

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

- Autenticação de usuários (administrador x barbeiro)
- Agenda e agendamento online
- Exportação de relatórios em PDF/Excel
- Gráficos interativos no dashboard

## 👤 Autor

**Elenilton Santos da Silveira**
Técnico em Desenvolvimento de Sistemas | Técnico em Automação Industrial
[LinkedIn](https://www.linkedin.com/in/elenilton-santos-da-silveira-450952285)
