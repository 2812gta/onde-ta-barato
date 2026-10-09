import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/core/network/api_client.dart';
import 'package:ondetabarato/core/storage/token_storage.dart';
import 'package:ondetabarato/features/contributions/capture.dart';
import 'package:ondetabarato/features/contributions/contribute_page.dart';
import 'package:ondetabarato/features/contributions/contribution.dart';
import 'package:ondetabarato/features/contributions/contributions_controller.dart';
import 'package:ondetabarato/features/contributions/contributions_repository.dart';
import 'package:ondetabarato/features/stores/location_service.dart';
import 'package:ondetabarato/features/stores/store.dart';
import 'package:ondetabarato/features/stores/stores_controller.dart';

import '../support/fakes.dart';

Map<String, dynamic> variantJson(String id, String name) => {
  'id': id,
  'name': name,
  'brand': 'Tio João',
  'label': '',
  'quantity': '5.000',
  'unit': 'kg',
};

Map<String, dynamic> draftJson({
  List<Map<String, dynamic>>? prices,
  List<Map<String, dynamic>>? variants,
}) => {
  'id': 'draft-1',
  'status': 'DRAFT',
  'reading': {
    'prices':
        prices ??
        [
          {
            'value': '24.90',
            'raw': 'R\$ 24,90',
            'line': 1,
            'has_currency': true,
            'origin': 'FACT',
          },
        ],
    'gtins': [],
    'name_lines': ['ARROZ'],
    'note': 'sugestão',
  },
  'suggested_variants':
      variants ??
      [
        {
          ...variantJson('v1', 'Arroz Branco'),
          'basis': 'TEXT',
          'origin': 'INFERENCE',
        },
      ],
};

const store = Store(
  id: 's1',
  name: 'Mercantil Teste',
  type: 'SUPERMARKET',
  neighborhood: 'Centro',
  city: 'Fortaleza',
  distanceMeters: 100,
  merchantVerified: false,
);

