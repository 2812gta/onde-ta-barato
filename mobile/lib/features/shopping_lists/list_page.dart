import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/widgets.dart';
import '../cart/cart_controller.dart';
import 'lists_controller.dart';
import 'shopping_list.dart';

class ListPage extends ConsumerWidget {
  const ListPage({super.key, required this.listId});

  final String listId;

  Future<void> _toCart(BuildContext context, WidgetRef ref) async {
    final ok = await attempt(
      context,
      () => ref.read(cartProvider.notifier).importList(listId),
    );
    if (ok && context.mounted) {
      notify(context, 'Itens levados para o carrinho.');
      context.go('/cart');
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(listDetailProvider(listId));
    final repository = ref.read(listsRepositoryProvider);

    Future<void> change(Future<void> Function() action) async {
      final ok = await attempt(context, action);
      if (ok) {
        ref.invalidate(listDetailProvider(listId));
        ref.invalidate(listsProvider);
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(detail.value?.name ?? 'Lista'),
        actions: [
          if (detail.value?.items.isNotEmpty ?? false)
            TextButton.icon(
              onPressed: () => _toCart(context, ref),
              icon: const Icon(Icons.shopping_cart_checkout),
              label: const Text('Ao carrinho'),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(listDetailProvider(listId).future),
        child: detail.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => ProblemView(
            error: error,
            onRetry: () => ref.invalidate(listDetailProvider(listId)),
          ),
          data: (list) => list.items.isEmpty
              ? const EmptyView(
                  icon: Icons.add_shopping_cart_outlined,
                  text:
                      'Lista vazia. Busque um produto na aba Produtos e toque em "Adicionar à lista".',
                )
              : ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  itemCount: list.items.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (_, index) {
                    final item = list.items[index];
                    return _ItemTile(
                      item: item,
                      onChecked: (value) => change(
                        () => repository.updateItem(
                          listId,
                          item.id,
                          checked: value,
                        ),
                      ),
                      onQuantity: (delta) => change(
                        () => repository.updateItem(
                          listId,
                          item.id,
                          quantity: nextQuantity(item.quantity, delta),
                        ),
                      ),
                      onRemove: () =>
                          change(() => repository.removeItem(listId, item.id)),
                    );
                  },
                ),
        ),
      ),
    );
  }
}

class _ItemTile extends StatelessWidget {
  const _ItemTile({
    required this.item,
    required this.onChecked,
    required this.onQuantity,
    required this.onRemove,
  });

  final ListItem item;
  final ValueChanged<bool> onChecked;
  final ValueChanged<int> onQuantity;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Checkbox(
        value: item.checked,
        onChanged: (value) => onChecked(value ?? false),
      ),
      title: Text(
        item.label,
        style: item.checked
            ? const TextStyle(decoration: TextDecoration.lineThrough)
            : null,
      ),
      subtitle: item.brand == null ? null : Text(item.brand!),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: 'Diminuir',
            icon: const Icon(Icons.remove_circle_outline),
            onPressed: () => onQuantity(-1),
          ),
          Text(formatQuantity(item.quantity)),
          IconButton(
            tooltip: 'Aumentar',
            icon: const Icon(Icons.add_circle_outline),
            onPressed: () => onQuantity(1),
          ),
          IconButton(
            tooltip: 'Remover',
            icon: const Icon(Icons.delete_outline),
            onPressed: onRemove,
          ),
        ],
      ),
    );
  }
}
