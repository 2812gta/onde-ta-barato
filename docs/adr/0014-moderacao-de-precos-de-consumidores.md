# ADR 0014: Moderação de preços de consumidores (ocultar com justificativa e recurso)

Status: **Aceita**

Contexto: a política de contribuição (CONTRIBUTION_POLICY.md) diz que contribuições contestadas são ocultadas com justificativa e registro em auditoria, e que há recurso. As observações de preço são somente-anexar, então ocultar não pode ser uma edição. Os sinais de fraude do M5 (ADR 0013) só apontam; faltava quem decide.

Decisão:
- **Ocultar é um registro novo**, `PriceModeration` (`HIDE`, `RESTORE`, `UPHOLD`), nunca uma alteração do preço. O estado atual é a última decisão. O preço, a evidência e o histórico de decisões permanecem; o preço só deixa de aparecer para os consumidores.
- **Um único filtro** (`moderation.selectors.exclude_hidden`) é aplicado em `current_prices` e `price_history`. Como telas de preço, recomendação e carrinho leem preço só por `current_prices`, um preço oculto some de todas elas. Um teste confere que nenhuma delas consulta `PriceObservation` direto. Se o preço mais novo é ocultado, o anterior volta a aparecer, com a idade dele.
- **Justificativa obrigatória** (10 a 1000 caracteres) em toda decisão, mostrada ao contribuinte. Toda decisão gera `AuditLog`. Decisões sobre o mesmo preço são serializadas (bloqueio de linha), para dois moderadores não ocultarem duas vezes.
- **Só moderadores** (`moderation.review`: MODERATOR, ADMIN, SUPERADMIN). Dono, gerente ou operador de loja **não** podem ocultar preço de concorrente nem de cliente da própria loja. Ninguém modera o próprio preço nem revisa sinais das próprias contribuições.
- **Escopo:** só preços `USER`. Preço de comerciante é tratado pela verificação/suspensão do comerciante, não por aqui.
- **Recurso:** o contribuinte, e só ele, recorre **uma vez** por decisão de ocultar. O moderador responde restaurando (`RESTORE`) ou mantendo oculto (`UPHOLD`); `UPHOLD` encerra o recurso. Um moderador ainda pode restaurar depois, por decisão própria registrada.
- **Sinal de fraude revisado** (`SignalReview`: confirmado ou descartado) não oculta nada sozinho: a revisão do sinal e a decisão sobre o preço são separadas. A fila (`/moderation/queue/`) lista sinais ainda não revistos (mais graves primeiro) e recursos sem resposta, e identifica o contribuinte só por um id opaco, nunca por e-mail ou nome.
- `moderation/selectors.py` e `moderation/services.py` entram na lista protegida do teste de isolamento comercial: nada comercial pode decidir o que é ocultado.

Consequências: a ocultação é reversível e auditável, e não apaga prova. Em troca, a fila é uma API: moderadores ainda não têm tela (o Django Admin é só leitura nesses modelos, de propósito, para toda decisão passar pela justificativa e pela auditoria). Falta também o contribuinte ver o estado e recorrer no app.
