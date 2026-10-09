import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/network/api_client.dart';
import '../../core/router.dart';
import '../auth/auth_controller.dart';
import 'location_service.dart';
import 'store.dart';
import 'stores_controller.dart';

class StoresPage extends ConsumerWidget {
  const StoresPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stores = ref.watch(nearbyStoresProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Lojas perto de você'),
        actions: [
          IconButton(
            tooltip: 'Sair',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: Column(
        children: [
          const _RadiusBar(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => ref.refresh(nearbyStoresProvider.future),
              child: stores.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (error, _) => _Problem(error: error),
                data: (list) => list.isEmpty
                    ? const _Empty()
                    : ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: list.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (_, index) =>
                            _StoreTile(store: list[index]),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RadiusBar extends ConsumerWidget {
  const _RadiusBar();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(radiusProvider);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          for (final km in radiusOptionsKm)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text('${km.toStringAsFixed(0)} km'),
                selected: km == selected,
                onSelected: (_) => ref.read(radiusProvider.notifier).select(km),
              ),
            ),
        ],
      ),
    );
  }
}

class _StoreTile extends StatelessWidget {
  const _StoreTile({required this.store});

  final Store store;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: theme.colorScheme.primaryContainer,
        child: Icon(
          Icons.storefront_outlined,
          color: theme.colorScheme.onPrimaryContainer,
        ),
      ),
      title: Row(
        children: [
          Flexible(child: Text(store.name, overflow: TextOverflow.ellipsis)),
          if (store.merchantVerified) ...[
            const SizedBox(width: 6),
            Tooltip(
              message: 'Comerciante verificado',
              child: Icon(
                Icons.verified,
                size: 18,
                color: theme.colorScheme.primary,
              ),
            ),
          ],
        ],
      ),
      subtitle: Text(
        [
          storeTypeLabel(store.type),
          store.place,
        ].where((s) => s.isNotEmpty).join(' · '),
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            formatDistance(store.distanceMeters),
            style: theme.textTheme.labelLarge,
          ),
          IconButton(
            tooltip: 'Fotografar um preço aqui',
            icon: const Icon(Icons.photo_camera_outlined),
            onPressed: () => context.push(Routes.contribute, extra: store),
          ),
        ],
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty();

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(32),
      children: const [
        SizedBox(height: 64),
        Icon(Icons.location_off_outlined, size: 48),
        SizedBox(height: 16),
        Text(
          'Não encontramos lojas neste raio. Tente aumentar a distância.',
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class _Problem extends ConsumerWidget {
  const _Problem({required this.error});

  final Object error;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = error is LocationFailure ? error as LocationFailure : null;
    final failure = error;
    final text =
        location?.message ??
        (failure is ApiException
            ? failure.message
            : 'Não foi possível carregar as lojas.');
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 64),
        Icon(
          location != null ? Icons.location_disabled : Icons.cloud_off_outlined,
          size: 48,
        ),
        const SizedBox(height: 16),
        Text(text, textAlign: TextAlign.center),
        const SizedBox(height: 24),
        if (location != null &&
            (location.problem == LocationProblem.deniedForever ||
                location.problem == LocationProblem.serviceOff))
          Center(
            child: FilledButton.tonal(
              onPressed: () => ref
                  .read(locationServiceProvider)
                  .openSettings(location.problem),
              child: const Text('Abrir configurações'),
            ),
          ),
        Center(
          child: TextButton(
            onPressed: () => ref.invalidate(nearbyStoresProvider),
            child: const Text('Tentar de novo'),
          ),
        ),
      ],
    );
  }
}
