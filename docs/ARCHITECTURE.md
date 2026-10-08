# Arquitetura

## Visão geral

**Monólito modular** Django + app Flutter. Sem microserviços. Se um módulo (OCR, IA, recomendação, imagens) precisar virar serviço, isso exige ADR com justificativa medida.

```text
Flutter (Android; iOS preparado)
        │ HTTPS /api/v1  (JWT)
        ▼
 Nginx (prod) ─► Django + DRF ──► PostgreSQL + PostGIS
                    │
                    ├──► Redis ─► Celery (OCR/IA/expiração de preços/notificações)
                    └──► Storage de imagens (local no dev; S3/MinIO/R2 em prod)
```

Ambientes: desenvolvimento nativo em Windows; produção em Docker na VPS Linux. O CI executa a suíte em Ubuntu para cobrir diferenças de plataforma (ADR 0001).

## Princípios arquiteturais

1. **Confiança acima de receita.** O módulo de recomendação é puro: recebe um DTO com campos explicitamente permitidos e **não importa** `subscriptions`, anúncios ou campanhas. Um teste de arquitetura impede essas importações (obrigatório desde o M3).
2. **Histórico imutável.** Preço é observação append-only (`PriceObservation`); nunca há UPDATE silencioso de valor.
3. **Origem sempre visível.** Todo dado comercial carrega fonte, data, condição e confiança.
4. **IA não é fonte da verdade.** Interpreta e explica; nunca cria preço, promoção, loja ou evidência.
5. **Dinheiro em `Decimal`/`NUMERIC`.** Nunca `float`.
6. **Geografia no banco.** Consultas por raio com PostGIS (`geography`, SRID 4326, índice GiST).
7. **Módulos com baixo acoplamento.** Comunicação por serviços/interfaces do domínio, não por acesso direto a models de outro app.

## Estrutura de módulos (backend)

Apps são criados **somente no marco em que são usados**:

| Marco | Apps | Modelos |
|---|---|---|
| M1 | `core`, `users`, `audit` (`locations` entra no M2 com o PostGIS) | User, Consent, papéis (RBAC), AuditLog; base models, soft delete, utilitários de dinheiro |
| M2 | `merchants`, `stores`, `products`, `prices` | Merchant, MerchantVerification, Store, Brand, Category, Product, ProductVariant, PriceObservation, PriceEvidence; comandos de seed (lojas via OSM, produtos via Open Food Facts) |
| M3 | `promotions`, `offers`, `recommendations` | Promotion, Offer; motor de promoções; preço por unidade; consenso/confiança; score de custo-benefício |
| M4 | `shopping_lists`, `shopping_cart` | ShoppingList(Item), ShoppingCart(Item) |
| M5 | `ocr`, `ai`, `fraud` | UserContribution (em `prices`), FraudSignal, AIProcessingJob; AIProvider, OCRProvider |
| M6 | portal do comerciante, moderação | verificação, publicação de preços/ofertas, fila de moderação |
| M7 | `analytics` | histórico, economia, otimização de lista |
| M8 | `voice`, `notifications`, `reviews`, `subscriptions` | VoiceProvider, FCM/APNs, reputação, planos |

Esta tabela substitui a árvore completa do prompt original e está sujeita à sua aprovação.

## Organização interna de um app

```text
apps/<app>/
  models.py        # entidades e invariantes
  services.py      # casos de uso (escrita, regras)
  selectors.py     # consultas (leitura)
  api/             # serializers, views, urls (DRF)
```

Testes ficam em `backend/tests/<app>/`, espelhando os apps.

Views finas; regras de negócio em `services`/`selectors`.

## Fronteira do módulo de recomendação

```text
selectors (preços, lojas, distância)  ──►  RecommendationInput (DTO, whitelist)
                                                │
                                                ▼
                              recommendations.engine  ──► resultado + explicação
```

Campos proibidos no DTO: qualquer coisa de assinatura, orçamento publicitário, patrocínio ou `commercial_score`. Teste de arquitetura verifica imports e campos.

## Mobile (Flutter)

Clean Architecture + feature-first:

```text
mobile/lib/
  core/            # tema/design system, rede (Dio), erros, config
  features/
    auth/ home/ stores/ products/ prices/
    shopping_lists/ shopping_cart/ camera/ profile/
  main.dart
```

- Estado: Riverpod. Navegação: GoRouter. HTTP: Dio. Modelos: Freezed + json_serializable (somente se justificados).
- **iOS:** código 100% Dart/Flutter sem dependências exclusivas de Android; plugins avaliados quanto ao suporte iOS (câmera, localização, ML Kit, voz, FCM). Build iOS depende de macOS (ADR 0005); no MVP o alvo entregue é Android.
- Offline completo fica fora do MVP; conflitos de preço nunca por `last-write-wins`.

## Contrato OCR/IA

- `OCRProvider` (backend) e OCR local no app (ML Kit, preferência inicial). Se o OCR rodar no aparelho, o app envia **texto, bounding boxes, confiança e idioma**; o backend normaliza e valida.
- `AIProvider` desacopla fornecedores (OpenAI, Ollama, etc.).
- Toda extração marca cada campo como **FATO** (lido na imagem) ou **INFERÊNCIA** (interpretado). Ver [AI_GOVERNANCE.md](AI_GOVERNANCE.md).

## Observabilidade e operação

Logs estruturados, health check, backup de PostgreSQL com restauração testada antes de qualquer deploy. Sentry/Prometheus ficam para depois.
