# Roadmap

Regra: executar o marco, testar, documentar, apresentar e **aguardar aprovação** antes do próximo.

| Marco | Escopo | Estado |
|---|---|---|
| M0 Fundação | Auditoria do ambiente, Git, estrutura, documentação inicial | Concluído |
| M1 Backend | Django + DRF, PostgreSQL, JWT, RBAC (com matriz de permissões), AuditLog, OpenAPI, rate limiting, e-mail transacional, consentimento e exclusão de conta (LGPD), soft delete, **CI (GitHub Actions)**, Dockerfile `dev`/`prod` | **Em validação.** PostGIS 3.6 e GeoDjango validados localmente. CI, Dockerfile e compose escritos mas **não executados** |
| M2 Núcleo comercial | Merchant, Store (PointField), Product/Variant (GTIN), Category, PriceObservation/Evidence, histórico, confiança, **seed de lojas e produtos** | **Em validação.** Seed de lojas (OSM) **não validado com dados reais** (Overpass indisponível); endpoint de upload de evidência fica para o M5 |
| M3 Inteligência de preços | Preço por unidade, promoções, conflitos, score, custo-benefício, distância, teste de isolamento comercial | **Em validação.** Pesos e R$/km são uma primeira proposta, sem calibração com dados reais; sem acúmulo de promoções; no máximo 2 lojas por compra |
| M4 Flutter | Login, localização, lojas próximas, produtos, preços, lista, carrinho | **Concluído (2026-10-08), aprovado pelo usuário.** App Android validado em aparelho real: login, lojas próximas, produtos, preços com conflito exibido, listas, "Onde comprar?", carrinho (remoção por gesto). Backend de listas e carrinho (ADR 0012), 612 testes. **Limites:** `flutter analyze` e os testes do app não rodaram neste PC (Flutter 3.29.1 / Dart 3.7, o app exige Dart ^3.12.2); só o CI ou o notebook os executam. Carrinho remove item só por gesto de deslizar (sem lixeira visível). Pix/Débito/Crédito e "Finalizar compra" não foram exercitados no aparelho. Localização usa GPS real; a coordenada fixa vem de `--dart-define` de demonstração |
| M5 Câmera | Câmera, OCR, identificação, IA, confirmação, contribuição, FraudSignal | **Em andamento.** Backend pronto (ADR 0013, 681 testes): rascunho por foto, interpretação do texto lido (FACT/INFERENCE), confirmação obrigatória, evidência sem EXIF/GPS, retenção de 24 h do rascunho, sinais de fraude para a moderação. **Falta o app** (câmera, ML Kit, tela de revisão), que exige Flutter ≥ 3.12 e não compila neste PC. Limites de fraude são uma primeira proposta, sem calibração. `purge_stale_drafts` precisa ser agendado no deploy |
| M6 Comerciantes | Cadastro, verificação, preços, promoções, ofertas, moderação | Pendente |
| M7 Inteligência avançada | Recomendações, otimização de lista, histórico, economia, analytics | Pendente |
| M8 Escala | Voz, notificações (FCM/APNs), reputação, cashback, fidelidade | Pendente |

## Antes do primeiro deploy

- Backup do PostgreSQL com restauração testada.
- Contato de segurança definido (SECURITY.md).
- Revisão jurídica de TERMS, PRIVACY, CONTRIBUTION_POLICY e LGPD.
- Definição de hospedagem.
