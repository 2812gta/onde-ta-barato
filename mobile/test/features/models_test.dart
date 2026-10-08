import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/features/cart/cart.dart';
import 'package:ondetabarato/features/products/product.dart';
import 'package:ondetabarato/features/shopping_lists/lists_controller.dart';
import 'package:ondetabarato/features/shopping_lists/shopping_list.dart';

Map<String, dynamic> cartJson({
  List<Map<String, dynamic>> items = const [],
  Map<String, dynamic>? totals,
}) => {
  'id': items.isEmpty ? null : 'cart-1',
  'status': 'OPEN',
  'store': {'id': 's1', 'name': '[DEMO] Supermercado Aldeota'},
  'payment_condition': 'PIX',
  'has_loyalty': false,
  'coupon_codes': <String>[],
  'items': items,
  'totals':
      totals ??
      {
        'gross': '0.00',
        'total': '0.00',
        'savings': '0.00',
        'cashback': '0.00',
        'unconfirmed_potential': '0.00',
        'unpriced_count': 0,
      },
  'warnings': ['Os preços podem divergir do caixa.'],
};

Map<String, dynamic> lineJson({
  String id = 'i1',
  bool priced = true,
  String freshness = 'CURRENT',
  String? promotion,
  String savings = '0.00',
  String unconfirmed = '0.00',
}) => {
  'id': id,
  'variant_id': 'v1',
  'label': 'Arroz Branco 5 kg',
  'brand': 'Grão Dourado',
  'quantity': '5.000',
  'in_basket': false,
  'priced': priced,
  'unit_price': priced ? '10.00' : null,
  'gross': priced ? '50.00' : null,
  'net': priced ? '40.00' : null,
  'savings': priced ? savings : null,
  'cashback': priced ? '0.00' : null,
  'promotion': promotion,
  'unconfirmed_potential': priced ? unconfirmed : null,
  'freshness': priced ? freshness : null,
  'confidence': priced ? 0.7 : null,
  'conflict': false,
  'age_hours': priced ? 2.0 : null,
};

void main() {
  group('Cart', () {
    test('keeps money as the exact text the server sent', () {
      final cart = Cart.fromJson(
        cartJson(
          items: [lineJson(promotion: '3 por R\$ 20', savings: '10.00')],
          totals: {
            'gross': '50.00',
            'total': '40.00',
            'savings': '10.00',
            'cashback': '0.00',
            'unconfirmed_potential': '0.00',
            'unpriced_count': 0,
          },
        ),
      );
      expect(cart.totals.total, '40.00');
      expect(cart.items.single.net, '40.00');
      expect(cart.items.single.hasSavings, isTrue);
      expect(cart.items.single.promotion, '3 por R\$ 20');
      expect(cart.totals.hasSavings, isTrue);
      expect(cart.store?.name, '[DEMO] Supermercado Aldeota');
      expect(cart.paymentCondition, 'PIX');
    });

    test('an unpriced line has no amounts and is never "stale"', () {
      final line = CartLine.fromJson(lineJson(priced: false));
      expect(line.priced, isFalse);
      expect(line.net, isNull);
      expect(line.stale, isFalse);
      expect(line.hasSavings, isFalse);
    });

    test('stale prices and unconfirmed promotions are recognised', () {
      final line = CartLine.fromJson(
        lineJson(freshness: 'STALE', unconfirmed: '10.00'),
      );
      expect(line.stale, isTrue);
      expect(line.hasUnconfirmedPotential, isTrue);
      expect(line.hasSavings, isFalse); // an unconfirmed saving is not a saving
    });

    test('an empty cart has no id (reading never creates one)', () {
      final cart = Cart.fromJson(cartJson());
      expect(cart.id, isNull);
      expect(cart.isEmpty, isTrue);
    });
  });

  group('Comparison', () {
    final json = {
      'variant_id': 'v1',
      'label': 'Menor preço encontrado na nossa base',
      'notes': ['Pode haver diferença no caixa.'],
      'results': [
        {
          'rank': 1,
          'store': {
            'id': 's1',
            'name': '[DEMO] Atacado Parangaba',
            'distance_m': 7979,
            'merchant_verified': true,
          },
          'price': '25.11',
          'price_range': null,
          'price_conflict': false,
          'payment_condition': 'NORMAL',
          'unit_price': {
            'amount': '5.0220',
            'per': 'kg',
            'display': 'R\$ 5,02/kg',
          },
          'freshness': 'CURRENT',
          'age_hours': 4.4,
          'confidence': 0.7,
        },
        {
          'rank': 2,
          'store': {
            'id': 's2',
            'name': 'Loja B',
            'distance_m': null,
            'merchant_verified': false,
          },
          'price': '27.00',
          'price_range': ['24.00', '27.00'],
          'price_conflict': true,
          'payment_condition': 'NORMAL',
          'unit_price': {
            'amount': '5.4',
            'per': 'kg',
            'display': 'R\$ 5,40/kg',
          },
          'freshness': 'STALE',
          'age_hours': 300,
          'confidence': 0.3,
        },
      ],
    };

    test('parses ranking, unit price text and honesty flags', () {
      final comparison = Comparison.fromJson(json);
      expect(comparison.label, 'Menor preço encontrado na nossa base');
      final first = comparison.results.first;
      expect(first.rank, 1);
      expect(first.unitPriceText, 'R\$ 5,02/kg');
      expect(first.merchantVerified, isTrue);
      expect(first.stale, isFalse);
      final second = comparison.results.last;
      expect(second.conflict, isTrue);
      expect(second.priceRange, ('24.00', '27.00'));
      expect(second.stale, isTrue);
      expect(second.distanceMeters, isNull);
    });

    test('the "lowest price" label can be absent', () {
      final comparison = Comparison.fromJson({
        'variant_id': 'v1',
        'label': null,
        'notes': ['Apenas um preço encontrado; não há com o que comparar.'],
        'results': <Map<String, dynamic>>[],
      });
      expect(comparison.label, isNull);
      expect(comparison.results, isEmpty);
    });
  });

  group('lists', () {
    test('parses a list with items', () {
      final detail = ShoppingListDetail.fromJson({
        'id': 'l1',
        'name': 'Semana',
        'items': [
          {
            'id': 'i1',
            'variant_id': 'v1',
            'label': 'Arroz Branco 5 kg',
            'brand': null,
            'quantity': '2.000',
            'checked': true,
          },
        ],
      });
      expect(detail.items.single.checked, isTrue);
      expect(detail.items.single.quantity, '2.000');
    });

    test('quantity steps stay within 1..1000 and whole', () {
      expect(nextQuantity('1.000', 1), '2');
      expect(nextQuantity('1.000', -1), '1'); // never below one
      expect(nextQuantity('3.500', 1), '5'); // 4.5 rounds to the nearest whole
      expect(nextQuantity('1000.000', 1), '1000');
    });
  });
}
