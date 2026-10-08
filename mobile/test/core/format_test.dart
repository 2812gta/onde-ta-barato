import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/core/format.dart';

void main() {
  group('formatDistance', () {
    test('meters below one kilometre', () {
      expect(formatDistance(0), '0 m');
      expect(formatDistance(350), '350 m');
      expect(formatDistance(999), '999 m');
    });

    test('kilometres with a decimal comma, dropping a useless ,0', () {
      expect(formatDistance(1000), '1 km');
      expect(formatDistance(1234), '1,2 km');
      expect(formatDistance(18400), '18,4 km');
    });

    test('unknown distance shows nothing', () {
      expect(formatDistance(null), '');
    });
  });

  test('store types are translated, unknown ones fall back', () {
    expect(storeTypeLabel('SUPERMARKET'), 'Supermercado');
    expect(storeTypeLabel('GREENGROCER'), 'Hortifruti');
    expect(storeTypeLabel('SOMETHING_NEW'), 'Outro');
  });
}
