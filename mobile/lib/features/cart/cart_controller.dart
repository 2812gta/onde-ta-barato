import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'cart.dart';
import 'cart_repository.dart';

final cartRepositoryProvider = Provider<CartRepository>(
  (ref) => CartRepository(ref.watch(apiClientProvider)),
);

/// The open cart, priced by the server on every change. Failures are thrown to the caller
/// (which words them for the shopper); the last good cart stays on screen meanwhile.
final cartProvider = AsyncNotifierProvider<CartController, Cart>(
  CartController.new,
);

class CartController extends AsyncNotifier<Cart> {
  CartRepository get _repository => ref.read(cartRepositoryProvider);

  @override
  Future<Cart> build() => _repository.fetch();

  Future<void> _apply(Future<Cart> Function() action) async {
    state = AsyncData(await action());
  }

  Future<void> selectStore(String storeId) =>
      _apply(() => _repository.selectStore(storeId));

  Future<void> setPayment(String payment) =>
      _apply(() => _repository.setPayment(payment));

  Future<void> addItem(String variantId, {String quantity = '1'}) =>
      _apply(() => _repository.addItem(variantId, quantity: quantity));

  Future<void> setQuantity(String itemId, String quantity) =>
      _apply(() => _repository.updateItem(itemId, quantity: quantity));

  Future<void> setInBasket(String itemId, bool inBasket) =>
      _apply(() => _repository.updateItem(itemId, inBasket: inBasket));

  Future<void> remove(String itemId) =>
      _apply(() => _repository.removeItem(itemId));

  Future<void> importList(String listId) =>
      _apply(() => _repository.importList(listId));

  /// Closes the trip and returns the final priced cart; the screen then starts empty.
  Future<Cart> finish() async {
    final closed = await _repository.close();
    state = AsyncData(await _repository.fetch());
    return closed;
  }

  Future<void> reload() async {
    state = await AsyncValue.guard(_repository.fetch);
  }
}
