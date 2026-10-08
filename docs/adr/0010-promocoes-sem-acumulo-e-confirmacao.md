# ADR 0010: Promoções sem acúmulo; só confirmadas entram no total

Status: **Aceita**

Contexto: somar promoções (percentual + leve 3 pague 2 + cupom...) multiplica casos de borda e é uma fonte clássica de preço calculado errado. Além disso, um comerciante recém-cadastrado, ainda sem verificação, poderia publicar uma promoção agressiva e vencer comparações.

Decisão:
- Uma promoção por linha: a de maior benefício (economia + cashback), com desempate determinístico. Sem acúmulo.
- Nas recomendações, só promoções de comerciantes **verificados** (confirmadas) entram no total. As demais são informadas como "possível economia, não confirmada".
- Cashback fica fora do preço pago; entra apenas no custo efetivo.

Consequências: o total mostrado nunca depende de uma promoção não revisada; acúmulo pode ser reavaliado com dados reais. Um comerciante legítimo mas ainda não verificado não vê suas promoções pesarem até a verificação.