void main() {
  group('parsePrice', () {
    test('accepts what a shopper types', () {
      expect(parsePrice('24,90'), '24.90');
      expect(parsePrice('24.90'), '24.90');
      expect(parsePrice(' R\$ 1.249,90 '), '1249.90');
      expect(parsePrice('5'), '5.00');
      expect(parsePrice('7,5'), '7.50');
    });

    test('refuses what is not a usable price', () {
      for (final bad in [
        '',
        'abc',
        '0',
        '0,00',
        '-3',
        '1,234',
        '123456',
        '2,5,1',
      ]) {
        expect(parsePrice(bad), isNull, reason: bad);
      }
    });
  });

  group('Draft', () {
    test('keeps what was read apart from what was inferred', () {
      final draft = Draft.fromJson(
        draftJson(
          variants: [
            {...variantJson('v1', 'Arroz'), 'basis': 'GTIN', 'origin': 'FACT'},
            {
              ...variantJson('v2', 'Feijão'),
              'basis': 'TEXT',
              'origin': 'INFERENCE',
            },
          ],
        ),
      );
      expect(draft.prices.single.value, '24.90');
      expect(draft.suggestions[0].byBarcode, isTrue);
      expect(draft.suggestions[0].origin, Origin.fact);
      expect(draft.suggestions[1].byBarcode, isFalse);
      expect(draft.suggestions[1].origin, Origin.inference);
    });

    test('an unknown origin is treated as an inference, never a fact', () {
      expect(Origin.parse(null), Origin.inference);
      expect(Origin.parse('WHATEVER'), Origin.inference);
    });
  });

  group('ContributionsRepository', () {
    test('sends the draft as multipart and the confirmation as json', () async {
      final server = FakeServer((options) {
        if (options.path.endsWith('/confirm/')) return reply(201, {});
        return reply(201, draftJson());
      });
      final repository = ContributionsRepository(
        clientFor(server, MemoryTokens()),
      );
      // Any existing file works as the photo.
      final photo = 'pubspec.yaml';
      final draft = await repository.createDraft(
        storeId: 's1',
        photoPath: photo,
        ocrText: 'ARROZ\nR\$ 24,90',
        capturedAt: DateTime.utc(2026, 10, 8, 12),
      );
      await repository.confirm(
        draft.id,
        variantId: 'v1',
        price: '24.90',
        lat: -3.8,
        lon: -38.6,
      );

      expect(draft.id, 'draft-1');
      final create = server.seen[0];
      expect(create.path, endsWith('/contributions/'));
      expect(create.data, isA<FormData>());
      final fields = {
        for (final f in (create.data as FormData).fields) f.key: f.value,
      };
      expect(fields['store_id'], 's1');
      expect(fields['ocr_text'], 'ARROZ\nR\$ 24,90');
      expect(fields['captured_at'], '2026-10-08T12:00:00.000Z');
      final confirm = server.seen[1];
      expect(confirm.path, endsWith('/contributions/draft-1/confirm/'));
      expect(confirm.data, {
        'variant_id': 'v1',
        'price': '24.90',
        'lat': -3.8,
        'lon': -38.6,
      });
    });

    test('confirming without a position sends no coordinates', () async {
      final server = FakeServer((_) => reply(201, {}));
      await ContributionsRepository(
        clientFor(server, MemoryTokens()),
      ).confirm('d', variantId: 'v1', price: '1.00');
      expect((server.seen.single.data as Map).keys, ['variant_id', 'price']);
    });

    test('a server refusal becomes a worded message', () async {
      final server = FakeServer(
        (_) => reply(400, {'detail': 'Você tem contribuições esperando.'}),
      );
      final repository = ContributionsRepository(
        clientFor(server, MemoryTokens()),
      );
      await expectLater(repository.cancel('d'), throwsA(isA<ApiException>()));
    });
  });

  group('ContributePage', () {
    testWidgets('photo, check and confirm sends the shopper\'s values', (
      tester,
    ) async {
      final rig = await pump(tester);
      expect(find.text('Tirar foto da etiqueta'), findsOneWidget);

      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      expect(find.text('Confira o que lemos'), findsOneWidget);
      expect(
        find.textContaining('R\$ 24,90 · lido na etiqueta'),
        findsOneWidget,
      );
      expect(find.text('Sugestão pelo nome (confira)'), findsOneWidget);
      expect(find.widgetWithText(TextField, '24,90'), findsOneWidget);

      await tester.tap(find.text('Confirmar e enviar'));
      await tester.pumpAndSettle();

      expect(rig.repository.confirmed, [('draft-1', 'v1', '24.90')]);
      expect(rig.repository.cancelled, isEmpty);
      expect(find.text('Obrigado! Seu preço foi enviado.'), findsOneWidget);
    });

    testWidgets('a corrected price is what gets sent, not the reading', (
      tester,
    ) async {
      final rig = await pump(tester);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '23,50');
      await tester.pump();
      await tester.tap(find.text('Confirmar e enviar'));
      await tester.pumpAndSettle();

      expect(rig.repository.confirmed.single.$3, '23.50');
    });

    testWidgets('an unusable price blocks the confirmation', (tester) async {
      final rig = await pump(tester);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'abc');
      await tester.pump();

      expect(find.text('Informe um valor como 24,90.'), findsOneWidget);
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
      expect(rig.repository.confirmed, isEmpty);
    });

    testWidgets('nothing read: says so and asks for the price', (tester) async {
      final rig = await pump(
        tester,
        draft: draftJson(prices: [], variants: []),
      );
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      expect(
        find.text('Não conseguimos ler o preço. Digite o valor que você viu.'),
        findsOneWidget,
      );
      expect(
        find.text('Não identificamos o produto. Escolha um na busca.'),
        findsOneWidget,
      );
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
      expect(rig.repository.confirmed, isEmpty);
    });

    testWidgets(
      'a barcode match is labelled as read, a name match as a guess',
      (tester) async {
        await pump(
          tester,
          draft: draftJson(
            variants: [
              {
                ...variantJson('v1', 'Arroz Branco'),
                'basis': 'GTIN',
                'origin': 'FACT',
              },
              {
                ...variantJson('v2', 'Arroz Integral'),
                'basis': 'TEXT',
                'origin': 'INFERENCE',
              },
            ],
          ),
        );
        await tester.tap(find.text('Tirar foto da etiqueta'));
        await tester.pumpAndSettle();

        expect(find.text('Código de barras lido na etiqueta'), findsOneWidget);
        expect(find.text('Sugestão pelo nome (confira)'), findsOneWidget);
      },
    );

    testWidgets('cancelling discards the draft on the server', (tester) async {
      final rig = await pump(tester);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Cancelar contribuição'),
        200,
        scrollable: find.byType(Scrollable).first,
      );

      await tester.tap(find.text('Cancelar contribuição'));
      await tester.pumpAndSettle();

      expect(rig.repository.cancelled, ['draft-1']);
      expect(rig.repository.confirmed, isEmpty);
    });

    testWidgets('going back from the review also discards the draft', (
      tester,
    ) async {
      final rig = await pump(tester);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      await tester.pageBack();
      await tester.pumpAndSettle();

      expect(rig.repository.cancelled, ['draft-1']);
    });

    testWidgets('backing out of the camera leaves nothing behind', (
      tester,
    ) async {
      final rig = await pump(tester, photo: null);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      expect(find.text('Tirar foto da etiqueta'), findsOneWidget);
      expect(rig.repository.created, 0);
    });

    testWidgets('a failed reading still lets the shopper type the price', (
      tester,
    ) async {
      final rig = await pump(tester, readerFails: true);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();

      expect(rig.repository.created, 1);
      expect(rig.repository.lastText, '');
      expect(find.text('Confira o que lemos'), findsOneWidget);
    });

    testWidgets('without location the price is still sent, with no position', (
      tester,
    ) async {
      final rig = await pump(tester);
      await tester.tap(find.text('Tirar foto da etiqueta'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Confirmar e enviar'));
      await tester.pumpAndSettle();

      expect(rig.repository.lastLat, isNull);
      expect(rig.repository.confirmed, hasLength(1));
    });
  });
}

