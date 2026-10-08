# Roadmap

Regra: executar o marco, testar, documentar, apresentar e **aguardar aprovação** antes do próximo.

| Marco | Escopo | Estado |
|---|---|---|
| M0 Fundação | Auditoria do ambiente, Git, estrutura, documentação inicial | Concluído |
| M1 Backend | Django + DRF, PostgreSQL, JWT, RBAC (com matriz de permissões), AuditLog, OpenAPI, rate limiting, e-mail transacional, consentimento e exclusão de conta (LGPD), soft delete, **CI (GitHub Actions)**, Dockerfile `dev`/`prod` | **Em validação.** PostGIS 3.6 e GeoDjango validados localmente. CI, Dockerfile e compose escritos mas **não executados** |
| M2 Núcleo comercial | Merchant, Store (PointField), Product/Variant (GTIN), Category, PriceObservation/Evidence, histórico, confiança, **seed de lojas e produtos** | **Em validação.** Seed de lojas (OSM) **não validado com dados reais** (Overpass indisponível); endpoint de upload de evidência fica para o M5 |
| M3 Inteligência de preços | Preço por unidade, promoções, conflitos, score, custo-benefício, distância, teste de isolamento comercial | Pendente |
| M4 Flutter | Login, localização, lojas próximas, produtos, preços, lista, carrinho | Pendente |
| M5 Câmera | Câmera, OCR, identificação, IA, confirmação, contribuição, FraudSignal | Pendente |
| M6 Comerciantes | Cadastro, verificação, preços, promoções, ofertas, moderação | Pendente |
| M7 Inteligência avançada | Recomendações, otimização de lista, histórico, economia, analytics | Pendente |
| M8 Escala | Voz, notificações (FCM/APNs), reputação, cashback, fidelidade | Pendente |

## Antes do primeiro deploy

- Backup do PostgreSQL com restauração testada.
- Contato de segurança definido (SECURITY.md).
- Revisão jurídica de TERMS, PRIVACY, CONTRIBUTION_POLICY e LGPD.
- Definição de hospedagem.
