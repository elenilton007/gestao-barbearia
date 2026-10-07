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
| `schema.sql` | Estrutura do banco de dados (barbearias, clientes, barbeiros, serviços, atendimentos) |
| `dados_exemplo.sql` | Dados de exemplo (*Barbearia Exemplo*) inseridos pelo `python database.py` |
| `schema_usuarios.sql` | Tabelas de usuários de login e de tentativas de login erradas (aplicadas sem apagar dados) |
| `database.py` | Camada de conexão (SQLite local ou PostgreSQL com `DATABASE_URL`), inicialização e atualização de bancos antigos |
| `models.py` | Operações de CRUD das entidades e autenticação de usuários, sempre filtradas por barbearia |
| `criar_usuario.py` | Linha de comando para cadastrar usuários (dono ou barbeiro) e barbearias novas |
| `reports.py` | Consultas SQL avançadas: faturamento, comissões, ranking de serviços/clientes, por barbearia |
| `app.py` | Aplicação web Flask (rotas, páginas, login e permissões) |
| `templates/` | Páginas HTML (login, troca de senha, dashboard, clientes, atendimentos, relatórios, barbeiros, serviços, usuários) |
| `static/style.css` | Estilo visual da aplicação |
| `tests/` | Testes automatizados (models, relatórios e rotas Flask) |
| `render.yaml` | Deploy gratuito no Render (Gunicorn + PostgreSQL do Neon) |
| `.python-version` | Versão do Python usada no Render |

## 📊 Funcionalidades

- **Várias barbearias no mesmo sistema**: cada barbearia só vê os próprios
  clientes, barbeiros, serviços, atendimentos e relatórios. Toda tabela tem
  a coluna `barbearia_id`, e toda consulta filtra pela barbearia do usuário
  logado. Um atendimento com cliente, barbeiro ou serviço de outra
  barbearia é recusado
- **Login com dois papéis**:
  - **dono** — acesso total à própria barbearia: faturamento, comissões de todos, relatórios
  - **barbeiro** — vê só os próprios atendimentos e a própria comissão;
    registra atendimentos apenas em seu nome e não acessa os relatórios
- **Login protegido**:
  - depois de **5 senhas erradas seguidas** o usuário fica bloqueado por
    **15 minutos** (nem a senha certa entra nesse tempo); o login certo
    zera a contagem
  - a sessão **expira após 30 minutos sem uso** (configurável)
  - cada usuário (dono ou barbeiro) troca a própria senha em **Trocar senha**, no menu; as sessões
    abertas em outros aparelhos são encerradas
- **Dashboard gerencial**: faturamento do mês, ticket médio, top serviços, top clientes, comissões
- **Cadastro de clientes**
- **Cadastro de barbeiros, serviços e usuários** (só o dono, menus
  *Barbeiros*, *Serviços* e *Usuários*): cadastrar, editar (nome, comissão,
  preço, duração, papel, barbeiro vinculado, troca de senha) e desativar.
  Nada é apagado: barbeiro ou serviço desativado some do registro de
  atendimentos, mas continua no histórico e nos relatórios; usuário
  desativado não consegue entrar. O dono não pode se desativar nem tirar o
  próprio papel, e a barbearia nunca fica sem um dono ativo
- **Registro de atendimentos**: vincula cliente, barbeiro, serviço e forma de pagamento
- **Relatórios**: faturamento mensal histórico, ranking de serviços e clientes
- **Cálculo automático de comissão** por barbeiro, baseado em percentual individual; o percentual é gravado em cada atendimento, então mudar a comissão não altera os atendimentos antigos

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

Cria o arquivo `barbearia.db` com uma barbearia de exemplo (*Barbearia
Exemplo*) e os barbeiros, serviços e clientes dela (de
`dados_exemplo.sql`).

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

Depois de entrar como dono, os barbeiros, os serviços e os outros
usuários podem ser cadastrados pelas telas *Barbeiros*, *Serviços* e
*Usuários*. Pela linha de comando também dá: para cada barbeiro, crie um
usuário vinculado ao id dele na tabela `barbeiros` (rode sem
`--barbeiro-id` para ver a lista de ids):

```bash
python criar_usuario.py barbeiro joao --barbeiro-id 2
```

Enquanto houver uma barbearia só no banco, os usuários vão para ela. Para
cadastrar outra barbearia junto com o dono dela:

```bash
python criar_usuario.py dono maria --nova-barbearia "Barbearia da Maria"
```

