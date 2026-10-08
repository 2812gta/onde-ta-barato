import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../stores/stores_controller.dart';
import 'product.dart';
import 'products_repository.dart';

final productsRepositoryProvider = Provider<ProductsRepository>(
  (ref) => ProductsRepository(ref.watch(apiClientProvider)),
);

class SearchQuery extends Notifier<String> {
  @override
  String build() => '';

  void set(String value) => state = value;
}

final searchQueryProvider = NotifierProvider<SearchQuery, String>(
  SearchQuery.new,
);

final productSearchProvider = FutureProvider.autoDispose<List<Variant>>(
  (ref) => ref
      .watch(productsRepositoryProvider)
      .search(ref.watch(searchQueryProvider)),
);

final variantProvider = FutureProvider.autoDispose.family<Variant, String>(
  (ref, id) => ref.watch(productsRepositoryProvider).byId(id),
);

/// The same radius the Stores tab uses, so both screens talk about the same area.
final comparisonProvider = FutureProvider.autoDispose
    .family<Comparison, String>((ref, variantId) async {
      final radius = ref.watch(radiusProvider);
      final position = await ref.read(locationServiceProvider).current();
      return ref
          .read(productsRepositoryProvider)
          .compare(
            variantId,
            lat: position.lat,
            lon: position.lon,
            radiusKm: radius,
          );
    });
