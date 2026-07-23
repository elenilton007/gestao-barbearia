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
| `tests/` | Testes automatizados dos relatórios e regras de negócio |

## 📊 Funcionalidades

- **Dashboard gerencial**: faturamento do mês, ticket médio, top serviços, top clientes, comissões
- **Cadastro de clientes**
- **Registro de atendimentos**: vincula cliente, barbeiro, serviço e forma de pagamento
- **Relatórios**: faturamento mensal histórico, ranking de serviços e clientes
- **Cálculo automático de comissão** por barbeiro, baseado em percentual individual

## ▶️ Como executar

Instalar dependências: `pip install -r requirements.txt`

Inicializar o banco de dados com dados de exemplo: `python database.py`

Rodar a aplicação: `python app.py`

Acesse **http://127.0.0.1:5000** no navegador.

Para rodar os testes: `pytest tests/ -v`

## 🔧 Tecnologias

- Python 3
- Flask
- SQLite (SQL puro, sem ORM — para deixar as queries explícitas)
- Jinja2 (templates HTML)
- Pytest (testes automatizados)

## 🚀 Próximos passos

- Autenticação de usuários (administrador x barbeiro)
- Exportação de relatórios em PDF/Excel
- Gráficos interativos no dashboard
- Análise preditiva de faturamento com IA

## 👤 Autor

**Elenilton Santos da Silveira**
Técnico em Desenvolvimento de Sistemas | Técnico em Automação Industrial
[LinkedIn](https://www.linkedin.com/in/elenilton-santos-da-silveira-450952285)
