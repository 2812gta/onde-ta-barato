# OndeTáBarato

Assistente inteligente de compras: ajuda o consumidor a descobrir **onde vale mais a pena comprar**, considerando preço por unidade, promoções, distância, confiança e atualização das informações.

> Princípio central: **a confiança do consumidor é inegociável.** Pagamento comercial nunca altera ranking orgânico, menor preço ou custo-benefício. Veja [docs/USER_TRUST.md](docs/USER_TRUST.md).

## Status

**M0 — Fundação** (em validação). Nenhum código de aplicação existe ainda. Veja [docs/ROADMAP.md](docs/ROADMAP.md).

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Django, DRF, PostgreSQL + PostGIS, Redis, Celery |
| Mobile | Flutter/Dart (Android no MVP; arquitetura preparada para iOS) |
| Infra | Docker (dev e prod), Nginx em produção, GitHub Actions |

Arquitetura: **monólito modular** (sem microserviços). Detalhes em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Ambiente

Desenvolvimento em Windows; produção em Linux. O backend roda em containers Linux para garantir paridade. Resultado da auditoria e pendências: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Documentação

- [Arquitetura](docs/ARCHITECTURE.md) · [Roadmap](docs/ROADMAP.md) · [Modelo de dados](docs/DATA_MODEL.md) · [API](docs/API.md)
- [Integridade dos dados](docs/DATA_INTEGRITY.md) · [Confiança do usuário](docs/USER_TRUST.md) · [Governança de IA](docs/AI_GOVERNANCE.md)
- [Segurança](docs/SECURITY.md) · [LGPD](docs/LGPD.md) · [Privacidade](docs/PRIVACY.md) · [Termos](docs/TERMS.md) · [Política de contribuição](docs/CONTRIBUTION_POLICY.md)
- [Decisões de arquitetura (ADR)](docs/adr/)

## Convenções

Código, commits e comentários técnicos em **inglês**; documentação de produto em **pt-BR**. Fluxo Git: `main` (estável) ← `develop` ← `feature/*`, `fix/*`, `hotfix/*`.
