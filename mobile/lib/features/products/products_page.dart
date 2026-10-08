import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/widgets.dart';
import 'product.dart';
import 'products_controller.dart';

class ProductsPage extends ConsumerStatefulWidget {
  const ProductsPage({super.key});

  @override
  ConsumerState<ProductsPage> createState() => _ProductsPageState();
}

class _ProductsPageState extends ConsumerState<ProductsPage> {
  final _controller = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    // Wait for a pause in typing: one request per search, not one per letter.
    _debounce = Timer(
      const Duration(milliseconds: 400),
      () => ref.read(searchQueryProvider.notifier).set(value),
    );
  }

  @override
  Widget build(BuildContext context) {
    final results = ref.watch(productSearchProvider);
    final query = ref.watch(searchQueryProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Produtos'),
        actions: const [LogoutButton()],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: SearchBar(
              controller: _controller,
              hintText: 'Buscar produto ou marca',
              leading: const Icon(Icons.search),
              onChanged: _onChanged,
              trailing: [
                if (_controller.text.isNotEmpty)
                  IconButton(
                    tooltip: 'Limpar',
                    icon: const Icon(Icons.close),
                    onPressed: () {
                      _controller.clear();
                      ref.read(searchQueryProvider.notifier).set('');
                      setState(() {});
                    },
                  ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => ref.refresh(productSearchProvider.future),
              child: results.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (error, _) => ProblemView(
                  error: error,
                  onRetry: () => ref.invalidate(productSearchProvider),
                ),
                data: (list) => list.isEmpty
                    ? EmptyView(
                        icon: Icons.search_off,
                        text: query.isEmpty
                            ? 'Nenhum produto cadastrado ainda.'
                            : 'Nenhum produto encontrado para "$query".',
                      )
                    : ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: list.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (_, index) => _VariantTile(list[index]),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _VariantTile extends StatelessWidget {
  const _VariantTile(this.variant);

  final Variant variant;

  @override
  Widget build(BuildContext context) {
    final size = formatSize(variant.quantity, variant.unit);
    return ListTile(
      title: Text(variant.name),
      subtitle: Text(
        [
          if (variant.brand != null) variant.brand!,
          if (variant.label.isNotEmpty) variant.label,
          size,
        ].join(' · '),
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => context.push('/products/${variant.id}'),
    );
  }
}
