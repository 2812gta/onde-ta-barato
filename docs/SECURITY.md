# Arquitetura de Segurança

Alvo de implementação em M1 (itens marcados) e marcos seguintes.

- **Transporte:** HTTPS em produção (Nginx), HSTS, cookies seguros.
- **Autenticação (M1):** JWT access curto + refresh com rotação e revogação; senhas com hash forte (Argon2/PBKDF2 do Django); verificação de e-mail e recuperação de senha.
- **Autorização (M1):** RBAC com papéis `CUSTOMER`, `MERCHANT_OWNER`, `MERCHANT_MANAGER`, `MERCHANT_OPERATOR`, `MODERATOR`, `SUPPORT`, `ADMIN`, `SUPERADMIN` e matriz de permissões documentada.
- **Abuso (M1):** rate limiting (Redis), proteção contra brute force, validação de entrada, CORS restrito, CSRF onde aplicável.
- **Segredos:** somente variáveis de ambiente; `.env` nunca versionado; produção injeta via orquestrador.
- **Uploads (M5):** limite de tamanho, validação MIME e extensão, armazenamento fora do webroot, URLs assinadas, antivírus quando necessário.
- **Logs:** estruturados, sem senha, token ou dados pessoais desnecessários.
- **Containers:** usuário não-root, imagem `prod` sem ferramentas de desenvolvimento, nenhuma ferramenta administrativa (ex.: Adminer) exposta em produção.
- **CI (M1):** lint, formato, testes, verificação de dependências e segredos, build. Testes críticos bloqueiam merge.
- **Backup:** PostgreSQL com restauração testada antes de qualquer deploy.
