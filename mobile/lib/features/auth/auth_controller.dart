import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'auth_repository.dart';

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(apiClientProvider),
    ref.watch(tokenStorageProvider),
  ),
);

/// Whether a shopper is signed in. Loading while the stored session is checked at start-up.
final authControllerProvider = AsyncNotifierProvider<AuthController, bool>(
  AuthController.new,
);

class AuthController extends AsyncNotifier<bool> {
  @override
  Future<bool> build() => ref.read(authRepositoryProvider).hasSession();

  Future<void> login({required String email, required String password}) async {
    await ref
        .read(authRepositoryProvider)
        .login(email: email, password: password);
    state = const AsyncData(true);
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AsyncData(false);
  }

  /// The server refused to renew the session: back to the login screen.
  void expire() => state = const AsyncData(false);
}
