# Desenvolvimento local (Windows)

Pré-requisitos: Python 3.12, PostgreSQL 17 rodando, Git.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements\dev.txt
```

## Banco

Crie um papel e um banco dedicados (com o superusuário, uma vez):

```sql
CREATE ROLE ondetabarato LOGIN CREATEDB PASSWORD '<senha-forte>';
CREATE DATABASE ondetabarato OWNER ondetabarato ENCODING 'UTF8';
```

Instale PostGIS (Stack Builder/EDB) e crie um template para os testes, com o superusuário (uma vez):

```sql
CREATE DATABASE template_postgis TEMPLATE template0 ENCODING 'UTF8';
UPDATE pg_database SET datistemplate = true WHERE datname = 'template_postgis';
\c template_postgis
CREATE EXTENSION postgis;
\c ondetabarato
CREATE EXTENSION postgis;
```

Copie `.env.example` para `.env` na raiz do repositório e preencha `SECRET_KEY`, `JWT_SECRET` e `DATABASE_URL`, e defina `DB_TEST_TEMPLATE=template_postgis`. O `.env` é ignorado pelo Git e **nunca** é carregado com `config.settings.production`.

## Comandos

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe -m pytest --create-db      # testes
.\.venv\Scripts\python.exe -m ruff check .            # lint
.\.venv\Scripts\python.exe -m black --check .         # formato
.\.venv\Scripts\python.exe -m mypy apps config        # tipos
```

## Dados de demonstração

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo              # senha aleatória, exibida uma vez
.\.venv\Scripts\python.exe manage.py seed_demo --password "<senha>"
```

Cria dados **fictícios** em Fortaleza para desenvolver e demonstrar o app: 3 comerciantes (2 verificados e 1 pendente), 6 lojas, 16 apresentações de produto (inclui dois tamanhos de café e de arroz para o preço por unidade), 64 preços, 5 promoções de tipos diferentes e 7 usuários (`*@demo.ondetabarato.invalid`, domínio reservado que nunca recebe e-mail).

O conjunto cobre os cenários do M3: preço desatualizado (hortifruti de 10 dias na loja de Messejana), preço contestado (arroz de 5 kg a R$ 20,90 informado por usuário, contestado por dois), preço promocional com validade e um comerciante não verificado cujos dados pesam menos.

- Usa os mesmos serviços da API (verificação de comerciante, registro de preço, promoções, confirmações), então respeita as regras e gera auditoria.
- É repetível: uma segunda execução não cria nada. O histórico de preços é append-only, então não há "reset"; para recomeçar, recrie o banco de desenvolvimento.
- Recusa rodar com `config.settings.production`. Tudo é identificado com o prefixo `[DEMO]`, sem CNPJ e sem GTIN; as coordenadas são aproximadas.

Swagger: http://localhost:8000/api/docs/ · Health: http://localhost:8000/health/

## Paridade com Linux

A máquina local é Windows; produção é Linux. A suíte roda em Ubuntu a cada push pelo GitHub Actions (`.github/workflows/backend-ci.yml`), que é a rede de proteção contra diferenças de plataforma. Mantenha nomes de arquivo em minúsculas e use `pathlib`.
