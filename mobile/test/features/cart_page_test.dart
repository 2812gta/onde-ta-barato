import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/core/network/api_client.dart';
import 'package:ondetabarato/core/storage/token_storage.dart';
import 'package:ondetabarato/features/cart/cart.dart';
import 'package:ondetabarato/features/cart/cart_controller.dart';
import 'package:ondetabarato/features/cart/cart_page.dart';
import 'package:ondetabarato/features/cart/cart_repository.dart';

import 'models_test.dart' show cartJson, lineJson;

class FakeCartRepository extends CartRepository {
  FakeCartRepository(this.cart) : super(ApiClient(TokenStorage()));

  Cart cart;
  final quantities = <(String, String)>[];
  final removed = <String>[];

  @override
  Future<Cart> fetch() async => cart;

  @override
  Future<Cart> updateItem(
    String itemId, {
    String? quantity,
    bool? inBasket,
  }) async {
    if (quantity != null) quantities.add((itemId, quantity));
    return cart;
  }

  @override
  Future<Cart> removeItem(String itemId) async {
    removed.add(itemId);
    return cart;
  }
}

Future<FakeCartRepository> pumpCart(WidgetTester tester, Cart cart) async {
  final repository = FakeCartRepository(cart);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [cartRepositoryProvider.overrideWithValue(repository)],
      child: const MaterialApp(home: CartPage()),
    ),
  );
  await tester.pumpAndSettle();
  return repository;
}

Map<String, dynamic> totals({
  String total = '40.00',
  String savings = '10.00',
  String potential = '0.00',
  int unpriced = 0,
}) => {
  'gross': '50.00',
  'total': total,
  'savings': savings,
  'cashback': '0.00',
  'unconfirmed_potential': potential,
  'unpriced_count': unpriced,
};

void main() {
  testWidgets('an empty cart explains how to fill it and has no total bar', (
    tester,
  ) async {
    await pumpCart(tester, Cart.fromJson(cartJson()));

    expect(find.textContaining('carrinho está vazio'), findsOneWidget);
    expect(find.byKey(const Key('cart-total')), findsNothing);
    expect(find.text('Finalizar compra'), findsNothing);
  });

  testWidgets('shows the server total, the saving and the promotion', (
    tester,
  ) async {
    await pumpCart(
      tester,
      Cart.fromJson(
        cartJson(
          items: [lineJson(promotion: '3 por R\$ 20', savings: '10.00')],
          totals: totals(),
        ),
      ),
    );

    expect(find.text('R\$ 40,00'), findsWidgets);
    expect(
      tester.widget<Text>(find.byKey(const Key('cart-total'))).data,
      'R\$ 40,00',
    );
    expect(find.text('Você economiza R\$ 10,00'), findsOneWidget);
    expect(find.textContaining('3 por R\$ 20'), findsOneWidget);
    expect(find.text('Arroz Branco 5 kg'), findsOneWidget);
    expect(find.text('Os preços podem divergir do caixa.'), findsOneWidget);
  });

  testWidgets('an unconfirmed promotion is reported but not counted', (
    tester,
  ) async {
    await pumpCart(
      tester,
      Cart.fromJson(
        cartJson(
          items: [lineJson(unconfirmed: '10.00')],
          totals: totals(total: '50.00', savings: '0.00', potential: '10.00'),
        ),
      ),
    );

    expect(find.text('Você economiza R\$ 0,00'), findsNothing);
    expect(find.textContaining('ainda não confirmada'), findsOneWidget);
    expect(
      find.textContaining('Promoção não confirmada: R\$ 10,00'),
      findsOneWidget,
    );
  });

  testWidgets('stale and unpriced items are flagged, never hidden', (
    tester,
  ) async {
    await pumpCart(
      tester,
      Cart.fromJson(
        cartJson(
          items: [
            lineJson(freshness: 'STALE'),
            lineJson(id: 'i2', priced: false),
          ],
          totals: totals(unpriced: 1),
        ),
      ),
    );

    expect(find.text('Preço desatualizado'), findsOneWidget);
    expect(find.text('Sem preço atual neste mercado'), findsOneWidget);
    expect(find.text('—'), findsOneWidget);
  });

  testWidgets('without a store the cart asks for one', (tester) async {
    final json = cartJson(items: [lineJson(priced: false)])..['store'] = null;
    await pumpCart(tester, Cart.fromJson(json));

    expect(find.text('Escolher o mercado'), findsOneWidget);
    // Not "no price at this store": no store was chosen yet.
    expect(find.text('Escolha o mercado para ver o preço'), findsOneWidget);
    expect(find.text('Sem preço atual neste mercado'), findsNothing);
  });

  testWidgets('the + button asks the server for the next quantity', (
    tester,
  ) async {
    final repository = await pumpCart(
      tester,
      Cart.fromJson(cartJson(items: [lineJson()], totals: totals())),
    );

    await tester.tap(find.byTooltip('Aumentar'));
    await tester.pumpAndSettle();

    expect(repository.quantities, [('i1', '6')]); // 5 -> 6
  });
}
