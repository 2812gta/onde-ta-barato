# LGPD (rascunho técnico, requer revisão jurídica)

Este documento não é parecer jurídico. Deve ser revisado por advogado antes do primeiro deploy.

## Princípios

Finalidade, necessidade (coletar apenas o necessário), transparência, segurança, prevenção. **Base legal definida por finalidade**; consentimento não é a base de tudo.

## Finalidades e bases (proposta inicial)

| Dado / tratamento | Finalidade | Base legal proposta |
|---|---|---|
| Conta (e-mail, nome, senha) | Autenticação e uso do serviço | Execução de contrato |
| Localização para buscar lojas | Lojas próximas, distância | Consentimento (permissão do SO + opt-in), uso pontual |
| Fotos de preço | Evidência de contribuição | Consentimento, com retenção limitada |
| Contribuições de preço | Base de preços da plataforma | Legítimo interesse (avaliar) / consentimento |
| Auditoria e antifraude | Segurança e prevenção a fraude | Legítimo interesse / obrigação legal |
| Dados de comerciante (CNPJ etc.) | Verificação e operação | Execução de contrato |

## Direitos do titular (implementar no M1)

Acesso e exportação, correção, exclusão/anonimização, revogação de consentimento, informação sobre compartilhamento, portabilidade. Gestão de consentimentos com versão e data.

## Localização

Tratada como dado de alto risco operacional: sem rastreamento contínuo; preferir região/raio; precisão exata só quando necessário e não armazenada além do necessário; nunca exposta a outros usuários.

## Fotografias

Finalidade, retenção definida, acesso controlado, não públicas por padrão, processo futuro de remoção de rostos e documentos. Envio a terceiros (OCR/IA) documentado, com o fornecedor e a transferência.

**Como o M5 trata (ADR 0013):** o OCR roda no aparelho, então a foto **não vai a nenhum terceiro**. No servidor, EXIF/GPS são removidos antes de gravar. A foto fica no rascunho por no máximo 24 h e é apagada ao confirmar, cancelar ou expirar (`purge_stale_drafts`); só é mantida como evidência do preço quando o usuário confirma e a evidência é anexada ao seu registro. Fica o SHA-256 para detectar reuso. A localização enviada ao confirmar só checa proximidade e não é armazenada. **Pendente:** prazo de retenção da evidência confirmada, regra de exclusão da evidência quando a conta é excluída, e processo de remoção de rostos/documentos.

## Retenção (a definir no M1)

Logs de aplicação, auditoria, histórico de preços, evidências, contas excluídas (anonimização preserva integridade do histórico de preços).

## Pendências

Encarregado (DPO), RIPD para localização e imagens, tratamento de menores, contrato com operadores (nuvem, IA, e-mail).
