import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import 'contribution.dart';

class ContributionsRepository {
  ContributionsRepository(this._api);

  final ApiClient _api;

  Future<T> _call<T>(Future<T> Function() request) async {
    try {
      return await request();
    } on DioException catch (error) {
      throw ApiClient.explain(error);
    }
  }

  /// Sends the photo and the text read on the phone. Creates a draft, never a price.
  Future<Draft> createDraft({
    required String storeId,
    required String photoPath,
    required String ocrText,
    required DateTime capturedAt,
  }) => _call(() async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/contributions/',
      data: FormData.fromMap({
        'store_id': storeId,
        'photo': await MultipartFile.fromFile(photoPath, filename: 'tag.jpg'),
        'ocr_text': ocrText,
        'captured_at': capturedAt.toUtc().toIso8601String(),
      }),
    );
    return Draft.fromJson(response.data!);
  });

  /// The shopper's explicit confirmation, with the values they checked or corrected.
  /// The position only lets the server check the phone is near the store; it is not stored.
  Future<void> confirm(
    String draftId, {
    required String variantId,
    required String price,
    double? lat,
    double? lon,
  }) => _call(() async {
    await _api.dio.post<Map<String, dynamic>>(
      '/contributions/$draftId/confirm/',
      data: {'variant_id': variantId, 'price': price, 'lat': ?lat, 'lon': ?lon},
    );
  });

  Future<void> cancel(String draftId) => _call(() async {
    await _api.dio.post<Map<String, dynamic>>(
      '/contributions/$draftId/cancel/',
    );
  });
}
