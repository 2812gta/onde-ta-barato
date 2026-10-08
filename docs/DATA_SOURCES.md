# Fontes de Dados Abertas e Atribuição

O app pode semear lojas e produtos a partir de dados abertos. Isso exige **atribuição** e respeito às licenças. Nada é copiado de bases comerciais.

## OpenStreetMap (lojas)

- Licença: ODbL. Atribuição obrigatória: **© OpenStreetMap contributors** (https://www.openstreetmap.org/copyright), visível onde as lojas forem exibidas (lista/mapa e página "Sobre").
- Comando: `python manage.py import_osm_stores [--bbox S,W,N,E] [--dry-run] [--file overpass.json]`. Área padrão: região metropolitana de Fortaleza.
- Só entram elementos com **nome e coordenada** de lojas de alimentos; nada é inventado. A carga é idempotente; lojas já reivindicadas por um comerciante nunca são sobrescritas.
- Usa instâncias públicas do Overpass (compartilhadas e às vezes sobrecarregadas): o comando tenta espelhos, identifica-se com `User-Agent` e falha com mensagem clara. Para volume maior, hospedar uma instância própria ou usar extratos da Geofabrik.
- **Estado:** a lógica foi testada offline com payloads no formato documentado; **não foi possível validar contra a API real** (os servidores devolveram 504/500 durante o desenvolvimento). Rode `--dry-run` antes da primeira carga.

## Open Food Facts (produtos)

- Licença do banco: ODbL. Atribuição: **Open Food Facts contributors** (https://world.openfoodfacts.org). Imagens têm licença própria (CC BY-SA) e **não são importadas**.
- Comando: `python manage.py import_off_products --gtin 789... [--search arroz] [--file produtos.json] [--dry-run]`.
- Só entra produto com GTIN válido (dígito verificador), nome e quantidade interpretável. A categoria só é atribuída por palavra-chave inequívoca; sem correspondência fica vazia.
- **Estado:** validado contra a API real com 3 GTINs (`--dry-run`). A cobertura de produtos brasileiros no OFF é parcial.

## Preços

Nenhuma fonte aberta de preços é usada. Preços vêm de comerciantes, consumidores e (fase 2) encartes autorizados. Coleta externa (scraping) só com permissão explícita dos termos do site, `robots.txt` e LGPD.
