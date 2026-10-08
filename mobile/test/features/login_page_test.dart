import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/core/network/api_client.dart';
import 'package:ondetabarato/core/storage/token_storage.dart';
import 'package:ondetabarato/features/auth/auth_controller.dart';
import 'package:ondetabarato/features/auth/auth_repository.dart';
import 'package:ondetabarato/features/auth/login_page.dart';

class FakeAuthRepository extends AuthRepository {
  FakeAuthRepository({this.failWith})
    : super(ApiClient(TokenStorage()), TokenStorage());

  final ApiException? failWith;
  final logins = <(String, String)>[];

  @override
  Future<bool> hasSession() async => false;

  @override
  Future<void> login({required String email, required String password}) async {
    logins.add((email, password));
    if (failWith != null) throw failWith!;
  }
}

Future<(FakeAuthRepository, ProviderContainer)> pumpLogin(
  WidgetTester tester, {
  ApiException? failWith,
}) async {
  final repository = FakeAuthRepository(failWith: failWith);
  final container = ProviderContainer(
    overrides: [authRepositoryProvider.overrideWithValue(repository)],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: LoginPage()),
    ),
  );
  await container.read(authControllerProvider.future);
  return (repository, container);
}

void main() {
  testWidgets('empty form shows what is missing and sends nothing', (
    tester,
  ) async {
    final (repository, _) = await pumpLogin(tester);

    await tester.tap(find.text('Entrar'));
    await tester.pump();

    expect(find.text('Informe seu e-mail.'), findsOneWidget);
    expect(find.text('Informe sua senha.'), findsOneWidget);
    expect(repository.logins, isEmpty);
  });

  testWidgets('an invalid e-mail is caught before the network', (tester) async {
    final (repository, _) = await pumpLogin(tester);

    await tester.enterText(find.byType(TextFormField).first, 'sem-arroba');
    await tester.enterText(find.byType(TextFormField).last, 'segredo');
    await tester.tap(find.text('Entrar'));
    await tester.pump();

    expect(find.text('E-mail inválido.'), findsOneWidget);
    expect(repository.logins, isEmpty);
  });

  testWidgets('signs in and marks the session as active', (tester) async {
    final (repository, container) = await pumpLogin(tester);

    await tester.enterText(find.byType(TextFormField).first, 'a@b.com');
    await tester.enterText(find.byType(TextFormField).last, 'segredo');
    await tester.tap(find.text('Entrar'));
    await tester.pump();

    expect(repository.logins.single, ('a@b.com', 'segredo'));
    expect(container.read(authControllerProvider).value, isTrue);
  });

  testWidgets('a refused login shows the server message and stays signed out', (
    tester,
  ) async {
    final (_, container) = await pumpLogin(
      tester,
      failWith: const ApiException('Credenciais inválidas.', statusCode: 401),
    );

    await tester.enterText(find.byType(TextFormField).first, 'a@b.com');
    await tester.enterText(find.byType(TextFormField).last, 'errada');
    await tester.tap(find.text('Entrar'));
    await tester.pump();

    expect(find.byKey(const Key('login-error')), findsOneWidget);
    expect(find.text('Credenciais inválidas.'), findsOneWidget);
    expect(container.read(authControllerProvider).value, isFalse);
  });

  testWidgets('the password can be revealed', (tester) async {
    await pumpLogin(tester);
    EditableText field() => tester.widget<EditableText>(
      find.descendant(
        of: find.byType(TextFormField).last,
        matching: find.byType(EditableText),
      ),
    );

    expect(field().obscureText, isTrue);
    await tester.tap(find.byTooltip('Mostrar senha'));
    await tester.pump();
    expect(field().obscureText, isFalse);
  });
}
