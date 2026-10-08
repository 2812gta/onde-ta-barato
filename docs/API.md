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

## Matriz RBAC (M1 + M2)

| Papel | users.view | users.manage | users.change_role | audit.view | catalog.write | merchants.review | merchants.suspend |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| CUSTOMER | | | | | | | |
| MERCHANT_OWNER / MANAGER / OPERATOR | | | | | ✔ | | |
| SUPPORT | ✔ | | | | | | |
| MODERATOR | ✔ | | | | ✔ | ✔ | |
| ADMIN | ✔ | ✔ | | ✔ | ✔ | ✔ | ✔ |
| SUPERADMIN | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

Regras **por objeto** (publicar preço, editar loja, gerir equipe) não estão nesta matriz: dependem do vínculo `MerchantMembership` com aquele comerciante (proprietário, gerente, operador). Permissões novas são adicionadas pelo marco que as introduz; o teste da matriz falha de propósito se ela mudar sem atualização consciente.

## Implementado (M2)

Todos exigem autenticação. **A localização vai no corpo de `POST`, nunca na URL**, para não cair em logs de acesso (ADR 0009); a localização do consumidor não é armazenada.

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET/POST | `/merchants/` | autenticado | Lista os meus comerciantes / cria (CNPJ validado; quem cria vira proprietário) |
| GET | `/merchants/{id}/` | membro ou revisor | Detalhe, com `is_verified` |
| GET/POST | `/merchants/{id}/verification/` | membro ou revisor | Histórico / transição de estado (`{"to": "...", "notes": ""}`) |
| GET | `/merchants/review-queue/` | `merchants.review` | Fila `UNDER_REVIEW` |
| GET/POST | `/merchants/{id}/members/` | membro / proprietário | Equipe (gerente, operador) |
| DELETE | `/merchants/{id}/members/{user_id}/` | proprietário | Remove membro |
| POST | `/merchants/{id}/stores/` | proprietário ou gerente | Cadastra loja (`lat`, `lon`, ...) |
| GET/PATCH | `/stores/{id}/` | autenticado / proprietário ou gerente | Detalhe / edição (CNPJ imutável) |
| POST | `/stores/search/` | autenticado, 120/min | Lojas por raio `{lat, lon, radius_km<=50}`, mais próxima primeiro, com `distance_m` |
| GET | `/categories/` | autenticado | Categorias e TTL de preço |
| GET | `/variants/?q=&gtin=&category=` | autenticado | Busca (sem acento, ordem livre; GTIN aceita EAN-13 ou GTIN-14) |
| GET | `/variants/{id}/` | autenticado | Detalhe |
| POST | `/catalog/variants/` | `catalog.write` | Cria ou devolve a variante existente (`created`) |
| POST | `/variants/{id}/prices/search/` | autenticado, 120/min | Preços do produto nas lojas do raio, por distância, **sem** ranking |
| GET | `/variants/{id}/price-history/?store=&payment_condition=` | autenticado | Histórico com `previous_price`; quem informou aparece só como papel |
| POST | `/stores/{id}/prices/` | equipe da loja, 60/h | Publica preço do estabelecimento (`source=MERCHANT`) |
| POST | `/stores/{id}/prices/report/` | consumidor, 60/h | Reporta preço visto (`source=USER`); `lat`/`lon` opcionais só validam proximidade |
| POST | `/prices/{id}/confirmations/` | consumidor independente | `{"agrees": true}` ou `false` |

Cada preço devolvido traz: valor, moeda, condição de pagamento, `source`, `collected_at`, `age_hours`, `status` (`CURRENT`, `STALE`, `EXPIRED` ou `CONFLICTING`), `verification`, `confidence_score/level/factors`, confirmações, `unit_price` (ex.: `R$ 4,98/kg`) e o aviso "Pode haver diferença no caixa.".

Erros de regra de negócio retornam 400; falta de permissão, 403. O OpenAPI (`/api/schema/`) documenta os 31 endpoints sem avisos.

## Implementado (M3)

Buscas por proximidade continuam em `POST` (localização fora da URL). Ver [PROMOTIONS.md](PROMOTIONS.md) e [RECOMMENDATIONS.md](RECOMMENDATIONS.md).

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET/POST | `/stores/{id}/promotions/` | autenticado / equipe da loja | Lista promoções ativas / cria (regra validada; `confirmed` indica se o comerciante é verificado) |
| DELETE | `/promotions/{id}/` | equipe da loja | Desativa (não apaga) |
| POST | `/promotions/calculate/` | autenticado | Calculadora sem estado: `{unit_price, quantity, rule, payment_condition, has_loyalty, coupon_codes}` |
| POST | `/recommendations/basket/` | autenticado, 120/min | Onde comprar a lista: `{items, lat, lon, radius_km, mode, payment_condition, has_loyalty, coupon_codes, cost_per_km?, max_stores}` |
| POST | `/variants/{id}/compare/` | autenticado, 120/min | Um produto em várias lojas, por preço por unidade |

**Resposta da recomendação:** `verdict` (`RECOMMENDED`, `TIE` ou `INSUFFICIENT_DATA`), `message`, `best` (plano com lojas, linhas, totais, `route_km`, `score_breakdown`), `alternatives`, `reasons` (cada uma com `code` e texto gerado dos números), `warnings`, `assumptions` (R$/km, fator de desvio, tratamento de conflito e de promoções) e `searched`. Quando faltam dados, `best` vem nulo e não há `reasons`.

**Resposta da comparação:** `label` ("Menor preço encontrado na nossa base" só quando verdadeiro), `notes`, `analysis` (data, lojas no raio, lojas com preço, cobertura, condições) e `results` ordenados por preço por unidade, com `rank`, `price_range` quando há conflito, `freshness`, `confidence` e se o comerciante é verificado (informativo; não reordena).

Modos: `ECONOMIZAR_MAIS`, `MAIS_PROXIMO`, `MELHOR_CUSTO_BENEFICIO` (padrão), `MENOS_DESLOCAMENTO`, `MELHORES_PROMOCOES`.

O OpenAPI (`/api/schema/`) documenta os 36 endpoints sem avisos.
