# ADR 0011: Preço em conflito é tratado de forma conservadora; sem dados, sem veredito

Status: **Aceita**

Contexto: quando comerciante e consumidor discordam (R$ 20,00 contra R$ 18,90), escolher o menor valor promete uma economia que talvez não exista, e escolher o maior esconde uma possível economia.

Decisão:
- O total usa o **valor mais alto** (não prometemos o que não conseguimos sustentar). O valor mais baixo é exibido como total otimista e o conflito é avisado.
- O rótulo "Menor preço encontrado na nossa base" é retido quando o menor valor está em conflito.
- Quando a cobertura, a confiança ou o número de lojas são insuficientes, o veredito é `INSUFFICIENT_DATA` com a mensagem fixa "Não foi possível determinar o melhor mercado com segurança.". Empates técnicos viram `TIE`.
- Planos completos (lista inteira disponível) sempre vêm antes de planos parciais.

Consequências: respostas mais cautelosas; em regiões com poucos dados o app dirá "não sabemos" com frequência, o que é o comportamento desejado ("honestidade é uma funcionalidade").
