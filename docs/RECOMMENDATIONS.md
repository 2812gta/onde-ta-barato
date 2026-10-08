# Recomendações e Custo-Benefício

Não é uma caixa-preta: o algoritmo é determinístico, todos os pesos são públicos e toda resposta traz os números que a justificam. Código em `apps/recommendations/`.

## O que o motor pode ver (lista fechada)

Preço (com fonte, idade, frescor, confiança, conflito), distância, quantidade, promoções confirmadas, condição de pagamento escolhida pelo consumidor e qualidade dos dados. **Não existe entrada para plano, pagamento, patrocínio ou anúncio.** Um teste (`tests/architecture/`) trava a lista exata de campos e falha se qualquer módulo de decisão importar ou nomear algo comercial; foi validado injetando violações.

## Passo a passo

1. **Cotação por loja e item** (`quotes.py`): preços vencidos nunca entram; preços antigos entram marcados. Só valem as condições que se aplicam ao consumidor (um preço Pix não é oferecido a quem paga no cartão). Se as fontes discordam, a cotação usa o **valor mais alto** (não prometemos economia que não conseguimos sustentar) e guarda o mais baixo para um total "otimista".
2. **Planos:** comprar tudo em uma loja, ou **dividir entre duas** (cada item vai para a loja de menor custo efetivo; só vale se as duas lojas recebem itens).
3. **Custo do plano:** `itens − cashback + deslocamento`. Deslocamento = distância em linha reta (PostGIS) × fator de desvio 1,3 × R$/km. Em duas paradas: casa→A→B→casa, com a distância A–B também do PostGIS.
4. **Pontuação** em cinco componentes normalizados de 0 a 1, com pesos por modo.
5. **Ranking:** planos **completos** sempre vêm antes dos parciais (um plano parcial é barato porque deixa itens de fora; nunca é normalizado contra os completos). Desempate determinístico (custo, distância, ids).
6. **Veredito honesto**, abaixo.

## Componentes

| Componente | Como é calculado |
|---|---|
| `cost` | 1 para o menor custo efetivo, 0 para o maior, entre planos do mesmo grupo |
| `distance` | idem, para a distância do roteiro |
| `coverage` | fração da lista disponível |
| `promotions` | economia de promoções confirmadas ÷ valor bruto, com 25% valendo nota máxima |
| `confidence` | confiança média dos preços ponderada pelo valor da linha; ×0,7 quando há conflito |

## Pesos por modo (cada linha soma 1,0)

| Modo | cost | distance | coverage | promotions | confidence |
|---|---|---|---|---|---|
| `ECONOMIZAR_MAIS` | 0,70 | 0,05 | 0,15 | 0,00 | 0,10 |
| `MAIS_PROXIMO` | 0,15 | 0,60 | 0,20 | 0,00 | 0,05 |
| `MELHOR_CUSTO_BENEFICIO` (padrão) | 0,40 | 0,10 | 0,20 | 0,10 | 0,20 |
| `MENOS_DESLOCAMENTO` (nunca divide a compra) | 0,20 | 0,55 | 0,20 | 0,00 | 0,05 |
| `MELHORES_PROMOCOES` | 0,25 | 0,05 | 0,15 | 0,45 | 0,10 |

Configuráveis em `RECOMMENDATION` (settings). **São uma primeira proposta, não calibrada com dados reais.**

## Quando dizemos "não sabemos"

`INSUFFICIENT_DATA` ("Não foi possível determinar o melhor mercado com segurança.") quando:

- a melhor opção cobre menos de 50% da lista;
- a confiança média dos preços é menor que 0,35;
- há menos de duas lojas com dados suficientes para comparar.

Nesses casos os planos encontrados ainda são mostrados, mas **sem** "melhor" e sem justificativa inventada. Se as duas melhores opções ficam a menos de 0,02 de pontuação, o veredito é `TIE` (empate), não um vencedor.

## Explicação

Cada frase é montada a partir dos números reais do plano: cobertura da lista, economia contra a **média** das outras opções (e, se a recomendada não é a mais barata, uma frase dizendo qual é e quanto custa), distância ou roteiro, promoções confirmadas, % de preços atualizados nas últimas 24 h. Os avisos dizem o que ficou de fora: itens sem preço, preços em conflito (com o total otimista), promoção não confirmada não contada, preços desatualizados e as premissas de deslocamento.

## Comparação de um produto (`POST /variants/{id}/compare/`)

Ordena por **preço por unidade** (R$/kg, R$/L…), depois por distância. Confiança, verificação e status do comerciante são exibidos, mas **não reordenam** (há testes para isso). O rótulo **"Menor preço encontrado na nossa base"** só aparece com pelo menos duas lojas comparadas; é retido quando o menor valor tem conflito entre fontes; recebe ressalvas se estiver desatualizado, tiver baixa confiança ou houver empate. Sempre vêm: data da análise, lojas no raio, lojas com preço, cobertura, condições consideradas.

## Premissas e limites

- O R$/km padrão (R$ 0,80) e o fator de desvio (1,3) são suposições; o consumidor pode informar o próprio R$/km (0 = a pé).
- Distância em linha reta, não rota real (ADR 0007); pode subestimar trajetos com barreiras (rios, vias sem travessia).
- Dividir em no máximo **2 lojas** (3 ou mais ficam para depois). O pareamento considera as 8 lojas mais promissoras.
- Não há estoque: um preço informado não garante que o produto esteja na prateleira.
- A verificação do comerciante, que é um processo editorial e gratuito, eleva a confiança do preço e, por isso, pesa um pouco na pontuação. Pagamento não tem nenhum caminho até aqui.
- Sem histórico de consumo, sem substituição de produtos equivalentes, sem horário de funcionamento das lojas.