class FakeContributions extends ContributionsRepository {
  FakeContributions(this.draft) : super(ApiClient(TokenStorage()));

  final Map<String, dynamic> draft;
  final confirmed = <(String, String, String)>[];
  final cancelled = <String>[];
  int created = 0;
  String? lastText;
  double? lastLat;

  @override
  Future<Draft> createDraft({
    required String storeId,
    required String photoPath,
    required String ocrText,
    required DateTime capturedAt,
  }) async {
    created++;
    lastText = ocrText;
    return Draft.fromJson(draft);
  }

  @override
  Future<void> confirm(
    String draftId, {
    required String variantId,
    required String price,
    double? lat,
    double? lon,
  }) async {
    lastLat = lat;
    confirmed.add((draftId, variantId, price));
  }

  @override
  Future<void> cancel(String draftId) async => cancelled.add(draftId);
}

class FakePhoto implements PhotoSource {
  FakePhoto(this.path);
  final String? path;
  @override
  Future<String?> take() async => path;
}

class FakeReader implements TextReader {
  FakeReader({this.fails = false});
  final bool fails;
  @override
  Future<String> read(String photoPath) async =>
      fails ? throw StateError('no ocr') : 'ARROZ\nR\$ 24,90';
}

class NoLocation extends LocationService {
  const NoLocation();
  @override
  Future<Coordinates> current() async =>
      throw const LocationFailure(LocationProblem.denied);
}

class Rig {
  Rig(this.repository);
  final FakeContributions repository;
}

Future<Rig> pump(
  WidgetTester tester, {
  Map<String, dynamic>? draft,
  String? photo = 'pubspec.yaml',
  bool readerFails = false,
}) async {
  // A phone-sized surface: the review screen is a long scrolling list.
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  final repository = FakeContributions(draft ?? draftJson());
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        contributionsRepositoryProvider.overrideWithValue(repository),
        photoSourceProvider.overrideWithValue(FakePhoto(photo)),
        textReaderProvider.overrideWithValue(FakeReader(fails: readerFails)),
        locationServiceProvider.overrideWithValue(const NoLocation()),
      ],
      child: MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const ContributePage(store: store),
                  ),
                ),
                child: const Text('abrir'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('abrir'));
  await tester.pumpAndSettle();
  return Rig(repository);
}
