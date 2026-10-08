# Modelo de Dados (rascunho de M0)

Detalhamento final em cada marco. Aqui ficam as decisões já fechadas.

## Dinheiro

`NUMERIC(12,2)` no PostgreSQL, `Decimal` no Python, moeda `BRL`. Política de arredondamento: `ROUND_HALF_UP` ao centavo, aplicada **uma vez no total da linha**, nunca por unidade. Testada em todas as regras de promoção.

## Fonte do preço (enum único)

```text
MERCHANT        informado pelo comerciante
USER            informado por consumidor
FLYER           extraído de encarte
PUBLIC_SOURCE   fonte pública autorizada
HISTORICAL      derivado de observações anteriores (rotulado como histórico)
CALCULATED      estimativa determinística (com fórmula, entradas e intervalo)
```

`ESTIMATED` não é fonte: estimativa é `CALCULATED` e exibida como estimativa. Verificado/validado é **status**, não fonte.

## Status do preço

`CURRENT`, `STALE`, `EXPIRED`, `CONFLICTING`, `UNVERIFIED`, `VERIFIED`. TTL configurável por categoria.

## Condição de pagamento

`NORMAL`, `PIX`, `DEBIT`, `CREDIT`, `LOYALTY`, `COUPON`.

## PriceObservation (append-only)

```text
id, product_variant, store
price (NUMERIC 12,2), currency
payment_condition, is_promotional
pack_quantity, pack_unit        # base do preço por unidade
source, status
collected_at, valid_from, valid_until
confidence_score, confidence_level
created_by, created_at
supersedes                      # observação anterior (nunca UPDATE do valor)
```

`PriceEvidence`: arquivo (referência de storage), hash, origem, tipo, usuário, data/hora. Não público por padrão.

## Geografia

`Store.location`: `PointField(geography=True, srid=4326)` com índice GiST. Consultas por raio via `ST_DWithin`. Nunca lat/lon como texto.

## Produto

- `Product`: conceito (ex.: Arroz Tio João). `ProductVariant`: apresentação (tipo, peso, volume, unidade).
- `gtin` opcional e único quando presente. Sem GTIN: identidade composta por nome normalizado, marca, variante, quantidade e unidade; associação posterior a um GTIN.
- Normalização: acentos, caixa, abreviações, unidades e marcas, para evitar duplicatas.

## Retenção e exclusão

Soft delete onde fizer sentido. Histórico comercial, auditoria e dados financeiros têm retenção própria (definida no M1/LGPD.md); nunca apagados silenciosamente.

## Mapa de modelos por marco

Ver [ARCHITECTURE.md](ARCHITECTURE.md).
