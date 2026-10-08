# ADR 0003: Gerenciador de dependências Python

Status: **Aceita**

Python 3.12 com `venv` e **pip** + `requirements/{base,dev,prod}.txt` com versões fixadas. Sem `uv` por ora (nada extra a instalar). Reavaliar quando houver lockfile hash-pinned no CI.

Python 3.14 descartado (compatibilidade de dependências).
