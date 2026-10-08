import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/core/network/api_client.dart';
import 'package:ondetabarato/core/storage/token_storage.dart';

class MemoryTokens implements TokenStorage {
  MemoryTokens({this.currentAccess, this.currentRefresh});

  String? currentAccess;
  String? currentRefresh;

  @override
  Future<String?> get access async => currentAccess;
  @override
  Future<String?> get refresh async => currentRefresh;
  @override
  Future<void> save({required String access, required String refresh}) async {
    currentAccess = access;
    currentRefresh = refresh;
  }

  @override
  Future<void> clear() async {
    currentAccess = null;
    currentRefresh = null;
  }
}

/// A scripted server: answers by request and records what it saw.
class FakeServer implements HttpClientAdapter {
  FakeServer(this.handler);

  final ResponseBody Function(RequestOptions options) handler;
  final seen = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    seen.add(options);
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody reply(int status, Object body) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: ['application/json'],
  },
);

ApiClient clientFor(
  FakeServer server,
  TokenStorage tokens, {
  void Function()? onSessionExpired,
}) => ApiClient(
  tokens,
  onSessionExpired: onSessionExpired,
  dio: Dio()..httpClientAdapter = server,
);

void main() {
  test('adds the bearer token to requests', () async {
    final server = FakeServer((_) => reply(200, {'ok': true}));
    final client = clientFor(
      server,
      MemoryTokens(currentAccess: 'A1', currentRefresh: 'R1'),
    );

    await client.dio.get<dynamic>('/stores/x/');

    expect(server.seen.single.headers['Authorization'], 'Bearer A1');
  });

  test('public requests carry no token', () async {
    final server = FakeServer((_) => reply(200, {}));
    final client = clientFor(
      server,
      MemoryTokens(currentAccess: 'A1', currentRefresh: 'R1'),
    );

    await client.dio.post<dynamic>('/auth/login/', options: ApiClient.public);

    expect(server.seen.single.headers.containsKey('Authorization'), isFalse);
  });

  test('a 401 renews the token once and repeats the request', () async {
    final tokens = MemoryTokens(currentAccess: 'OLD', currentRefresh: 'R1');
    final server = FakeServer((options) {
      if (options.path == '/auth/refresh/') {
        return reply(200, {'access': 'NEW', 'refresh': 'R2'});
      }
      return options.headers['Authorization'] == 'Bearer NEW'
          ? reply(200, {'ok': true})
          : reply(401, {'detail': 'expired'});
    });
    var expired = false;
    final client = clientFor(
      server,
      tokens,
      onSessionExpired: () => expired = true,
    );

    final response = await client.dio.get<dynamic>('/shopping-lists/');

    expect(response.statusCode, 200);
    expect(await tokens.access, 'NEW');
    expect(
      await tokens.refresh,
      'R2',
    ); // the rotated token replaces the old one
    expect(expired, isFalse);
    expect(server.seen.map((r) => r.path), [
      '/shopping-lists/',
      '/auth/refresh/',
      '/shopping-lists/',
    ]);
  });

  test('concurrent 401s share one renewal', () async {
    final tokens = MemoryTokens(currentAccess: 'OLD', currentRefresh: 'R1');
    final server = FakeServer((options) {
      if (options.path == '/auth/refresh/') {
        return reply(200, {'access': 'NEW', 'refresh': 'R2'});
      }
      return options.headers['Authorization'] == 'Bearer NEW'
          ? reply(200, {})
          : reply(401, {'detail': 'expired'});
    });
    final client = clientFor(server, tokens);

    await Future.wait([
      client.dio.get<dynamic>('/a/'),
      client.dio.get<dynamic>('/b/'),
      client.dio.get<dynamic>('/c/'),
    ]);

    // The server rotates the refresh token: a second renewal would use a dead one.
    expect(server.seen.where((r) => r.path == '/auth/refresh/'), hasLength(1));
  });

  test('a failed renewal ends the session and clears the tokens', () async {
    final tokens = MemoryTokens(currentAccess: 'OLD', currentRefresh: 'DEAD');
    final server = FakeServer((_) => reply(401, {'detail': 'no'}));
    var expired = false;
    final client = clientFor(
      server,
      tokens,
      onSessionExpired: () => expired = true,
    );

    await expectLater(
      client.dio.get<dynamic>('/shopping-lists/'),
      throwsA(isA<DioException>()),
    );

    expect(expired, isTrue);
    expect(await tokens.access, isNull);
    expect(await tokens.refresh, isNull);
  });

  test('a request is retried only once', () async {
    final tokens = MemoryTokens(currentAccess: 'OLD', currentRefresh: 'R1');
    final server = FakeServer((options) {
      if (options.path == '/auth/refresh/') {
        return reply(200, {'access': 'NEW', 'refresh': 'R2'});
      }
      return reply(401, {'detail': 'still no'}); // e.g. the account was blocked
    });
    final client = clientFor(server, tokens);

    await expectLater(
      client.dio.get<dynamic>('/x/'),
      throwsA(isA<DioException>()),
    );

    expect(server.seen.map((r) => r.path), ['/x/', '/auth/refresh/', '/x/']);
  });

  group('explain', () {
    DioException failure(
      DioExceptionType type, [
      Response<dynamic>? response,
    ]) => DioException(
      requestOptions: RequestOptions(path: '/x'),
      type: type,
      response: response,
    );

    Response<dynamic> answer(int status, Object? data) => Response<dynamic>(
      requestOptions: RequestOptions(path: '/x'),
      statusCode: status,
      data: data,
    );

    test('no connection and timeouts', () {
      expect(
        ApiClient.explain(failure(DioExceptionType.connectionError)).message,
        'Sem conexão com o servidor.',
      );
      expect(
        ApiClient.explain(failure(DioExceptionType.receiveTimeout)).message,
        contains('demorou'),
      );
    });

    test('shows the API detail, never a stack trace', () {
      final error = failure(
        DioExceptionType.badResponse,
        answer(401, {'detail': 'Credenciais inválidas.'}),
      );
      expect(ApiClient.explain(error).message, 'Credenciais inválidas.');
    });

    test('field errors and plain lists', () {
      expect(
        ApiClient.explain(
          failure(
            DioExceptionType.badResponse,
            answer(400, {
              'quantity': ['Quantidade inválida.'],
            }),
          ),
        ).message,
        'Quantidade inválida.',
      );
      expect(
        ApiClient.explain(
          failure(
            DioExceptionType.badResponse,
            answer(400, ['Carrinho vazio.']),
          ),
        ).message,
        'Carrinho vazio.',
      );
    });

    test('rate limit and server errors get their own wording', () {
      expect(
        ApiClient.explain(
          failure(DioExceptionType.badResponse, answer(429, {'detail': 'x'})),
        ).message,
        contains('Muitas tentativas'),
      );
      expect(
        ApiClient.explain(
          failure(
            DioExceptionType.badResponse,
            answer(500, '<html>boom</html>'),
          ),
        ).message,
        'Erro no servidor. Tente mais tarde.',
      );
    });
  });
}
