# Integridade dos Dados

O sistema responde, para qualquer preço: de onde veio, quando, quem registrou, se foi confirmado, se foi alterado, qual era o valor anterior, qual a confiança, se o comerciante informou, se um consumidor fotografou.

| Pergunta | Onde está a resposta |
|---|---|
| De onde veio? | `source` (+ `PriceEvidence` quando existe) |
| Quando foi registrado? | `collected_at` (visto) e `created_at` (gravado) |
| Quem registrou? | `created_by` (interno); a API pública mostra só `ESTABELECIMENTO`/`CONSUMIDOR` |
| Foi confirmado? | `PriceConfirmation` → `confirmations`, `contradictions`, `verification` |
| Foi alterado? Qual era o valor anterior? | `supersedes` → `previous_price` no histórico |
| Qual a confiança? | `confidence_score/level` + `confidence_factors` (explicação) |
| O comerciante informou? Um consumidor fotografou? | `source`, `has_evidence`, `location_verified` |

## Princípios

- **Somente-anexar:** correção = nova observação com `supersedes`. Nenhum UPDATE/DELETE em histórico (modelo e queryset bloqueiam).
- **Ordem confiável:** relógio estritamente crescente e desempate por `created_at`. Sem isso, "qual foi o preço anterior?" seria ambíguo em relógios de baixa resolução (Windows: 15,6 ms).
- **Auditoria:** toda escrita relevante gera `AuditLog` (ator, ação, entidade, valor anterior/novo, metadados). Segredos são removidos antes de gravar; IP só se `AUDIT_STORE_IP` estiver ligado.
- **Conflito nunca é resolvido em silêncio:** observações de fontes diferentes, para a mesma loja e condição, que divirjam mais de **1%** aparecem **todas**, marcadas `CONFLICTING`. Condições de pagamento diferentes (Pix vs normal) não são conflito.
- **Preço antigo é dito antigo.** Listagens incluem `STALE` e `EXPIRED` com o rótulo; só saem da listagem ao passar de `PRICE_MAX_LISTED_AGE_DAYS` (90), continuando no histórico.
- **Sem afirmação de "melhor preço"** enquanto o algoritmo de custo-benefício não existe (M3). A busca de preços ordena apenas por distância.
- **Estimativas** (fonte `CALCULATED`) serão determinísticas, com fórmula, entradas e intervalo; nenhum fluxo as cria ainda.
- **Moderação nunca apaga:** oculta, registra justificativa e auditoria (fila de moderação: M6).

## Frescor (`apps/prices/freshness.py`)

| Situação | Estado |
|---|---|
| Com `valid_until` (promoção, encarte) | `CURRENT` até a data; depois `EXPIRED` |
| Sem validade: idade ≤ TTL da categoria | `CURRENT` |
| TTL < idade ≤ 2×TTL | `STALE` |
| Idade > 2×TTL | `EXPIRED` |

## Confiança (`apps/prices/confidence.py`)

```text
score = base(fonte) × frescor(idade/TTL)
        + bônus de evidência + bônus de localização
        + min(confirmações × 0,08 ; 0,24)
        − min(contradições × 0,10 ; 0,30)
        + (reputação − 0,5) × 0,20
        limitado a [0, 1]        BAIXA < 0,35 ≤ MÉDIA < 0,65 ≤ ALTA

        preço de CONSUMIDOR sem evidência: teto 0,649 (nunca ALTA)
```

| Fonte | Base | | Frescor (idade/TTL) | Fator |
|---|---|---|---|---|
| MERCHANT (comerciante verificado) | 0,70 | | ≤ 0,5 | 1,0 |
| FLYER | 0,65 | | 1,0 | 0,6 |
| PUBLIC_SOURCE | 0,60 | | 2,0 | 0,2 |
| MERCHANT (não verificado) | 0,55 | | > 2,0 | 0,1 |
| USER | 0,40 | | | |
| HISTORICAL | 0,30 | | | |
| CALCULATED | 0,25 | | | |

Propriedades garantidas por teste:

- **Preço de consumidor sem evidência nunca é ALTA**, não importa quantos votos ou qual localização (teto explícito). Votos e coordenadas são baratos de forjar (contas descartáveis, GPS falsificado); ALTA exige evidência anexada ou uma fonte mais forte. Esta regra nasceu de uma falha encontrada em revisão: 3 votos + localização davam 0,69 (ALTA) sem prova alguma.
- Autor e equipe da loja **não votam**; cada usuário vota uma vez; preço expirado não recebe voto.
- Pesos configuráveis em `PRICE_CONFIDENCE`; cada resposta devolve os fatores (`confidence_factors`).
- A entrada não tem campo comercial algum. Ser "verificado" vem do fluxo de revisão, nunca de pagamento. `tests/architecture/` falha se um módulo de preço/confiança/ordenação importar ou nomear algo comercial.
- A reputação do contribuinte é neutra (0,5) por enquanto; o histórico de reputação entra na fase 2.

**Limitações conhecidas:** os pesos são uma primeira proposta, não calibrados com dados reais; ainda não há detecção de preços fora do padrão (antifraude, M5); contas falsas podem contornar a regra de votos independentes (mas sem evidência não alcançam ALTA); a evidência em si ainda não é verificada por humanos nem por IA.
