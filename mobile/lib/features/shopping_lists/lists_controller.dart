import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'lists_repository.dart';
import 'shopping_list.dart';

final listsRepositoryProvider = Provider<ListsRepository>(
  (ref) => ListsRepository(ref.watch(apiClientProvider)),
);

final listsProvider = FutureProvider.autoDispose<List<ListSummary>>(
  (ref) => ref.watch(listsRepositoryProvider).all(),
);

final listDetailProvider = FutureProvider.autoDispose
    .family<ShoppingListDetail, String>(
      (ref, id) => ref.watch(listsRepositoryProvider).detail(id),
    );

/// Quantity steps in the UI: whole units, never below 1.
String nextQuantity(String current, int delta) {
  final value = double.tryParse(current) ?? 1;
  final next = (value + delta).clamp(1, 1000).round();
  return '$next';
}
