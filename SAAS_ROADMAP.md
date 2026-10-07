# 🚀 O que falta para vender como SaaS

Análise do estado atual do projeto e do que é necessário para oferecê-lo
como serviço por assinatura para barbearias. Itens ordenados por prioridade.

## Estado atual

Hoje o sistema é uma aplicação **de uma única barbearia**, rodando
em SQLite local com o servidor de desenvolvimento do Flask. Já tem
`SECRET_KEY` por variável de ambiente, debug desligado por padrão e
proteção CSRF nos formulários (Flask-WTF), e login com os papéis *dono*
e *barbeiro* (o barbeiro vê só os próprios atendimentos e comissões).
Tem cadastro de clientes, registro de atendimentos, comissões e relatórios
básicos. Barbeiros e serviços só existem via `schema.sql` (não há tela para
cadastrá-los), e rodar `python database.py` **apaga todos os dados**
(o schema começa com `DROP TABLE`).

## 🔴 Bloqueadores (sem isso não dá para cobrar de ninguém)

1. **Multi-tenancy** — cada barbearia precisa ver só os próprios dados.
   - Criar tabela `barbearias` (tenant) e coluna `barbearia_id` em
     `clientes`, `barbeiros`, `servicos` e `atendimentos`.
   - Filtrar **todas** as queries de `models.py` e `reports.py` pelo tenant
     da sessão (hoje nenhuma filtra nada).
2. **Autenticação e permissões**
   - ~~Tabela `usuarios` com senha em hash (`werkzeug.security`), papéis
     *dono* e *barbeiro* (barbeiro vê só as próprias comissões).~~ Feito.
   - Papel *recepção*, tela para o dono gerenciar usuários (hoje é pelo
     `criar_usuario.py`), troca e recuperação de senha por e-mail.
3. **Segurança web**
   - ~~`SECRET_KEY` via variável de ambiente e proteção CSRF nos
     formulários (Flask-WTF).~~ Feito.
   - ~~Remover `debug=True` em produção.~~ Feito: o debug só liga com
     `FLASK_DEBUG=1`.
   - Validar entradas: hoje `valor_cobrado` aceita qualquer texto, IDs não
     são checados e o SQLite está com chaves estrangeiras desligadas
     (`PRAGMA foreign_keys = ON` não é executado).
   - HTTPS, cookies `Secure`/`HttpOnly`, rate limit no login.
4. **Banco de produção e migrações**
   - Migrar para PostgreSQL (SQLite não aguenta bem vários clientes
     escrevendo ao mesmo tempo).
   - Separar o schema dos dados de exemplo e usar migrações versionadas
     (Alembic) em vez de `DROP TABLE` + `CREATE TABLE`.
   - Guardar dinheiro como `NUMERIC`/centavos inteiros, não `REAL`
     (ponto flutuante gera erro de arredondamento em comissões).
   - Backups automáticos diários com teste de restauração.
5. **Cobrança da assinatura** — integração com gateway brasileiro
   (Stripe, Asaas, Pagar.me, Mercado Pago, Iugu): planos, período de teste,
   cobrança recorrente por cartão/Pix/boleto, bloqueio por inadimplência,
   emissão de nota fiscal de serviço.
6. **Conformidade legal (LGPD)** — telefone e nome de clientes são dados
   pessoais: termos de uso, política de privacidade, contrato de
   processamento de dados com a barbearia, exportação e exclusão de dados
   do titular, registro de acessos.

## 🟠 Funcionalidades que o mercado espera

Concorrentes (Trinks, AppBarber, Booksy, Avec etc.) já oferecem:

- **Agenda / agendamento online** — o recurso mais importante. Hoje o
  sistema só registra o que já aconteceu. Falta agenda por barbeiro,
  horários de funcionamento, bloqueios, e um link público para o cliente
  marcar sozinho.
- **Lembretes por WhatsApp/SMS** (confirmação e redução de faltas).
- **CRUD completo** — editar/excluir clientes e atendimentos; telas para
  cadastrar barbeiros, serviços e percentuais de comissão.
- **Preenchimento automático do valor** a partir do preço do serviço.
- **Filtro por período** nos relatórios (hoje somam *tudo* desde sempre) e
  fechamento de comissão por período, com marcação de "pago".
- **Caixa**: abertura/fechamento, despesas, sangrias, taxas de cartão.
- Venda de **produtos** e controle de estoque; **pacotes/planos de
  assinatura** do cliente da barbearia (ex.: "clube do corte").
- Busca e paginação nas listas; histórico por cliente.
- Interface responsiva para celular (ou PWA).
- Exportação para PDF/Excel.

## 🟡 Operação e infraestrutura

- Servidor WSGI de produção (Gunicorn) atrás de Nginx, ou PaaS
  (Render, Railway, Fly.io); `Dockerfile` e `docker-compose`.
- Configuração por variáveis de ambiente (12-factor) e arquivo `.env.example`.
- CI (GitHub Actions) rodando os testes a cada push.
- Logs estruturados e monitoramento de erros (Sentry), uptime check.
- Onboarding: cadastro da barbearia → assistente inicial para criar
  serviços e barbeiros → importação de clientes por planilha.
- Painel administrativo seu (dono do SaaS): lista de assinantes, status de
  pagamento, métricas (MRR, churn).
- Domínio, landing page com preços, canal de suporte.

## Sugestão de ordem de execução

1. Migrações + PostgreSQL + `barbearia_id` em todas as tabelas.
2. Login, papéis, validação de entrada.
3. CRUD completo de barbeiros/serviços/clientes e filtros de período.
4. Agenda e agendamento online (principal argumento de venda).
5. Deploy (Docker + Gunicorn + HTTPS), backups, Sentry, CI.
6. Cobrança recorrente, LGPD/termos e lançamento com algumas barbearias
   piloto antes de abrir ao público.
