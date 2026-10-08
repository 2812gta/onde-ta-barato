import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import 'shopping_list.dart';

class ListsRepository {
  ListsRepository(this._api);

  final ApiClient _api;

  Future<T> _call<T>(Future<T> Function() request) async {
    try {
      return await request();
    } on DioException catch (error) {
      throw ApiClient.explain(error);
    }
  }

  Future<List<ListSummary>> all() => _call(() async {
    final response = await _api.dio.get<List<dynamic>>('/shopping-lists/');
    return [
      for (final row in response.data ?? const <dynamic>[])
        ListSummary.fromJson(row as Map<String, dynamic>),
    ];
  });

  Future<ShoppingListDetail> detail(String id) => _call(() async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/shopping-lists/$id/',
    );
    return ShoppingListDetail.fromJson(response.data!);
  });

  Future<ShoppingListDetail> create(String name) => _call(() async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/shopping-lists/',
      data: {'name': name},
    );
    return ShoppingListDetail.fromJson(response.data!);
  });

  Future<void> delete(String id) =>
      _call(() => _api.dio.delete<void>('/shopping-lists/$id/'));

  Future<void> addItem(
    String listId,
    String variantId, {
    String quantity = '1',
  }) => _call(
    () => _api.dio.post<void>(
      '/shopping-lists/$listId/items/',
      data: {'variant_id': variantId, 'quantity': quantity},
    ),
  );

  Future<void> updateItem(
    String listId,
    String itemId, {
    String? quantity,
    bool? checked,
  }) => _call(
    () => _api.dio.patch<void>(
      '/shopping-lists/$listId/items/$itemId/',
      data: {'quantity': ?quantity, 'checked': ?checked},
    ),
  );

  Future<void> removeItem(String listId, String itemId) => _call(
    () => _api.dio.delete<void>('/shopping-lists/$listId/items/$itemId/'),
  );
}
