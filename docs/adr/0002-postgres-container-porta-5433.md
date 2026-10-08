# ADR 0002: PostgreSQL/PostGIS em container, porta 5433

Status: **Proposta**

Contexto: existe PostgreSQL 17.4 nativo (porta 5432) sem PostGIS.

Decisão: usar imagem `postgis/postgis` em container, exposta no host em **5433**. O PostgreSQL nativo permanece intocado.

Consequências: banco reproduzível, backup/restauração padronizados via scripts. Dados do projeto não ficam no PostgreSQL nativo.
