import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/widgets.dart';
import '../shopping_lists/lists_controller.dart';
import '../stores/stores_controller.dart';
import 'cart.dart';
import 'cart_controller.dart';

class CartPage extends ConsumerWidget {
  const CartPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Carrinho'),
        actions: const [LogoutButton()],
      ),
      body: cart.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => ProblemView(
          error: error,
          onRetry: () => ref.read(cartProvider.notifier).reload(),
        ),
        data: (data) => RefreshIndicator(
          onRefresh: () => ref.read(cartProvider.notifier).reload(),
          child: _CartBody(cart: data),
        ),
      ),
    );
  }
}

class _CartBody extends ConsumerWidget {
  const _CartBody({required this.cart});

  final Cart cart;

  Future<void> _pickStore(BuildContext context, WidgetRef ref) async {
    final storeId = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => const _StorePicker(),
    );
    if (storeId == null || !context.mounted) return;
    await attempt(
      context,
      () => ref.read(cartProvider.notifier).selectStore(storeId),
    );
  }

  Future<void> _finish(BuildContext context, WidgetRef ref) async {
    Cart? closed;
    final ok = await attempt(context, () async {
      closed = await ref.read(cartProvider.notifier).finish();
    });
    if (!ok || !context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Compra finalizada'),
        content: Text(
          'Total: ${formatMoney(closed!.totals.total)}'
          '${closed!.totals.hasSavings ? '\nVocê economizou ${formatMoney(closed!.totals.savings)}' : ''}'
          '\n\nOs preços podem divergir do caixa.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Ok'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Column(
      children: [
        Expanded(
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 16),
            children: [
              ListTile(
                leading: const Icon(Icons.storefront_outlined),
                title: Text(cart.store?.name ?? 'Escolher o mercado'),
                subtitle: Text(
                  cart.store == null
                      ? 'Os preços são calculados para o mercado escolhido.'
                      : 'Toque para trocar de mercado',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => _pickStore(context, ref),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Wrap(
                  spacing: 8,
                  children: [
                    for (final option in paymentOptions.entries)
                      ChoiceChip(
                        label: Text(option.value),
                        selected: cart.paymentCondition == option.key,
                        onSelected: (_) => attempt(
                          context,
                          () => ref
                              .read(cartProvider.notifier)
                              .setPayment(option.key),
                        ),
                      ),
                  ],
                ),
              ),
              const Divider(height: 24),
              if (cart.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(32),
                  child: Column(
                    children: [
                      Icon(Icons.shopping_cart_outlined, size: 48),
                      SizedBox(height: 16),
                      Text(
                        'Seu carrinho está vazio. Adicione produtos pela busca ou leve uma lista para cá.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                )
              else
                for (final line in cart.items)
                  _LineTile(line: line, storeChosen: cart.store != null),
            ],
          ),
        ),
        if (!cart.isEmpty)
          Material(
            elevation: 8,
            color: theme.colorScheme.surfaceContainer,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('Total', style: theme.textTheme.titleMedium),
                        const Spacer(),
                        Text(
                          formatMoney(cart.totals.total),
                          key: const Key('cart-total'),
                          style: theme.textTheme.headlineSmall,
                        ),
                      ],
                    ),
                    if (cart.totals.hasSavings)
                      Text(
                        'Você economiza ${formatMoney(cart.totals.savings)}',
                        style: TextStyle(color: theme.colorScheme.primary),
                      ),
                    if (cart.totals.hasUnconfirmedPotential)
                      Text(
                        'Economia possível de ${formatMoney(cart.totals.unconfirmedPotential)} '
                        'em promoção ainda não confirmada (não está no total).',
                        style: theme.textTheme.bodySmall,
                      ),
                    for (final warning in cart.warnings)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(warning, style: theme.textTheme.bodySmall),
                      ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: () => _finish(context, ref),
                        child: const Text('Finalizar compra'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _LineTile extends ConsumerWidget {
  const _LineTile({required this.line, required this.storeChosen});

  final CartLine line;

  /// Without a store nothing can be priced yet; say that instead of "no price here".
  final bool storeChosen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final notifier = ref.read(cartProvider.notifier);
    final details = <String>[
      if (line.priced)
        '${formatMoney(line.unitPrice)} × ${formatQuantity(line.quantity)}'
      else if (storeChosen)
        'Sem preço atual neste mercado'
      else
        'Escolha o mercado para ver o preço',
    ];
    return Dismissible(
      key: ValueKey(line.id),
      direction: DismissDirection.endToStart,
      background: Container(
        color: theme.colorScheme.errorContainer,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        child: const Icon(Icons.delete_outline),
      ),
      confirmDismiss: (_) => attempt(context, () => notifier.remove(line.id)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Checkbox(
              value: line.inBasket,
              onChanged: (value) => attempt(
                context,
                () => notifier.setInBasket(line.id, value ?? false),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      line.label,
                      style: line.inBasket
                          ? const TextStyle(
                              decoration: TextDecoration.lineThrough,
                            )
                          : null,
                    ),
                    if (line.brand != null)
                      Text(line.brand!, style: theme.textTheme.bodySmall),
                    Text(details.join(' · '), style: theme.textTheme.bodySmall),
                    Wrap(
                      spacing: 6,
                      children: [
                        if (line.promotion != null)
                          _Tag(
                            '${line.promotion} · economiza ${formatMoney(line.savings)}',
                            color: theme.colorScheme.primaryContainer,
                          ),
                        if (line.hasUnconfirmedPotential)
                          _Tag(
                            'Promoção não confirmada: ${formatMoney(line.unconfirmedPotential)}',
                            color: theme.colorScheme.surfaceContainerHighest,
                          ),
                        if (line.stale)
                          _Tag(
                            'Preço desatualizado',
                            color: theme.colorScheme.tertiaryContainer,
                          ),
                        if (line.conflict)
                          _Tag(
                            'Preços divergentes',
                            color: theme.colorScheme.tertiaryContainer,
                          ),
                      ],
                    ),
                    Row(
                      children: [
                        IconButton(
                          tooltip: 'Diminuir',
                          visualDensity: VisualDensity.compact,
                          icon: const Icon(Icons.remove_circle_outline),
                          onPressed: () => attempt(
                            context,
                            () => notifier.setQuantity(
                              line.id,
                              nextQuantity(line.quantity, -1),
                            ),
                          ),
                        ),
                        Text(formatQuantity(line.quantity)),
                        IconButton(
                          tooltip: 'Aumentar',
                          visualDensity: VisualDensity.compact,
                          icon: const Icon(Icons.add_circle_outline),
                          onPressed: () => attempt(
                            context,
                            () => notifier.setQuantity(
                              line.id,
                              nextQuantity(line.quantity, 1),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 12, 8, 0),
              child: Text(
                line.priced ? formatMoney(line.net) : '—',
                style: theme.textTheme.titleSmall,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text, {required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: Theme.of(context).textTheme.labelSmall),
    );
  }
}

class _StorePicker extends ConsumerWidget {
  const _StorePicker();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stores = ref.watch(nearbyStoresProvider);
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.7,
        ),
        child: stores.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(32),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (_, _) => const Padding(
            padding: EdgeInsets.all(32),
            child: Text(
              'Não foi possível carregar os mercados. Veja a aba Lojas.',
              textAlign: TextAlign.center,
            ),
          ),
          data: (list) => list.isEmpty
              ? const Padding(
                  padding: EdgeInsets.all(32),
                  child: Text(
                    'Nenhum mercado por perto. Aumente o raio na aba Lojas.',
                    textAlign: TextAlign.center,
                  ),
                )
              : ListView(
                  shrinkWrap: true,
                  children: [
                    for (final store in list)
                      ListTile(
                        leading: const Icon(Icons.storefront_outlined),
                        title: Text(store.name),
                        subtitle: Text(storeTypeLabel(store.type)),
                        trailing: Text(formatDistance(store.distanceMeters)),
                        onTap: () => Navigator.pop(context, store.id),
                      ),
                  ],
                ),
        ),
      ),
    );
  }
}
