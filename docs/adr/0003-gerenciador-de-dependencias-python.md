# ADR 0003: Gerenciador de dependências Python

Status: **Aguardando decisão**

Python 3.12 (3.14 descartado por compatibilidade). Opções: **uv** (rápido, lockfile, `pyproject.toml`; recomendado) ou pip + `requirements/*.txt` (sem instalação extra). Como o backend roda em container, a escolha afeta principalmente o Dockerfile e o fluxo de CI.
