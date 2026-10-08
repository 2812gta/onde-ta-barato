import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/features/stores/store.dart';

void main() {
  test('parses what the API returns', () {
    final store = Store.fromJson({
      'id': 'abc',
      'name': '[DEMO] Supermercado Aldeota',
      'store_type': 'SUPERMARKET',
      'neighborhood': 'Aldeota',
      'city': 'Fortaleza',
      'distance_m': 350,
      'merchant': {'id': 'm', 'trade_name': 'Rede Alfa', 'is_verified': true},
    });
    expect(store.name, '[DEMO] Supermercado Aldeota');
    expect(store.distanceMeters, 350);
    expect(store.merchantVerified, isTrue);
    expect(store.place, 'Aldeota · Fortaleza');
  });

  test('tolerates missing optional fields and an unclaimed store', () {
    final store = Store.fromJson({
      'id': 'abc',
      'name': 'Padaria',
      'store_type': null,
      'merchant': null,
    });
    expect(store.type, 'OTHER');
    expect(store.merchantVerified, isFalse);
    expect(store.distanceMeters, isNull);
    expect(store.place, '');
  });
}
