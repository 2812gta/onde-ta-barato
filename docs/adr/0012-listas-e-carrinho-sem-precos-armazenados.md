# ADR 0012: Listas e carrinho guardam quantidades, nunca preços

Status: **Aceita**

Contexto: o M4 traz a lista de compras e o carrinho na loja. A tentação é gravar o preço no item para "lembrar quanto custava". Esse valor envelhece, vira promessa que o mercado não cumpre e duplica a verdade que já mora no histórico de preços.

Decisão:
- `ShoppingList` e `ShoppingCart` guardam apenas produto (apresentação) e quantidade. Preços, promoções e totais são **calculados a cada leitura** com o mesmo código das recomendações (`build_quote`, `best_promotion`), sem acúmulo e só com promoções confirmadas (ADR 0010).
- Item sem preço utilizável fica fora do total e é contado, nunca estimado. Preço vencido não entra; desatualizado entra sinalizado; em conflito vale o maior.
- Ao finalizar, o carrinho grava uma única vez `final_total` e `final_savings`, base do histórico de economia (M7). Esses valores são o que foi mostrado ao usuário naquele momento.
- São dados pessoais sem valor de auditoria: ao excluir a conta são **apagados** (não anonimizados) e entram na exportação (LGPD).
- Existe no máximo um carrinho aberto por usuário (restrição no banco). O recurso de outro usuário responde 404.
- `shopping_cart/pricing.py` entra na lista protegida do teste de isolamento comercial: nenhum conceito de plano, patrocínio ou anúncio pode influenciar o total.

Consequências: o app sempre mostra o preço atual e a confiança dele; reabrir uma lista antiga nunca exibe preço velho como se fosse atual. Em troca, o total muda entre leituras quando os preços mudam, o que é o comportamento desejado.
