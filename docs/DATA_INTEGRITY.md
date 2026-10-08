# Integridade dos Dados

O sistema deve responder, para qualquer preço: de onde veio, quando, quem registrou, se foi confirmado, se foi alterado, qual era o valor anterior, qual a confiança, se o comerciante informou, se um consumidor fotografou.

## Princípios

- **Append-only**: preço é observação; correções criam nova observação que referencia a anterior (`supersedes`).
- **Auditoria**: operações críticas geram `AuditLog` (ator, ação, entidade, valor anterior/novo, timestamp, metadados). Sem dados sensíveis desnecessários.
- **Evidência**: foto/encarte/documento com hash; acesso controlado.
- **Confiança**: score documentado e configurável a partir de idade, fonte, evidência, confirmações, histórico do contribuinte, contradições e confirmação do comerciante. Número de votos sozinho nunca basta.
- **Conflito**: nunca escolher silenciosamente; exibir as observações com fonte e idade.
- **TTL por categoria**: hortifruti curto, estáveis longo, promoção até o fim da vigência, encarte até a data de término.
- **Estimativas** são determinísticas: fórmula, entradas, data, intervalo e rótulo visível.
- **Moderação** nunca apaga: oculta, registra justificativa e auditoria.

Algoritmo de confiança: proposta formal a ser aprovada no M2/M3.
