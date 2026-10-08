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

1. **Disco (12,9 GB livres).** Emulador Android, builds Flutter e PostGIS/GDAL podem ultrapassar isso. Acompanhar.
2. **Docker/WSL2 ausentes (decisão: só na VPS).** Sem paridade local com Linux; mitigado pelo CI em Ubuntu. Dockerfile e compose não são executáveis aqui.
3. **PostGIS local resolvido**, mas a versão do PROJ no bundle (8.2) é mais antiga que a de produção (Debian). Diferenças de transformação entre sistemas de coordenadas são possíveis; distâncias em `geography` (SRID 4326) não são afetadas.
4. **Fim de linha / caixa de nomes.** Windows (CRLF, case-insensitive) vs Linux (LF, case-sensitive). Mitigado com `.gitattributes` e `.editorconfig`; nomes de arquivo sempre em minúsculas.
5. **Flutter defasado.** Pacotes novos podem exigir SDK mais recente. Decidir a atualização no início do M4.
6. **iOS sem Mac.** Build/assinatura iOS só via macOS (CI em nuvem ou Mac físico).

## Atualização (M1)

- Decisão: **Docker só na VPS**; desenvolvimento nativo no Windows (ADR 0001/0002).
- Criados no PostgreSQL 17 local: papel `ondetabarato` (LOGIN, CREATEDB) e banco `ondetabarato`. A senha do superusuário `postgres` não é usada pela aplicação e não está em nenhum arquivo.
- **PostGIS 3.6.2 instalado** (GEOS 3.14, PROJ 8.2.1, GDAL 3.9.2 do bundle). Extensão criada em `ondetabarato` e no template `template_postgis` (usado pelo banco de testes; `template1` não foi alterado).
- GeoDjango no Windows reaproveita as DLLs do bundle (`config/gis.py`). O GDAL do bundle não lê variáveis de ambiente definidas após o início do processo, por isso o caminho do PROJ é passado via `OSRSetPROJSearchPaths`.
- O bundle não inclui `gdal-data`; irrelevante para pontos/distâncias/transformações EPSG, mas formatos de arquivo raster/vetor avançados podem exigir instalação completa do GDAL (OSGeo4W).
- venv do backend em `backend/.venv` (Python 3.12.10, ignorado pelo Git).

## Pendências que dependem de autorização

- Aceitar licenças do Android SDK (`flutter doctor --android-licenses`), ação interativa que aceita termos em seu nome.
- Instalar `uv` (opcional).
