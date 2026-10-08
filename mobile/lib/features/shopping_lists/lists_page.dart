import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/widgets.dart';
import 'lists_controller.dart';
import 'shopping_list.dart';

Future<String?> askText(
  BuildContext context, {
  required String title,
  required String action,
}) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        maxLength: 100,
        textCapitalization: TextCapitalization.sentences,
        decoration: const InputDecoration(labelText: 'Nome da lista'),
        onSubmitted: (value) => Navigator.pop(context, value),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, controller.text),
          child: Text(action),
        ),
      ],
    ),
  );
}

class ListsPage extends ConsumerWidget {
  const ListsPage({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final name = await askText(context, title: 'Nova lista', action: 'Criar');
    if (name == null || name.trim().isEmpty || !context.mounted) return;
    final repository = ref.read(listsRepositoryProvider);
    ShoppingListDetail? created;
    final ok = await attempt(context, () async {
      created = await repository.create(name);
    });
    if (!ok || !context.mounted) return;
    ref.invalidate(listsProvider);
    context.push('/lists/${created!.id}');
  }

  Future<void> _delete(
    BuildContext context,
    WidgetRef ref,
    ListSummary list,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Excluir lista?'),
        content: Text('"${list.name}" e seus itens serão removidos.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Excluir'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final ok = await attempt(
      context,
      () => ref.read(listsRepositoryProvider).delete(list.id),
    );
    if (ok) ref.invalidate(listsProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lists = ref.watch(listsProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Minhas listas'),
        actions: const [LogoutButton()],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Nova lista'),
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(listsProvider.future),
        child: lists.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => ProblemView(
            error: error,
            onRetry: () => ref.invalidate(listsProvider),
          ),
          data: (items) => items.isEmpty
              ? const EmptyView(
                  icon: Icons.checklist_outlined,
                  text:
                      'Você ainda não tem listas. Crie uma e adicione produtos para saber onde comprar mais barato.',
                )
              : ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.only(bottom: 88),
                  itemCount: items.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (_, index) {
                    final list = items[index];
                    final count = list.itemCount;
                    return ListTile(
                      leading: const Icon(Icons.list_alt_outlined),
                      title: Text(list.name),
                      subtitle: Text(
                        count == 0
                            ? 'Vazia'
                            : '$count ${count == 1 ? 'item' : 'itens'} · ${list.checkedCount} marcados',
                      ),
                      trailing: PopupMenuButton<String>(
                        onSelected: (_) => _delete(context, ref, list),
                        itemBuilder: (_) => const [
                          PopupMenuItem(
                            value: 'delete',
                            child: Text('Excluir'),
                          ),
                        ],
                      ),
                      onTap: () => context.push('/lists/${list.id}'),
                    );
                  },
                ),
        ),
      ),
    );
  }
}
