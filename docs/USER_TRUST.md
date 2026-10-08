# Confiança do Consumidor

## Regras inegociáveis

1. Pagamento (assinatura, anúncio, campanha, destaque) **não** altera: menor preço, melhor custo-benefício, ranking orgânico, confiança, avaliações.
2. Publicidade é sempre rotulada (**OFERTA PATROCINADA** / **ANÚNCIO**) e visualmente separada do resultado orgânico.
3. O preço informado pelo **comerciante** é dado de catálogo e participa do ranking de preço como qualquer outra fonte. Ele não é publicidade.
4. Toda recomendação traz explicação baseada em dados reais. Dados insuficientes: "Não foi possível determinar o melhor mercado com segurança."
5. Honestidade como funcionalidade: preço antigo é dito antigo; promoção não confirmada é dita não confirmada; conflitos são mostrados, não escondidos; IA incerta pede confirmação.

## Linguagem

- Evitar absolutos ("o mais barato da cidade"). Usar: "Menor preço encontrado na nossa base", com data, número de lojas analisadas e cobertura.
- Preço sempre com fonte, data, condição de pagamento, validade e aviso: "Pode haver diferença no caixa."

## Garantias técnicas

- Módulo de recomendação sem dependência de módulos comerciais (teste de arquitetura).
- Testes de integridade comercial obrigatórios: `merchant_payment`, `subscription`, `sponsorship`, `advertising`, `commercial_score` não podem influenciar rankings orgânicos.
- Conflito entre fontes: exibir todas as observações relevantes com fonte e idade.
