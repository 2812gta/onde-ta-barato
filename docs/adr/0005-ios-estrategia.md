# ADR 0005: Estratégia iOS

Status: **Parcialmente aceita**

Aceito: o app é concebido para Android e iOS; nenhum código ou plugin exclusivo de Android sem alternativa iOS; câmera, localização, OCR (ML Kit), voz e push (FCM/APNs) avaliados quanto ao suporte iOS. O MVP entrega Android.

Em aberto: compilar/assinar iOS exige macOS e conta Apple Developer (paga). Opções: Mac físico, runner macOS no GitHub Actions ou serviço como Codemagic. Não há Mac disponível nesta máquina (Windows).
