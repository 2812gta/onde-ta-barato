# API

- Prefixo: `/api/v1/`, organizada por domínio (auth, stores, products, prices, ...).
- Documentação: OpenAPI gerada automaticamente, Swagger UI e Redoc (M1).
- Autenticação: JWT Bearer.
- Versionamento: mudanças incompatíveis exigem nova versão. Aplicativos instalados antigos continuam funcionando durante um período de depreciação anunciado em `CHANGELOG`; o app consulta uma versão mínima suportada.
- Erros em formato consistente; paginação por cursor nas listagens grandes.
- Toda resposta com preço inclui: valor, fonte, data de coleta, condição de pagamento, status e confiança.

Endpoints serão documentados a partir do M1.
