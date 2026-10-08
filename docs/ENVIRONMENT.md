# Auditoria do Ambiente (M0)

Data: 2026-10-07. Máquina de desenvolvimento do projeto. Nada foi instalado durante a auditoria.

## Resultado

| Item | Situação | Detalhe |
|---|---|---|
| Sistema operacional | OK | Windows 10 Pro 22H2 (10.0.19045), x64 |
| Recursos | ATENÇÃO | 15,4 GB RAM; **12,9 GB livres em C:** (apertado, veja riscos) |
| Python | OK | 3.12.10 (padrão). `py` também expõe 3.14.3, **não usar** (dependências ainda sem suporte) |
| pip | OK | 25.0.1 |
| uv / Poetry | AUSENTE | Opcional. Ver ADR 0003 |
| Git | OK | 2.52.0; `user.name` e `user.email` configurados globalmente |
| Docker / Compose | **AUSENTE** | Obrigatório para o ambiente canônico (ADR 0001) |
| WSL2 | **AUSENTE** | Só o stub do `wsl.exe`; sem distribuição e sem recursos habilitados. Pré-requisito do Docker Desktop |
| Hipervisor | OK | Presente (`HypervisorPresent = True`) |
| PostgreSQL nativo | PRESENTE | 17.4, serviço `postgresql-x64-17` rodando (porta 5432). `psql` fora do PATH |
| PostGIS | **AUSENTE** | Não instalado no PostgreSQL 17 nativo |
| GDAL/GEOS (GeoDjango) | AUSENTE no host | Resolvido dentro do container |
| Flutter / Dart | ATENÇÃO | Flutter 3.29.1 / Dart 3.7.0 (fev/2025, defasado). Funciona; atualizar só no M4 |
| Android SDK | ATENÇÃO | Presente (platforms 30–36.1, emulator, cmdline-tools); **licenças não aceitas** |
| Android Studio | OK | 2026.1.1; JBR embutido disponível |
| Java | ATENÇÃO | JDK do sistema é 1.8 (obsoleto). `JAVA_HOME` vazio. Flutter usa o JBR do Android Studio |
| Node.js | OK | 22.20.0 (não obrigatório) |
| Xcode / macOS (iOS) | AUSENTE | Windows não compila iOS. Ver ADR 0005 |
| Diretório do projeto | OK | Estava vazio e fora de repositório Git |

## Riscos

1. **Disco (12,9 GB livres).** Docker Desktop + disco virtual do WSL2 + imagens (Postgres/PostGIS, Redis, Python) + emulador Android podem ultrapassar isso. Liberar espaço ou mover o disco do WSL2 para outra unidade.
2. **Docker/WSL2 ausentes.** Sem eles não há ambiente reproduzível nem paridade com produção Linux. A instalação exige administrador e provavelmente reinício.
3. **PostgreSQL nativo ocupa a 5432.** O container de desenvolvimento usará **5433** para não conflitar.
4. **Fim de linha / caixa de nomes.** Windows (CRLF, case-insensitive) vs Linux (LF, case-sensitive). Mitigado com `.gitattributes` e `.editorconfig`; nomes de arquivo sempre em minúsculas.
5. **Flutter defasado.** Pacotes novos podem exigir SDK mais recente. Decidir a atualização no início do M4.
6. **iOS sem Mac.** Build/assinatura iOS só via macOS (CI em nuvem ou Mac físico).

## Pendências que dependem de autorização

- Instalar WSL2 + Docker Desktop (administrador, reinício, ~vários GB).
- Aceitar licenças do Android SDK (`flutter doctor --android-licenses`), ação interativa que aceita termos em seu nome.
- Instalar `uv` (opcional).
