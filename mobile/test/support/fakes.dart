import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
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
