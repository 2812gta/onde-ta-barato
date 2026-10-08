import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import 'store.dart';

class StoresRepository {
  StoresRepository(this._api);

  final ApiClient _api;

  /// Nearby stores, closest first. The position travels in the body, never in the URL.
  Future<List<Store>> nearby({
    required double lat,
    required double lon,
    required double radiusKm,
  }) async {
    try {
      final response = await _api.dio.post<List<dynamic>>(
        '/stores/search/',
        data: {'lat': lat, 'lon': lon, 'radius_km': radiusKm},
      );
      return [
        for (final item in response.data ?? const <dynamic>[])
          Store.fromJson(item as Map<String, dynamic>),
      ];
    } on DioException catch (error) {
      throw ApiClient.explain(error);
    }
  }
}
