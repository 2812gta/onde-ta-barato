# OndeTáBarato (app Flutter)

Android no MVP; o código evita dependências exclusivas de Android para preparar o iOS (ADR 0005).

Stack (docs/ARCHITECTURE.md): Riverpod, GoRouter, Dio, `flutter_secure_storage` e `geolocator`. Estrutura por feature:

```text
lib/
  core/       config, rede (Dio + renovação do token), armazenamento seguro, rotas, tema
  features/
    auth/            login, estado da sessão
    stores/          lojas próximas (aba Lojas)
    products/        busca e comparação de preços por unidade (aba Produtos)
    shopping_lists/  listas de compras (aba Listas)
    cart/            carrinho calculado no servidor (aba Carrinho)
```

Regras que a interface segue (ADR 0012 e docs/USER_TRUST.md):

- Dinheiro é sempre o **texto decimal** que o servidor enviou (`"24.00"`), nunca `double`. O app só formata.
- O total do carrinho vem do servidor, a cada alteração. O app não soma preços.
- Preço desatualizado, divergente ou sem valor é **sinalizado**, nunca escondido. Promoção de comerciante não verificado aparece como "não confirmada" e fica fora do total.
- O selo "Menor preço encontrado na nossa base" só aparece quando o servidor o envia.

## Rodar no celular por cabo USB

Pré-requisitos: depuração USB ativa e autorizada (`adb devices` mostra `device`), API em `localhost:8001` e o banco no ar.

```powershell
adb reverse tcp:8001 tcp:8001      # o celular enxerga a API do notebook como localhost:8001
cd mobile
flutter run -d <id-do-aparelho>
```

Os dados de demonstração ficam em Fortaleza. Para não depender do GPS durante o desenvolvimento:

```powershell
flutter run -d <id> --dart-define=DEMO_LAT=-3.7385 --dart-define=DEMO_LON=-38.4965
```

Login de teste: qualquer usuário criado por `manage.py seed_demo` (ex.: `cliente1@demo.ondetabarato.invalid`).

Outra API: `--dart-define=API_BASE_URL=https://.../api/v1`.

## Segurança

- Os tokens ficam no armazenamento criptografado da plataforma, nunca em preferências simples.
- HTTP sem TLS só é permitido no build **debug** (`android/app/src/debug/AndroidManifest.xml`); o release mantém o bloqueio padrão do Android.
- A localização vai no corpo da requisição (nunca na URL) e não é guardada pelo app.
- O login e o 401 nunca exibem detalhes técnicos do servidor.

## Testes

```powershell
flutter analyze
flutter test
```
