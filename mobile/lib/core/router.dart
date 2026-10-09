import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/auth_controller.dart';
import '../features/auth/login_page.dart';
import '../features/cart/cart_controller.dart';
import '../features/cart/cart_page.dart';
import '../features/contributions/contribute_page.dart';
import '../features/products/product_page.dart';
import '../features/products/products_page.dart';
import '../features/shopping_lists/list_page.dart';
import '../features/shopping_lists/lists_page.dart';
import '../features/stores/store.dart';
import '../features/stores/stores_page.dart';

abstract final class Routes {
  static const splash = '/';
  static const login = '/login';
  static const stores = '/stores';
  static const contribute = '/stores/contribute';
  static const products = '/products';
  static const lists = '/lists';
  static const cart = '/cart';
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
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => MainShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.stores,
                builder: (_, _) => const StoresPage(),
                routes: [
                  GoRoute(
                    path: 'contribute',
                    // The store comes from the tile that was tapped; without it there is
                    // nothing to contribute to, so go back to the list.
                    redirect: (_, state) =>
                        state.extra is Store ? null : Routes.stores,
                    builder: (_, state) =>
                        ContributePage(store: state.extra! as Store),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.products,
                builder: (_, _) => const ProductsPage(),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (_, state) =>
                        ProductPage(variantId: state.pathParameters['id']!),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.lists,
                builder: (_, _) => const ListsPage(),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (_, state) =>
                        ListPage(listId: state.pathParameters['id']!),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(path: Routes.cart, builder: (_, _) => const CartPage()),
            ],
          ),
        ],
      ),
    ],
  );
});

/// The signed-in frame: one tab per branch, each keeping its own navigation stack.
class MainShell extends ConsumerWidget {
  const MainShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(cartProvider).value?.items.length ?? 0;
    return Scaffold(
      body: shell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: shell.currentIndex,
        onDestinationSelected: (index) =>
            shell.goBranch(index, initialLocation: index == shell.currentIndex),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.storefront_outlined),
            selectedIcon: Icon(Icons.storefront),
            label: 'Lojas',
          ),
          const NavigationDestination(
            icon: Icon(Icons.search),
            label: 'Produtos',
          ),
          const NavigationDestination(
            icon: Icon(Icons.checklist_outlined),
            selectedIcon: Icon(Icons.checklist),
            label: 'Listas',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: items > 0,
              label: Text('$items'),
              child: const Icon(Icons.shopping_cart_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: items > 0,
              label: Text('$items'),
              child: const Icon(Icons.shopping_cart),
            ),
            label: 'Carrinho',
          ),
        ],
      ),
    );
  }
}