Com mais de uma barbearia, informe `--barbearia-id` (rode sem ele para ver
a lista de ids):

```bash
python criar_usuario.py barbeiro pedro --barbearia-id 2 --barbeiro-id 5
```

O nome de usuário é único no sistema todo, mesmo entre barbearias
diferentes. Uma barbearia nova começa vazia: entre com o dono dela e
cadastre os barbeiros, os serviços e os usuários pelas telas.

> 🔒 **Usuário bloqueado por senha errada?** Espere 15 minutos e tente de
> novo. Ainda não há recuperação de senha esquecida (veja o
> [SAAS_ROADMAP.md](SAAS_ROADMAP.md)).

> 💡 **Já tem um `barbearia.db` com dados?** Não rode `python database.py`
> de novo. O `criar_usuario.py` e o `app.py` atualizam o banco existente
> sem apagar nada: criam a tabela de usuários e a coluna `ativo`, se
> faltarem, e colocam todos os dados antigos numa barbearia chamada
> *Minha Barbearia*.

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
| `DATABASE_URL` | Endereço de um PostgreSQL (`postgresql://usuario:senha@host/banco`). Se definida, é usada no lugar do SQLite. Sem ela, o sistema usa o SQLite. |
| `SESSAO_COOKIE_SEGURO` | `1` faz o cookie de login só ir por HTTPS. Ligue em produção (o `render.yaml` já liga). |
| `SESSAO_INATIVIDADE_MINUTOS` | Minutos sem uso até o login expirar (padrão: `30`). |

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
| `test_cadastros.py` | Telas de barbeiros, serviços e usuários: só o dono acessa, validações, edição, desativar/reativar, último dono ativo e isolamento entre barbearias |
| `test_barbearias.py` | Uma barbearia não vê nem altera os dados da outra (listas, relatórios, páginas e formulários) e atualização de banco antigo |
| `test_criar_usuario.py` | Script `criar_usuario.py`: validações, barbearia nova ou informada e criação da tabela em banco antigo sem perder dados |
| `test_login_seguro.py` | Bloqueio após 5 senhas erradas, troca de senha pelo dono e expiração da sessão por inatividade |
| `test_comissao_gravada.py` | Percentual de comissão gravado no atendimento: mudar a comissão do barbeiro não altera os atendimentos antigos, e banco antigo recebe a coluna |
| `test_security.py` | `SECRET_KEY` obrigatória, debug desligado por padrão e proteção CSRF |
| `test_deploy.py` | Escolha do banco pela `DATABASE_URL`, tradução do SQL para o PostgreSQL, `database.py --preparar` sem apagar dados, validação dos valores do atendimento, `render.yaml` e cookie seguro |

O GitHub Actions roda esses testes a cada push e pull request
(`.github/workflows/testes.yml`). O selo no topo deste README mostra
o resultado da última execução na `main`.

Cada teste roda em um banco SQLite temporário (veja `tests/conftest.py`),
então o seu `barbearia.db` nunca é alterado pelos testes. A `DATABASE_URL`
é ignorada nos testes, para eles nunca tocarem no banco de produção.

Para rodar os mesmos testes num PostgreSQL, aponte `TEST_DATABASE_URL`
para um banco **só de testes** (ele é apagado a cada teste):

```bash
TEST_DATABASE_URL=postgresql://postgres:senha@localhost:5432/teste pytest -v
```

O GitHub Actions roda a suíte nos dois bancos.

## ☁️ Deploy gratuito (Render + Neon)

O sistema pode ficar no ar de graça, com:

- **Render** (plano Free): roda a aplicação com o Gunicorn;
- **Neon** (plano Free): guarda os dados num PostgreSQL.

No seu computador nada muda: sem a variável `DATABASE_URL`, o sistema
continua usando o SQLite (`barbearia.db`).

> ℹ️ **Limites do plano gratuito** (confira os valores atuais nos sites):
> o Render desliga o serviço depois de 15 minutos sem acesso, e o
> primeiro acesso seguinte demora cerca de 1 minuto para carregar. O Neon
> também pausa o banco sem uso e tem limite de armazenamento — sobra para
> começar. Quando tiver clientes pagando, passe para um plano pago.

### 1. Criar o banco no Neon

1. Crie uma conta em **https://neon.tech** (dá para entrar com o GitHub).
2. Crie um projeto (ex.: `gestao-barbearia`). Escolha a região mais
   perto do Render — por exemplo **AWS US East (Ohio)** se o Render for
   ficar em Ohio.
