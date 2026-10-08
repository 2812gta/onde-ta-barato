# API

- Prefixo: `/api/v1/`, organizada por domínio.
- Documentação gerada automaticamente (OpenAPI): `/api/schema/`, Swagger em `/api/docs/`, Redoc em `/api/redoc/`.
- Autenticação: JWT Bearer (access 15 min; refresh 14 dias com rotação e blacklist).
- Versionamento: mudanças incompatíveis exigem nova versão. O app consulta uma versão mínima suportada (a implementar) e há período de depreciação anunciado no CHANGELOG.
- Toda resposta com preço (a partir do M2) inclui: valor, fonte, data de coleta, condição de pagamento, status e confiança.
- Erros: JSON com `detail` (ou campos de validação). Mensagens de autenticação são deliberadamente genéricas (sem enumeração de usuários).

## Implementado (M1)

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/health/` | público | Liveness + banco (fora do `/api/v1`) |
| POST | `/auth/register/` | público, 10/h | Cadastro. Resposta idêntica se o e-mail já existir |
| POST | `/auth/login/` | público, 10/min | Retorna `access` e `refresh`. Bloqueio após 5 falhas por e-mail (15 min) |
| POST | `/auth/refresh/` | público | Rotaciona o refresh; o anterior é invalidado |
| POST | `/auth/logout/` | autenticado | Revoga o refresh |
| POST | `/auth/verify-email/` | público | Confirma e-mail com o código recebido |
| POST | `/auth/resend-verification/` | autenticado | Reenvia confirmação |
| POST | `/auth/password-reset/` | público, 5/h | Sempre 202 (não revela se o e-mail existe) |
| POST | `/auth/password-reset/confirm/` | público | Redefine senha; revoga sessões |
| GET/PATCH | `/me/` | autenticado | Perfil. `role` e `email` não são editáveis |
| DELETE | `/me/` | autenticado | Exclusão (anonimização) com confirmação de senha |
| GET/POST | `/me/consents/` | autenticado | Consentimentos (histórico append-only) |
| GET | `/me/export/` | autenticado | Exportação dos dados do titular (LGPD) |
| PATCH | `/users/{id}/role/` | `users.change_role` (SUPERADMIN) | Altera papel; auditado |
| GET | `/audit/logs/` | `audit.view` (ADMIN, SUPERADMIN) | Leitura da auditoria; não expõe IP |

## Matriz RBAC (M1)

| Papel | users.view | users.manage | users.change_role | audit.view |
|---|:-:|:-:|:-:|:-:|
| CUSTOMER / MERCHANT_* | | | | |
| MODERATOR, SUPPORT | ✔ | | | |
| ADMIN | ✔ | ✔ | | ✔ |
| SUPERADMIN | ✔ | ✔ | ✔ | ✔ |

Permissões novas são adicionadas pelo marco que as introduz; o teste da matriz falha de propósito se ela mudar sem atualização consciente.
