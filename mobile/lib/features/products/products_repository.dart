import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import 'product.dart';

class ProductsRepository {
  ProductsRepository(this._api);

  final ApiClient _api;

  Future<T> _call<T>(Future<T> Function() request) async {
    try {
      return await request();
    } on DioException catch (error) {
      throw ApiClient.explain(error);
    }
  }

  Future<List<Variant>> search(String query) => _call(() async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/variants/',
      queryParameters: {if (query.trim().isNotEmpty) 'q': query.trim()},
    );
    return [
      for (final row in response.data!['results'] as List<dynamic>)
        Variant.fromJson(row as Map<String, dynamic>),
    ];
  });

  Future<Variant> byId(String id) => _call(() async {
    final response = await _api.dio.get<Map<String, dynamic>>('/variants/$id/');
    return Variant.fromJson(response.data!);
  });

  /// Where this presentation is cheapest nearby, ranked by price per unit.
  Future<Comparison> compare(
    String variantId, {
    required double lat,
    required double lon,
    required double radiusKm,
  }) => _call(() async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/variants/$variantId/compare/',
      data: {'lat': lat, 'lon': lon, 'radius_km': radiusKm},
    );
    return Comparison.fromJson(response.data!);
  });
}