3. No painel do projeto, clique em **Connect** e copie a *connection
   string*. Ela parece com:

   ```
   postgresql://usuario:senha@ep-xxxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   Prefira a versão com **pooling** (o endereço tem `-pooler`). Guarde
   essa linha: ela é a sua `DATABASE_URL`. Ela contém a senha do banco —
   **nunca** coloque no repositório.

As tabelas não precisam ser criadas à mão: o Render cria na primeira vez
que o serviço sobe.

### 2. Criar o serviço no Render

1. Crie uma conta em **https://render.com** e conecte o seu GitHub.
2. Clique em **New → Blueprint** e escolha o repositório
   `gestao-barbearia`. O Render lê o arquivo `render.yaml`, que já
   configura:
   - plano **Free**, Python da versão do `.python-version`;
   - instalação: `pip install -r requirements.txt`;
   - início: `python database.py --preparar && gunicorn app:app ...`;
   - `SECRET_KEY` gerada automaticamente e `SESSAO_COOKIE_SEGURO=1`.
3. O Render pede o valor de **`DATABASE_URL`**: cole a connection string
   do Neon.
4. Clique em **Apply** (ou **Deploy Blueprint**) e espere o deploy
   terminar. O endereço fica parecido com
   `https://gestao-barbearia.onrender.com`.

O `python database.py --preparar` roda a cada vez que o serviço sobe: num
banco vazio ele cria as tabelas (sem dados de exemplo); num banco que já
tem dados ele só o atualiza, **sem apagar nada**.

A cada push na `main`, o Render faz o deploy de novo sozinho.

### 3. Criar a barbearia e o primeiro usuário

O banco de produção começa vazio. O plano gratuito do Render não tem
terminal, então crie a barbearia e o dono **no seu computador**,
apontando para o banco do Neon (com o projeto instalado, como no passo
3 da instalação):

Linux/macOS:

```bash
DATABASE_URL="postgresql://...cole aqui..." python criar_usuario.py dono elenilton --nova-barbearia "Nome da Sua Barbearia"
```

Windows (PowerShell):

```powershell
$env:DATABASE_URL="postgresql://...cole aqui..."
python criar_usuario.py dono elenilton --nova-barbearia "Nome da Sua Barbearia"
Remove-Item Env:DATABASE_URL
```

Digite a senha quando pedir. Pronto: abra o endereço do Render, entre com
esse usuário e cadastre barbeiros, serviços e usuários pelas telas.

> ⚠️ **Nunca rode `python database.py` (sem `--preparar`) com a
> `DATABASE_URL` do Neon**: esse comando recria o banco do zero e apaga
> todos os dados de produção. Depois de usar a `DATABASE_URL` no
> terminal, feche-o (ou remova a variável) antes de voltar a trabalhar
> no banco local.

### Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Deploy falha com erro de conexão ao banco | Confira a `DATABASE_URL` no Render (**Environment**): ela precisa terminar com `?sslmode=require`. |
| Primeiro acesso demora | Normal no plano gratuito: o serviço estava dormindo. |
| Todo mundo foi deslogado | A `SECRET_KEY` mudou. Não a troque à toa no painel do Render. |
| `criar_usuario.py` diz que o usuário já existe | O nome de usuário é único no sistema todo; escolha outro. |

## 🔧 Tecnologias

- Python 3
- Flask
- SQLite no desenvolvimento e PostgreSQL em produção (SQL puro, sem ORM — para deixar as queries explícitas)
- Gunicorn (servidor de produção), Render (hospedagem) e Neon (PostgreSQL)
- Jinja2 (templates HTML)
- Pytest (testes automatizados)

## 🚀 Próximos passos

Veja **[SAAS_ROADMAP.md](SAAS_ROADMAP.md)** para a lista completa do que falta
para oferecer o sistema como SaaS (multi-barbearia, login, agenda online,
cobrança, LGPD, deploy). Destaques:

- Cadastro de barbearia pela web e troca de senha pelo próprio usuário
- Agenda e agendamento online
- Exportação de relatórios em PDF/Excel
- Gráficos interativos no dashboard

## 👤 Autor

**Elenilton Santos da Silveira**
Técnico em Desenvolvimento de Sistemas | Técnico em Automação Industrial
[LinkedIn](https://www.linkedin.com/in/elenilton-santos-da-silveira-450952285)
