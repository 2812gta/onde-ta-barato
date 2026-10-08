# ADR 0001: Desenvolvimento nativo no Windows, Docker na VPS

Status: **Aceita** (substitui a proposta anterior de Docker local)

Contexto: desenvolvimento em Windows; produção em VPS Linux com Docker. Docker/WSL2 não serão instalados na máquina de desenvolvimento.

Decisão:
- Local: Python (venv) + PostgreSQL 17 nativo com PostGIS + GDAL/GEOS para GeoDjango; Redis opcional até o M5 (cache/Celery podem usar backends locais em dev/testes).
- VPS: Docker Compose (backend, postgres/postgis, redis, celery, nginx).
- Os `Dockerfile` e `docker-compose` são escritos no M1, mas só são validados na VPS (ou no CI).

Riscos e mitigação (perda de paridade com Linux):
- CI em `ubuntu-latest` com serviço PostGIS roda toda a suíte de testes em Linux a cada push. É a rede de proteção contra "funciona no Windows".
- `.gitattributes` (LF), nomes de arquivo em minúsculas, `pathlib`, sem caminhos fixos.
- Até existir o CI/VPS, o Dockerfile fica marcado como **não validado**.
