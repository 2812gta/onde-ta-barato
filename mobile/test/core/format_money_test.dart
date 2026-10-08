import 'package:flutter_test/flutter_test.dart';
import 'package:ondetabarato/core/format.dart';

void main() {
  group('formatMoney', () {
    test('keeps the cents exactly as the server sent them', () {
      expect(formatMoney('24.00'), 'R\$ 24,00');
      expect(formatMoney('5.9'), 'R\$ 5,90');
      expect(formatMoney('0.05'), 'R\$ 0,05');
      expect(formatMoney('7'), 'R\$ 7,00');
    });

    test('groups thousands the Brazilian way', () {
      expect(formatMoney('1234.50'), 'R\$ 1.234,50');
      expect(formatMoney('1234567.89'), 'R\$ 1.234.567,89');
    });

    test('never rounds (the server already did, once)', () {
      expect(formatMoney('0.999'), 'R\$ 0,99');
    });

    test('missing values show nothing', () {
      expect(formatMoney(null), '');
      expect(formatMoney(''), '');
    });
  });

  group('formatQuantity', () {
    test('whole numbers lose the decimals', () {
      expect(formatQuantity('2.000'), '2');
      expect(formatQuantity('12'), '12');
    });

    test('fractions use a decimal comma', () {
      expect(formatQuantity('1.500'), '1,5');
      expect(formatQuantity('0.250'), '0,25');
    });
  });

  test('sizes read naturally', () {
    expect(formatSize('5.000', 'kg'), '5 kg');
    expect(formatSize('900.000', 'ml'), '900 ml');
    expect(formatSize('1.000', 'l'), '1 L');
    expect(formatSize('12.000', 'un'), '12 un');
  });
}
