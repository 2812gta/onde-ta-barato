import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/network/api_client.dart';
import '../../core/widgets.dart';
import '../cart/cart_controller.dart';
import '../shopping_lists/lists_controller.dart';
import '../shopping_lists/lists_page.dart';
import '../shopping_lists/shopping_list.dart';
import '../stores/location_service.dart';
import '../stores/stores_controller.dart';
import 'product.dart';
import 'products_controller.dart';

class ProductPage extends ConsumerWidget {
  const ProductPage({super.key, required this.variantId});

  final String variantId;

  Future<void> _addToList(BuildContext context, WidgetRef ref) async {
    final listId = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => const _ListPicker(),
    );
    if (listId == null || !context.mounted) return;
    var target = listId;
    if (listId == _ListPicker.newList) {
      final name = await askText(context, title: 'Nova lista', action: 'Criar');
      if (name == null || name.trim().isEmpty || !context.mounted) return;
      String? created;
      final ok = await attempt(context, () async {
        created = (await ref.read(listsRepositoryProvider).create(name)).id;
      });
      if (!ok || !context.mounted) return;
      target = created!;
    }
    final ok = await attempt(
      context,
      () => ref.read(listsRepositoryProvider).addItem(target, variantId),
    );
    if (ok && context.mounted) {
      ref.invalidate(listsProvider);
      notify(context, 'Adicionado à lista.');
    }
  }

  Future<void> _addToCart(BuildContext context, WidgetRef ref) async {
    final ok = await attempt(
      context,
      () => ref.read(cartProvider.notifier).addItem(variantId),
    );
    if (ok && context.mounted) notify(context, 'Adicionado ao carrinho.');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final variant = ref.watch(variantProvider(variantId));
    final comparison = ref.watch(comparisonProvider(variantId));
    return Scaffold(
      appBar: AppBar(title: const Text('Produto')),
      body: variant.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => ProblemView(
          error: error,
          onRetry: () => ref.invalidate(variantProvider(variantId)),
        ),
        data: (v) => RefreshIndicator(
          onRefresh: () => ref.refresh(comparisonProvider(variantId).future),
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              _Header(variant: v),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _addToList(context, ref),
                        icon: const Icon(Icons.playlist_add),
                        label: const Text('À lista'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: () => _addToCart(context, ref),
                        icon: const Icon(Icons.add_shopping_cart),
                        label: const Text('Ao carrinho'),
                      ),
                    ),
                  ],
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 24, 16, 4),
                child: _SectionTitle('Onde está mais barato'),
              ),
              comparison.when(
                loading: () => const Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (error, _) => _ComparisonProblem(
                  error: error,
                  onRetry: () => ref.invalidate(comparisonProvider(variantId)),
                ),
                data: (data) => _ComparisonView(comparison: data),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) =>
      Text(text, style: Theme.of(context).textTheme.titleMedium);
}

class _Header extends StatelessWidget {
  const _Header({required this.variant});

  final Variant variant;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(variant.name, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text(
            [
              if (variant.brand != null) variant.brand!,
              if (variant.label.isNotEmpty) variant.label,
              formatSize(variant.quantity, variant.unit),
            ].join(' · '),
            style: theme.textTheme.bodyLarge,
          ),
        ],
      ),
    );
  }
}

class _ComparisonProblem extends ConsumerWidget {
  const _ComparisonProblem({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final failure = error;
    final location = failure is LocationFailure ? failure : null;
    final text =
        location?.message ??
        (failure is ApiException
            ? failure.message
            : 'Não foi possível comparar os preços agora.');
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Text(text, textAlign: TextAlign.center),
          if (location != null &&
              (location.problem == LocationProblem.deniedForever ||
                  location.problem == LocationProblem.serviceOff))
            TextButton(
              onPressed: () => ref
                  .read(locationServiceProvider)
                  .openSettings(location.problem),
              child: const Text('Abrir configurações'),
            ),
          TextButton(onPressed: onRetry, child: const Text('Tentar de novo')),
        ],
      ),
    );
  }
}

class _ComparisonView extends StatelessWidget {
  const _ComparisonView({required this.comparison});

  final Comparison comparison;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (comparison.label != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Chip(
              avatar: const Icon(Icons.local_offer_outlined, size: 18),
              label: Text(comparison.label!),
            ),
          ),
        for (final quote in comparison.results) _QuoteTile(quote: quote),
        for (final note in comparison.notes)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text(note, style: theme.textTheme.bodySmall),
          ),
      ],
    );
  }
}

String confidenceLabel(double score) =>
    score >= 0.65 ? 'alta' : (score >= 0.35 ? 'média' : 'baixa');

String ageLabel(double hours) {
  if (hours < 1) return 'agora há pouco';
  if (hours < 48) return 'há ${hours.round()} h';
  return 'há ${(hours / 24).round()} dias';
}

class _QuoteTile extends StatelessWidget {
  const _QuoteTile({required this.quote});

  final StoreQuote quote;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final details = <String>[
      formatDistance(quote.distanceMeters),
      'atualizado ${ageLabel(quote.ageHours)}',
      'confiança ${confidenceLabel(quote.confidence)}',
    ].where((s) => s.isNotEmpty).join(' · ');
    return ListTile(
      leading: CircleAvatar(
        radius: 16,
        backgroundColor: quote.rank == 1
            ? theme.colorScheme.primary
            : theme.colorScheme.surfaceContainerHighest,
        foregroundColor: quote.rank == 1
            ? theme.colorScheme.onPrimary
            : theme.colorScheme.onSurface,
        child: Text('${quote.rank}'),
      ),
      title: Row(
        children: [
          Flexible(
            child: Text(quote.storeName, overflow: TextOverflow.ellipsis),
          ),
          if (quote.merchantVerified) ...[
            const SizedBox(width: 6),
            Icon(Icons.verified, size: 16, color: theme.colorScheme.primary),
          ],
        ],
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(details),
          if (quote.stale)
            Text(
              'Preço desatualizado: confirme no local.',
              style: TextStyle(color: theme.colorScheme.tertiary),
            ),
          if (quote.conflict && quote.priceRange != null)
            Text(
              'Fontes divergem: ${formatMoney(quote.priceRange!.$1)} a ${formatMoney(quote.priceRange!.$2)}.',
              style: TextStyle(color: theme.colorScheme.tertiary),
            ),
        ],
      ),
      isThreeLine: quote.stale || quote.conflict,
      trailing: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(formatMoney(quote.price), style: theme.textTheme.titleMedium),
          Text(quote.unitPriceText, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _ListPicker extends ConsumerWidget {
  const _ListPicker();

  static const newList = '__new__';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lists = ref.watch(listsProvider);
    return SafeArea(
      child: lists.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(32),
          child: Center(child: CircularProgressIndicator()),
        ),
        error: (_, _) => const Padding(
          padding: EdgeInsets.all(32),
          child: Text('Não foi possível carregar suas listas.'),
        ),
        data: (items) => ListView(
          shrinkWrap: true,
          children: [
            ListTile(
              leading: const Icon(Icons.add),
              title: const Text('Nova lista'),
              onTap: () => Navigator.pop(context, newList),
            ),
            for (final ListSummary list in items)
              ListTile(
                leading: const Icon(Icons.list_alt_outlined),
                title: Text(list.name),
                subtitle: Text('${list.itemCount} itens'),
                onTap: () => Navigator.pop(context, list.id),
              ),
          ],
        ),
      ),
    );
  }
}
