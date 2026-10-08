# Promoções

O motor (`apps/promotions/engine.py`) é uma função pura: sem banco, sem IA. Mesma entrada, mesma saída. Cada regra é um JSON validado quando o comerciante a salva, não no momento da compra.

## Regras de cálculo

- Tudo em `Decimal`. O cálculo é exato e **arredondado uma única vez, no total da linha**, em centavos (`ROUND_HALF_UP`). Nunca por unidade: 3 × R$ 0,55 com 15% de desconto dá R$ 1,40, e não R$ 1,41.
- Promoção **só reduz** o preço. Se não reduzir, é "não aplicável" e a razão é devolvida.
- A razão de uma promoção não valer sempre é informada ("Válido apenas para pagamento via Pix", "Leve 3 para ativar a promoção", "Fora do horário da promoção").
- **Uma promoção por linha, sem acúmulo.** Vale a de maior benefício (economia + cashback); empate vai para o menor valor líquido e depois para a regra mais antiga.
- **Cashback não é desconto:** o valor pago no caixa continua cheio; o cashback é devolvido depois e aparece à parte (`effective_cost = net − cashback`).
- Dias da semana e horários são avaliados em **America/Fortaleza**, não em UTC. Janelas que cruzam a meia-noite funcionam (22:00–06:00).
- `float` é rejeitado (regra, preço e quantidade).

## Tipos suportados

| Tipo | Parâmetros | Exemplo |
|---|---|---|
| `PERCENTAGE` | `percent` | 10% off |
| `FIXED_PRICE` | `bundle_price`, `bundle_quantity` (padrão 1) | **3 por R$ 20**: 5 un a R$ 10 = 20 + 2×10 = **R$ 40** |
| `BUY_X_PAY_Y` | `buy`, `pay` | Leve 3, pague 2: 7 un = 2 grupos + 1 = paga 5 |
| `SECOND_UNIT_DISCOUNT` | `percent` | 2ª unidade com 50% |
| `QUANTITY_DISCOUNT` | `min_quantity` + `percent` ou `unit_price` | 10% a partir de 3 |
| `CASHBACK` | `percent` ou `amount_per_unit`, `max_cashback?` | 5% de volta |
| `PIX_PRICE` | `percent` ou `unit_price` | só se o pagamento é Pix |
| `LOYALTY_PRICE` | `percent` ou `unit_price` | só para clube de fidelidade |
| `COUPON` | `code`, `percent` ou `amount`, `min_quantity?` | só com o cupom informado |
| `TIME_LIMITED` | `start_time`, `end_time`, `base` | 18h–20h |
| `DAY_LIMITED` | `weekdays` (0=segunda…6=domingo), `base` | só às quartas |

`TIME_LIMITED` e `DAY_LIMITED` embrulham uma regra base (não aninham outra temporal).

## Promoção confirmada ou não

Uma promoção é **confirmada** apenas se o comerciante foi verificado. Nas recomendações:

- promoção **confirmada** entra no total;
- promoção **não confirmada** não entra: é informada à parte ("possível economia de R$ X, não confirmada").

Isso impede que um cadastro novo, sem verificação, vença uma comparação com uma promoção que ninguém checou. É a regra "se a promoção não puder ser confirmada, dizer que não foi confirmada".

## Promoção não é anúncio

`Promotion` é um dado de preço do comerciante. Não tem posição, orçamento nem destaque, e não pode influenciar ordem. Publicidade (OFERTA PATROCINADA) é outro conceito, ainda não implementado, e ficará separado (M6/M8).

## API

- `POST /stores/{id}/promotions/` · `GET /stores/{id}/promotions/` · `DELETE /promotions/{id}/` (desativa; o registro permanece).
- `POST /promotions/calculate/`: calculadora sem estado que usa o mesmo motor (para testar uma regra ou, no futuro, o carrinho).

## Limitações

- Sem acúmulo de promoções (decisão consciente, ADR 0010).
- Sem promoções "do mercado todo" ou por categoria: cada regra vale para um produto em uma loja.
- Condições de estoque e limite por cliente não existem.
- Promoções informadas por consumidores (encarte, foto) ainda não existem.
