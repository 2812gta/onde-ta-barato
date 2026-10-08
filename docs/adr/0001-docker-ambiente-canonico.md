# ADR 0001: Docker como ambiente canônico do backend

Status: **Proposta (depende de instalar WSL2 + Docker Desktop)**

Contexto: desenvolvimento em Windows, produção em Linux; GeoDjango exige GDAL/GEOS, frágeis no Windows.

Decisão: backend, PostGIS, Redis e Celery rodam em containers Linux; testes rodam dentro do container; CI em `ubuntu-latest`. Flutter roda nativo no Windows.

Consequências: paridade com produção; requer Docker/WSL2 e espaço em disco.

Alternativas descartadas: PostgreSQL nativo + OSGeo4W (frágil, sem paridade).
