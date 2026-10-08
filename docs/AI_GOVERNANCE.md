# Governança de IA e OCR

## O que a IA pode fazer

Interpretar OCR, normalizar produtos, classificar categorias, sugerir correções, explicar recomendações com dados fornecidos, detectar inconsistências.

## O que a IA não pode fazer

Inventar preços, promoções, lojas ou evidências; alterar ranking; criar avaliações; confirmar dados sem evidência.

## FATO vs INFERÊNCIA

Toda extração de imagem marca cada campo:

- **FATO**: texto realmente lido na imagem (com bounding box e confiança quando disponível).
- **INFERÊNCIA**: informação interpretada (ex.: marca deduzida, unidade normalizada).

Os dois nunca são misturados. Contribuição só é registrada após **confirmação explícita do usuário** (CONFIRMAR / CORRIGIR / CANCELAR).

## Rótulos de origem em respostas

`AI_INFERENCE`, `VERIFIED_DATA`, `USER_DATA`, `MERCHANT_DATA`. Respostas sobre dados comerciais incluem fonte, confiança e timestamp.

## Provedores

- `AIProvider` e `OCRProvider` são interfaces; implementações trocáveis (OpenAI, Ollama, Tesseract, ML Kit, etc.).
- Preferência: processamento local (menor custo, latência e exposição).
- Envio de imagem a terceiro exige documentação do fornecedor e da transferência (ver LGPD.md) e limite de custo/uso por usuário.
- Estimativas de preço são calculadas por fórmula, nunca geradas por LLM.
