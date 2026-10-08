# ADR 0002: PostgreSQL/PostGIS no desenvolvimento local

Status: **Aceita** (substitui a proposta de container na 5433)

Decisão: usar o PostgreSQL 17.4 nativo já instalado (porta 5432), adicionando a extensão PostGIS. Criar um banco e um usuário dedicados do projeto (`ondetabarato`), sem usar o superusuário `postgres` na aplicação. Testes usam um banco de teste separado.

Pendência: instalar PostGIS (Stack Builder → Spatial Extensions), que exige administrador. Produção na VPS usa a imagem `postgis/postgis`.

Backup: `pg_dump` via script; restauração testada antes de qualquer deploy.
