# Política de Segurança

## Reporte de vulnerabilidades

Não abra issue pública. Envie os detalhes por e-mail privado ao mantenedor (contato a definir antes do primeiro deploy — pendência registrada em docs/ROADMAP.md).

Inclua: descrição, passos para reproduzir, impacto estimado. Não acesse dados de terceiros nem degrade o serviço durante testes.

## Regras do repositório

- Nunca commitar `.env`, tokens, chaves, certificados ou credenciais. Use `.env.example`.
- Se um segredo vazar, considere-o comprometido: revogar e rotacionar antes de remover do histórico.

Arquitetura de segurança: [docs/SECURITY.md](docs/SECURITY.md).
