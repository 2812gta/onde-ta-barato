# ADR 0008: Relógio estritamente crescente nas tabelas de histórico

Status: **Aceita**

Contexto: o relógio do Windows tem resolução de ~15,6 ms. Duas escritas seguidas recebiam o mesmo `created_at`, tornando indefinida a ordem em "qual foi o preço anterior?" e "última entrada de auditoria". Foi descoberto quando um teste passou isolado e falhou na suíte completa.

Decisão: `apps/core/clock.now()` nunca devolve valor menor ou igual ao anterior dentro do processo (soma 1 µs em empates). É usado como `default` em `AuditLog`, `MerchantVerification`, `PriceObservation`, `PriceEvidence` e `PriceConfirmation`. Consultas de "mais recente" desempatam por `created_at`.

Limite: garante ordem dentro de um processo. Entre processos ou servidores simultâneos, escritas concorrentes não têm ordem "verdadeira" de qualquer forma.
