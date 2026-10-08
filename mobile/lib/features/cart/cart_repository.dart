import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import 'cart.dart';

class CartRepository {
  CartRepository(this._api);

  final ApiClient _api;

  Future<Cart> _cart(Future<Response<Map<String, dynamic>>> request) async {
    try {
      return Cart.fromJson((await request).data!);
    } on DioException catch (error) {
      throw ApiClient.explain(error);
    }
  }

  Future<Cart> fetch() => _cart(_api.dio.get('/shopping-cart/'));

  Future<Cart> selectStore(String storeId) =>
      _cart(_api.dio.put('/shopping-cart/', data: {'store_id': storeId}));

  Future<Cart> setPayment(String payment) => _cart(
    _api.dio.put('/shopping-cart/', data: {'payment_condition': payment}),
  );

  Future<Cart> addItem(String variantId, {String quantity = '1'}) => _cart(
    _api.dio.post(
      '/shopping-cart/items/',
      data: {'variant_id': variantId, 'quantity': quantity},
    ),
  );

  Future<Cart> updateItem(String itemId, {String? quantity, bool? inBasket}) =>
      _cart(
        _api.dio.patch(
          '/shopping-cart/items/$itemId/',
          data: {'quantity': ?quantity, 'in_basket': ?inBasket},
        ),
      );

  Future<Cart> removeItem(String itemId) =>
      _cart(_api.dio.delete('/shopping-cart/items/$itemId/'));

  Future<Cart> importList(String listId) => _cart(
    _api.dio.post('/shopping-cart/import-list/', data: {'list_id': listId}),
  );

  /// Finishes the trip. Returns the cart as it was priced when closed.
  Future<Cart> close() => _cart(_api.dio.post('/shopping-cart/close/'));
}
