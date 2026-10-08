# ADR 0009: Localização do consumidor no corpo do POST

Status: **Aceita**

Contexto: coordenadas em query string aparecem em logs de acesso (servidor, proxy, CDN) e no histórico de navegação.

Decisão: buscas por proximidade são `POST` com `lat`/`lon` no corpo; `GET` com coordenadas na URL retorna 405. A localização do consumidor não é gravada (nem na auditoria). Nos relatos de preço, as coordenadas só servem para marcar `location_verified` (raio de 500 m da loja) e são descartadas.

Consequências: semântica de `POST` para uma leitura (sem cache HTTP; a alternativa futura é cache de aplicação por região arredondada).
