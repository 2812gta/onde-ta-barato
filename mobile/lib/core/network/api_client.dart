import 'dart:async';

import 'package:dio/dio.dart';

import '../config.dart';
import '../storage/token_storage.dart';

/// A failure already worded for the shopper (Portuguese, no stack traces or server detail).
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

const _skipAuth = 'skipAuth';
const _retried = 'retried';

/// Dio wrapper: adds the bearer token and, on a 401, renews it once and repeats the request.
/// When renewing fails the session is over and [onSessionExpired] is called.
class ApiClient {
  ApiClient(this._tokens, {this.onSessionExpired, Dio? dio})
    : dio = dio ?? Dio() {
    this.dio.options
      ..baseUrl = AppConfig.apiBaseUrl
      ..connectTimeout = const Duration(seconds: 10)
      ..receiveTimeout = const Duration(seconds: 20)
      ..contentType = Headers.jsonContentType;
    this.dio.interceptors.add(
      InterceptorsWrapper(onRequest: _addToken, onError: _renewOnUnauthorized),
    );
  }

  final Dio dio;
  final TokenStorage _tokens;
  final void Function()? onSessionExpired;
  Future<bool>? _renewing; // one renewal at a time, shared by concurrent 401s

  Future<void> _addToken(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (options.extra[_skipAuth] != true) {
      final token = await _tokens.access;
      if (token != null) options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  Future<void> _renewOnUnauthorized(
    DioException error,
    ErrorInterceptorHandler handler,
  ) async {
    final request = error.requestOptions;
    final eligible =
        error.response?.statusCode == 401 &&
        request.extra[_skipAuth] != true &&
        request.extra[_retried] != true;
    if (!eligible) return handler.next(error);

    final renewed = await (_renewing ??= _renew().whenComplete(
      () => _renewing = null,
    ));
    if (!renewed) {
      onSessionExpired?.call();
      return handler.next(error);
    }
    try {
      request.extra[_retried] = true;
      handler.resolve(await dio.fetch<dynamic>(request));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  Future<bool> _renew() async {
    final refresh = await _tokens.refresh;
    if (refresh == null) return false;
    try {
      final response = await dio.post<Map<String, dynamic>>(
        '/auth/refresh/',
        data: {'refresh': refresh},
        options: Options(extra: {_skipAuth: true}),
      );
      final data = response.data!;
      await _tokens.save(
        access: data['access'] as String,
        refresh: (data['refresh'] as String?) ?? refresh,
      );
      return true;
    } on DioException {
      await _tokens.clear();
      return false;
    }
  }

  /// A request that must not carry (or renew) a token, such as the login itself.
  static Options get public => Options(extra: {_skipAuth: true});

  /// Turns any failure into a message safe to show.
  static ApiException explain(Object error) {
    if (error is ApiException) return error;
    if (error is DioException) {
      final status = error.response?.statusCode;
      switch (error.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.receiveTimeout:
        case DioExceptionType.sendTimeout:
          return const ApiException(
            'O servidor demorou a responder. Tente de novo.',
          );
        case DioExceptionType.connectionError:
          return const ApiException('Sem conexão com o servidor.');
        default:
          break;
      }
      if (status == 429) {
        return const ApiException(
          'Muitas tentativas. Aguarde um pouco e tente de novo.',
          statusCode: 429,
        );
      }
      if (status != null && status >= 500) {
        return ApiException(
          'Erro no servidor. Tente mais tarde.',
          statusCode: status,
        );
      }
      return ApiException(
        _detail(error.response?.data) ?? 'Não foi possível concluir.',
        statusCode: status,
      );
    }
    return const ApiException('Algo deu errado.');
  }

  static String? _detail(Object? body) {
    if (body is Map<String, dynamic>) {
      final detail = body['detail'];
      if (detail is String) return detail;
      for (final value in body.values) {
        if (value is List && value.isNotEmpty) return value.first.toString();
        if (value is String) return value;
      }
    }
    if (body is List && body.isNotEmpty) return body.first.toString();
    return null;
  }
}
