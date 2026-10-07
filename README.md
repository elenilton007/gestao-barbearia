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
| `dados_exemplo.sql` | Dados de demonstração (*Barbearia Exemplo*), usados só por `python database.py` |
| `schema_usuarios.sql` | Tabelas de usuários de login e de tentativas de login erradas (aplicadas sem apagar dados) |
| `database.py` | Camada de conexão (SQLite ou PostgreSQL), criação das tabelas e atualização de bancos antigos |
| `models.py` | Operações de CRUD das entidades e autenticação de usuários, sempre filtradas por barbearia |
| `criar_usuario.py` | Linha de comando para cadastrar usuários (dono ou barbeiro) e barbearias novas |
| `reports.py` | Consultas SQL avançadas: faturamento, comissões, ranking de serviços/clientes, por barbearia |
| `app.py` | Aplicação web Flask (rotas, páginas, login e permissões) |
| `templates/` | Páginas HTML (login, troca de senha, dashboard, clientes, atendimentos, relatórios, barbeiros, serviços, usuários) |
| `static/style.css` | Estilo visual da aplicação |
| `tests/` | Testes automatizados (models, relatórios e rotas Flask) |
| `Dockerfile` | Imagem de produção: cria as tabelas e sobe o Gunicorn |
| `render.yaml` | Blueprint do Render: site no plano gratuito (Gunicorn), com o banco PostgreSQL do Neon |

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
Exemplo*) e os barbeiros, serviços e clientes dela (veja
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
| `DATABASE_URL` | Endereço do PostgreSQL (`postgresql://usuario:senha@servidor:5432/banco`). Sem ela, o banco é o SQLite. |
| `BARBEARIA_DB` | Caminho do arquivo do banco SQLite, quando não há `DATABASE_URL` (padrão: `barbearia.db`). |
| `SESSAO_INATIVIDADE_MINUTOS` | Minutos sem uso até o login expirar (padrão: `30`). |
| `COOKIE_SEGURO` | `1` faz o cookie de login só trafegar por HTTPS. Use em produção (o `render.yaml` já liga); deixe desligado ao testar em `http://`. |
| `PORT` / `WEB_CONCURRENCY` | Só no Docker: porta do Gunicorn (padrão `8000`; o Render define a dele) e número de processos (padrão `2`). |

Para gerar uma `SECRET_KEY` forte:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> ⚠️ Nunca use `FLASK_DEBUG=1` em um servidor exposto na internet: o
> debugger do Werkzeug permite executar código remotamente. O servidor
> embutido do Flask serve apenas para desenvolvimento.

Os formulários são protegidos contra CSRF com o Flask-WTF.

## 🌐 Publicar na internet de graça (Render + Neon)

Até aqui o sistema só roda no seu computador (`127.0.0.1` quer dizer
"esta máquina"). Para o dono da barbearia e os barbeiros entrarem pelo
navegador de qualquer lugar — celular, computador do balcão — o sistema
precisa estar num servidor na internet. Este passo a passo usa só planos
**gratuitos**:

- **[Render](https://render.com)** (plano Free): roda o site com o
  **Gunicorn**, a partir do `Dockerfile` e do `render.yaml` deste
  repositório, com **HTTPS** automático e o cookie de login marcado como
  seguro (`COOKIE_SEGURO=1`);
- **[Neon](https://neon.tech)** (plano Free): guarda os dados num
  **PostgreSQL** (variável `DATABASE_URL`). O SQLite do Render seria
  apagado a cada nova versão publicada, e o banco gratuito do próprio
  Render expira depois de um tempo; o do Neon não expira.

No seu computador nada muda: sem `DATABASE_URL`, o sistema continua
usando o SQLite (`barbearia.db`).

### 1. Criar o banco no Neon

1. Crie uma conta em <https://neon.tech> (dá para entrar com o GitHub).
2. Crie um projeto (por exemplo `gestao-barbearia`). Na região, escolha a
   mais perto de onde o site vai ficar no Render — por exemplo **AWS US
   East (Ohio)** com o Render em **Ohio**.
3. No painel do projeto, clique em **Connect** e copie a *connection
   string*. Ela parece com:

   ```
   postgresql://usuario:senha@ep-xxxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   Prefira a versão com **pooling** (o endereço tem `-pooler`). Essa linha
   é a sua `DATABASE_URL`: ela contém a senha do banco, então **nunca** a
   coloque no repositório.

As tabelas não precisam ser criadas à mão: o site cria quando sobe.

### 2. Criar o site no Render

1. Crie uma conta em <https://render.com> entrando com o GitHub e
   autorize o acesso ao repositório `gestao-barbearia`.
2. No painel, clique em **New → Blueprint** e escolha o repositório. O
   Render lê o `render.yaml` e monta o site **gestao-barbearia** no plano
   **Free**, a partir do `Dockerfile`, com uma `SECRET_KEY` aleatória e
   `COOKIE_SEGURO=1`.
3. O Render pede os valores das variáveis e confirme em **Apply**:
   - **`DATABASE_URL`**: a connection string do Neon;
   - **`DONO_USUARIO`** e **`DONO_SENHA`** (mínimo de 8 caracteres): o
     login do primeiro dono;
   - **`BARBEARIA_NOME`**: o nome da barbearia (se ficar vazio, vira
     "Minha Barbearia").
4. Espere o deploy terminar (alguns minutos). Ao iniciar, o contêiner
   roda `python database.py --preparar`, que cria as tabelas vazias (sem
   os dados de exemplo) e nunca apaga dados — roda a cada deploy. Se o
   banco ainda não tem nenhum usuário, ele também cria a barbearia e o
   dono de `DONO_USUARIO`/`DONO_SENHA`. Depois sobe o Gunicorn.
5. O endereço do site aparece no topo da página do serviço, algo como
   **https://gestao-barbearia.onrender.com**. Entre com o usuário e a
   senha do dono e cadastre os barbeiros, os serviços e os usuários dos
   barbeiros pelas telas.
6. Depois de entrar, apague `DONO_SENHA` em **Environment** no Render
   (com o dono criado, as variáveis não são mais usadas). Troque a senha
   pelo menu do sistema quando quiser.

<details>
<summary>Prefere criar o site à mão, sem o Blueprint?</summary>

1. **New → Web Service**: escolha o repositório; o Render detecta o
   `Dockerfile` (*Language: Docker*). Em **Instance Type**, escolha
   **Free**.
2. Em **Environment Variables**, adicione:
   - `DATABASE_URL` = a connection string do Neon;
   - `SECRET_KEY` = o resultado de
     `python -c "import secrets; print(secrets.token_hex(32))"`;
   - `COOKIE_SEGURO` = `1`;
   - `DONO_USUARIO`, `DONO_SENHA` e `BARBEARIA_NOME` = o primeiro dono.
3. Em **Health Check Path**, coloque `/login` e crie o serviço.

</details>

### 3. Criar o primeiro dono pelo computador (opcional)

Se você não definiu `DONO_USUARIO`/`DONO_SENHA` no Render (o plano
gratuito não tem terminal no servidor), crie o dono do seu computador,
conectando direto no banco do Neon:

1. Dentro da pasta do projeto e com o ambiente virtual ativado (passos 2
   e 3 da instalação), rode, colando a connection string do Neon:

   Linux/macOS:

   ```bash
   DATABASE_URL="cole-aqui-a-connection-string-do-Neon" \
     python criar_usuario.py dono elenilton --nova-barbearia "Nome da Barbearia"
   ```

   Windows (PowerShell):

   ```powershell
   $env:DATABASE_URL="cole-aqui-a-connection-string-do-Neon"
   python criar_usuario.py dono elenilton --nova-barbearia "Nome da Barbearia"
   Remove-Item Env:DATABASE_URL
   ```

2. Abra o endereço do site, entre com esse usuário e cadastre os
   barbeiros, os serviços e os usuários dos barbeiros pelas telas.

> ⚠️ Com a `DATABASE_URL` definida, **não** rode `python database.py`
> sem argumentos: ele apaga tudo. Por segurança, no PostgreSQL ele se
> recusa a rodar sem `--apagar-tudo`. Para só criar as tabelas, use
> `python database.py --preparar`.

### 4. Passar o endereço para a barbearia

Mande o link (por exemplo `https://gestao-barbearia.onrender.com`) para o
dono e os barbeiros. Cada um entra com o próprio usuário e senha, de
qualquer navegador. No celular, dá para usar **Adicionar à tela de
início** para abrir como um aplicativo.

Para usar um endereço próprio (como `sistema.suabarbearia.com.br`), vá em
**Settings → Custom Domains** do serviço e siga as instruções de DNS; o
Render emite o certificado HTTPS sozinho.

Toda mudança mesclada na `main` é publicada automaticamente
(**Auto-Deploy**); os dados ficam no Neon e não se perdem.

> 💡 **Limites do plano gratuito** (confira os valores atuais nos sites):
> o site do Render "dorme" após uns 15 minutos sem acesso e leva cerca de
> um minuto para acordar no próximo acesso. O Neon também pausa o banco
> sem uso (acorda sozinho em segundos) e tem limite de armazenamento —
> sobra para começar. Quando houver barbearias pagando, passe para os
> planos pagos, que não dormem e têm mais backup.

### Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Deploy falha com erro de conexão ao banco | Confira a `DATABASE_URL` em **Environment** no Render: é a connection string do Neon, com `?sslmode=require` no fim. |
| Primeiro acesso demora | Normal no plano gratuito: o site estava dormindo. |
| Todo mundo foi deslogado | A `SECRET_KEY` mudou. Não a troque à toa no painel do Render. |
| `criar_usuario.py` diz que o usuário já existe | O nome de usuário é único no sistema todo; escolha outro. |

### Rodar a imagem Docker no seu computador

```bash
docker build -t gestao-barbearia .
docker run -p 8000:8000 -e SECRET_KEY=troque-esta-chave gestao-barbearia
```

Acesse **http://127.0.0.1:8000**. Sem `DATABASE_URL` o contêiner usa um
SQLite interno, que some junto com o contêiner — sirva-se dele só para
testar. Para usar um PostgreSQL, passe
`-e DATABASE_URL=postgresql://...`.

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
| `test_producao.py` | Tradução do SQL para o PostgreSQL, `database.py --preparar` sem apagar dados, primeiro dono pelas variáveis `DONO_USUARIO`/`DONO_SENHA`, proteção contra apagar o PostgreSQL, cookie seguro e o app rodando no Gunicorn |

O GitHub Actions roda esses testes a cada push e pull request
(`.github/workflows/testes.yml`), uma vez no SQLite e outra no
PostgreSQL, e também constrói a imagem Docker e confere que ela sobe. O
selo no topo deste README mostra o resultado da última execução na `main`.

Cada teste roda em um banco SQLite temporário (veja `tests/conftest.py`),
então o seu `barbearia.db` nunca é alterado pelos testes. A `DATABASE_URL`
também é ignorada pelos testes, para nunca apagarem o banco de produção.

Para rodar os testes no PostgreSQL, aponte `TEST_DATABASE_URL` para um
banco **só de testes** (ele é apagado e recriado a cada teste):

```bash
TEST_DATABASE_URL=postgresql://usuario:senha@localhost:5432/barbearia_teste pytest -v
```

## 🔧 Tecnologias

- Python 3
- Flask
- SQLite no desenvolvimento e PostgreSQL em produção (SQL puro, sem ORM —
  para deixar as queries explícitas)
- Gunicorn, Docker, Render e Neon (deploy gratuito)
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
