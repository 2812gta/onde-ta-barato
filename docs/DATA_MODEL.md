# Modelo de Dados (estado do M2)

Reflete o que está implementado e testado. Decisões que **mudaram** em relação ao rascunho do M0 estão marcadas com ⚠.

## Convenções

- Chaves primárias **UUID** (não enumeráveis) em todas as entidades de domínio.
- **Dinheiro:** `NUMERIC(12,2)` / `Decimal`, moeda `BRL`. `float` é rejeitado. Arredondamento `ROUND_HALF_UP` ao centavo (`apps/core/money.py`).
- **Soft delete** (`deleted_at`) em Merchant, Store, Product e ProductVariant. Unicidades consideram só registros vivos.
- **Somente-anexar** (`AppendOnlyModel`): `AuditLog`, `MerchantVerification`, `PriceObservation`, `PriceEvidence`, `PriceConfirmation`. Update/delete levantam erro no modelo e no queryset.
- **Relógio estritamente crescente** (`apps/core/clock.py`) nas tabelas de histórico, para que a ordem de escrita seja sempre a ordem de leitura (ver ADR 0008).

## Entidades

```text
User ─┬─ Consent (histórico)                       AuditLog (somente-anexar)
      └─ MerchantMembership ─ Merchant ─ MerchantVerification (somente-anexar)
                               │
                               └─ Store (location: geography Point, GiST)

Category (price_ttl_hours) ─ Product ─ ProductVariant (gtin?, quantity, unit, base_*, identity_key)
Brand ─────────────────────────┘                │
                                                └─ PriceObservation ─┬─ PriceEvidence
                                                      (Store)        └─ PriceConfirmation
```

### Merchant / verificação

Estados: `PENDING → UNDER_REVIEW → VERIFIED | REJECTED`; `VERIFIED ⇄ SUSPENDED`; `REJECTED → PENDING`. Quem pode: o proprietário submete e reenvia; `merchants.review` (MODERATOR+) aprova/rejeita; `merchants.suspend` (ADMIN+) suspende/reintegra. Rejeição e suspensão exigem justificativa. Cada passo vira uma linha em `MerchantVerification`. **Não há consulta automática à Receita Federal**: a verificação é manual.

O selo (`is_verified`) existe **somente** em `VERIFIED`; nenhum campo de plano ou pagamento interfere (garantido por teste de arquitetura).

`MerchantMembership` liga usuários ao comerciante com papel `MERCHANT_OWNER | MERCHANT_MANAGER | MERCHANT_OPERATOR`. Regras por objeto (publicar preço, editar loja) usam o vínculo; o papel global é promovido de `CUSTOMER` apenas na criação do vínculo e nunca rebaixa equipe interna.

### Store

`location = PointField(geography=True, srid=4326)` com índice GiST: distâncias em metros e raio via `ST_DWithin`. `merchant` é nulo para lojas semeadas de dados abertos e ainda não reivindicadas; nesse caso ninguém as edita. `source`: `MERCHANT | OPENSTREETMAP | USER`. Unicidade `(source, external_id)`.

### Produto

- `Product`: conceito. `ProductVariant`: apresentação comprável; **preços sempre apontam para a variante**.
- ⚠ **GTIN fica na variante**, não no produto: cada embalagem tem o seu código. Armazenado com 14 dígitos (EAN-13 e GTIN-14 do mesmo item são idênticos), dígito verificador validado.
- `quantity`/`unit` informados; `base_quantity`/`base_unit` derivados (`kg→g`, `l→ml`) para comparar preço por unidade. Multipacks (`12x350ml`) usam o volume total.
- `identity_key` = hash de (nome normalizado, marca, rótulo, quantidade base, unidade base). Evita duplicatas por grafia; um GTIN descoberto depois é **anexado** à variante existente. Se o produto for renomeado depois, a chave não é recalculada automaticamente.
- `Category.price_ttl_hours`: por quanto tempo um preço da categoria é "atual" (12 categorias semeadas, de 48 h em hortifruti a 336 h em limpeza).

### PriceObservation

```text
id, product_variant, store
price NUMERIC(12,2) > 0, currency
payment_condition (NORMAL|PIX|DEBIT|CREDIT|LOYALTY|COUPON), is_promotional
source (MERCHANT|USER|FLYER|PUBLIC_SOURCE|HISTORICAL|CALCULATED)
collected_at, valid_from, valid_until (> collected_at)
confidence_score, confidence_level      # instantâneo na criação; a leitura recalcula
created_by (SET NULL), created_at
supersedes -> PriceObservation          # valor anterior (mesma variante, loja, condição e fonte)
location_verified                        # o aparelho estava perto da loja; coordenadas NÃO são guardadas
```

- ⚠ **`pack_quantity`/`pack_unit` saíram** da observação: a embalagem vive na variante, evitando dois lugares para a mesma informação divergirem.
- ⚠ **`status` não é coluna**: `CURRENT/STALE/EXPIRED` dependem da idade no momento da leitura, e `CONFLICTING` depende das outras observações. São calculados na leitura (`selectors.py`). `VERIFIED/UNVERIFIED` também são derivados.
- **Deduplicação:** o mesmo preço (mesma condição, fonte, promoção e validade) reportado dentro de `PRICE_DEDUP_HOURS` (6 h) não cria nova linha.
- Fontes `HISTORICAL`, `CALCULATED`, `FLYER` e `PUBLIC_SOURCE` existem no enum e na fórmula de confiança, mas ainda não têm fluxo de entrada (encartes: fase 2).

### Promotion (M3)

`store`, `product_variant`, `title`, `rule` (JSON validado por `promotions/engine.py`), `valid_from`, `valid_until` (> início), `is_active`, `created_by`. Desativar não apaga: o registro do que foi oferecido permanece. É dado de preço do comerciante, não anúncio: não há posição, orçamento nem destaque. Ver [PROMOTIONS.md](PROMOTIONS.md).

### Evidência

`PriceEvidence`: foto/encarte (arquivo privado, sem URL pública) ou link `http(s)`. Imagens são validadas e **reencodadas em JPEG sem metadados** (remove EXIF/GPS e conteúdo anexado), limite de 8 MB e 40 MP, SHA-256 do arquivo final. Ainda **não há endpoint de upload**: o serviço existe e é testado; o endpoint entra com a câmera (M5).

## Retenção

Políticas formais (prazos de logs, evidências, contas) seguem pendentes e estão listadas em [LGPD.md](LGPD.md). Nenhum histórico comercial é apagado hoje: o sistema simplesmente não oferece essa operação.

## Mapa de modelos por marco

Ver [ARCHITECTURE.md](ARCHITECTURE.md).
