import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';

class AuthRepository {
  AuthRepository(this._api, this._tokens);

  final ApiClient _api;
  final TokenStorage _tokens;

  Future<bool> hasSession() async => (await _tokens.refresh) != null;

  Future<void> login({required String email, required String password}) async {
    try {
      final response = await _api.dio.post<Map<String, dynamic>>(
        '/auth/login/',
        data: {'email': email.trim().toLowerCase(), 'password': password},
        options: ApiClient.public,
      );
      final data = response.data!;
      await _tokens.save(
        access: data['access'] as String,
        refresh: data['refresh'] as String,
      );
    } on DioException catch (error) {
      throw ApiClient.explain(error);
    }
  }

  /// Ends the session here even if the server cannot be reached.
  Future<void> logout() async {
    final refresh = await _tokens.refresh;
    try {
      if (refresh != null) {
        await _api.dio.post<void>('/auth/logout/', data: {'refresh': refresh});
      }
    } on DioException {
      // Nothing to do: the local tokens are removed below either way.
    } finally {
      await _tokens.clear();
    }
  }
}
