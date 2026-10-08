import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/auth_controller.dart';
import '../features/auth/login_page.dart';
import '../features/stores/stores_page.dart';

abstract final class Routes {
  static const splash = '/';
  static const login = '/login';
  static const stores = '/stores';
}

/// Lets GoRouter re-evaluate its redirect whenever the sign-in state changes.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(Ref ref) {
    ref.listen(authControllerProvider, (_, _) => notifyListeners());
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final listenable = _AuthListenable(ref);
  ref.onDispose(listenable.dispose);

  return GoRouter(
    initialLocation: Routes.splash,
    refreshListenable: listenable,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final here = state.matchedLocation;
      if (auth.isLoading) return here == Routes.splash ? null : Routes.splash;
      final signedIn = auth.value ?? false;
      if (!signedIn) return here == Routes.login ? null : Routes.login;
      return (here == Routes.login || here == Routes.splash)
          ? Routes.stores
          : null;
    },
    routes: [
      GoRoute(
        path: Routes.splash,
        builder: (_, _) =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
      ),
      GoRoute(path: Routes.login, builder: (_, _) => const LoginPage()),
      GoRoute(path: Routes.stores, builder: (_, _) => const StoresPage()),
    ],
  );
});
