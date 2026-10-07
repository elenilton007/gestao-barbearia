-- dados_exemplo.sql
-- Dados de exemplo para demonstração: a Barbearia Exemplo com dois
-- barbeiros, cinco serviços e três clientes. Usado só por
-- `python database.py` (que recria o banco do zero); o banco de produção
-- (`python database.py --preparar`) começa vazio.

INSERT INTO barbearias (nome) VALUES ('Barbearia Exemplo');

INSERT INTO barbeiros (barbearia_id, nome, comissao_percentual) VALUES
    (1, 'Elenilton Silveira', 50.0),
    (1, 'João Pereira', 40.0);

INSERT INTO servicos (barbearia_id, nome, preco, duracao_minutos) VALUES
    (1, 'Corte Masculino', 35.00, 30),
    (1, 'Barba', 25.00, 20),
    (1, 'Corte + Barba', 55.00, 50),
    (1, 'Sobrancelha', 15.00, 10),
    (1, 'Coloração', 60.00, 60);

INSERT INTO clientes (barbearia_id, nome, telefone) VALUES
    (1, 'Carlos Souza', '(71) 90000-0001'),
    (1, 'Rafael Lima', '(71) 90000-0002'),
    (1, 'Bruno Andrade', '(71) 90000-0003');
