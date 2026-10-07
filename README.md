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
| `render.yaml` | Blueprint do Render: banco PostgreSQL + site, de uma vez |

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

## 🌐 Publicar na internet (Render)

Até aqui o sistema só roda no seu computador (`127.0.0.1` quer dizer
"esta máquina"). Para o dono da barbearia e os barbeiros entrarem pelo
navegador de qualquer lugar — celular, computador do balcão — o sistema
precisa estar num servidor na internet. Este passo a passo usa o
[Render](https://render.com), que tem plano gratuito e lê o `Dockerfile`
e o `render.yaml` deste repositório.

Em produção o sistema roda com:

- **Gunicorn** no lugar do servidor de desenvolvimento do Flask;
- **PostgreSQL** no lugar do SQLite (variável `DATABASE_URL`). O SQLite
  do Render seria apagado a cada nova versão publicada;
- **HTTPS** automático do Render, com o cookie de login marcado como
  seguro (`COOKIE_SEGURO=1`).

### 1. Criar o banco e o site

1. Crie uma conta em <https://render.com> entrando com o GitHub e
   autorize o acesso ao repositório `gestao-barbearia`.
2. No painel, clique em **New → Blueprint**, escolha o repositório e
   confirme em **Apply**. O Render lê o `render.yaml` e cria:
   - o banco **gestao-barbearia-db** (PostgreSQL);
   - o site **gestao-barbearia**, construído a partir do `Dockerfile`,
     com a `DATABASE_URL` do banco e uma `SECRET_KEY` aleatória já
     configuradas.
3. Espere o deploy terminar (alguns minutos). Ao iniciar, o contêiner
   roda `python database.py --preparar`, que cria as tabelas vazias (sem
   os dados de exemplo) e nunca apaga dados — pode rodar a cada deploy.
4. O endereço do site aparece no topo da página do serviço, algo como
   **https://gestao-barbearia.onrender.com**. A tela de login já abre,
   mas ainda não existe nenhum usuário.

<details>
<summary>Prefere criar tudo à mão, sem o Blueprint?</summary>

1. **New → Postgres**: dê um nome, escolha a região e o plano, e crie.
   Copie a **Internal Database URL**.
2. **New → Web Service**: escolha o repositório; o Render detecta o
   `Dockerfile` (*Language: Docker*). Na região, use a mesma do banco.
3. Em **Environment Variables**, adicione:
   - `DATABASE_URL` = a *Internal Database URL* copiada;
   - `SECRET_KEY` = o resultado de
     `python -c "import secrets; print(secrets.token_hex(32))"`;
   - `COOKIE_SEGURO` = `1`.
4. Em **Health Check Path**, coloque `/login` e crie o serviço.

</details>

### 2. Criar o primeiro dono

O usuário dono é criado do seu computador, conectando direto no banco do
Render (funciona no plano gratuito, que não tem terminal no servidor):

1. No Render, abra o banco **gestao-barbearia-db** → **Connect** e copie a
   **External Database URL**.
2. No seu computador, dentro da pasta do projeto e com o ambiente virtual
   ativado (passos 2 e 3 da instalação), rode:

   Linux/macOS:

   ```bash
   DATABASE_URL="cole-aqui-a-External-Database-URL" \
     python criar_usuario.py dono elenilton --nova-barbearia "Nome da Barbearia"
   ```

   Windows (PowerShell):

   ```powershell
   $env:DATABASE_URL="cole-aqui-a-External-Database-URL"
   python criar_usuario.py dono elenilton --nova-barbearia "Nome da Barbearia"
   Remove-Item Env:DATABASE_URL
   ```

3. Abra o endereço do site, entre com esse usuário e cadastre os
   barbeiros, os serviços e os usuários dos barbeiros pelas telas.

> ⚠️ Com a `DATABASE_URL` definida, **não** rode `python database.py`
> sem argumentos: ele apaga tudo. Por segurança, no PostgreSQL ele se
> recusa a rodar sem `--apagar-tudo`. Para só criar as tabelas, use
> `python database.py --preparar`.

### 3. Passar o endereço para a barbearia

Mande o link (por exemplo `https://gestao-barbearia.onrender.com`) para o
dono e os barbeiros. Cada um entra com o próprio usuário e senha, de
qualquer navegador. No celular, dá para usar **Adicionar à tela de
início** para abrir como um aplicativo.

Para usar um endereço próprio (como `sistema.suabarbearia.com.br`), vá em
**Settings → Custom Domains** do serviço e siga as instruções de DNS; o
Render emite o certificado HTTPS sozinho.

Toda mudança mesclada na `main` é publicada automaticamente
(**Auto-Deploy**); os dados ficam no PostgreSQL e não se perdem.

> 💡 **Plano gratuito do Render**: o site "dorme" após uns 15 minutos sem
> acesso e leva cerca de um minuto para acordar no próximo acesso, e o
> banco gratuito expira depois de um tempo (veja os prazos atuais na
> página de preços do Render). Para uma barbearia de verdade, use os
> planos pagos do site e do banco, que também têm backup automático —
> basta trocar o `plan` no `render.yaml` ou mudar o plano no painel.

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
| `test_producao.py` | Tradução do SQL para o PostgreSQL, `database.py --preparar` sem apagar dados, proteção contra apagar o PostgreSQL, cookie seguro e o app rodando no Gunicorn |

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
- Gunicorn, Docker e Render (deploy)
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
