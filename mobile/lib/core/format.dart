/// "350 m" below one kilometre, "1,2 km" above (Brazilian decimal comma).
String formatDistance(int? meters) {
  if (meters == null) return '';
  if (meters < 1000) return '$meters m';
  final km = (meters / 1000).toStringAsFixed(1).replaceAll('.', ',');
  return '${km.endsWith(',0') ? km.substring(0, km.length - 2) : km} km';
}

/// "24.00" (as the API sends decimals, always text) -> "R$ 24,00"; "1234.5" -> "R$ 1.234,50".
/// Money is never parsed to a double: it stays text from the server to the screen.
String formatMoney(String? amount) {
  if (amount == null || amount.isEmpty) return '';
  final negative = amount.startsWith('-');
  final parts = (negative ? amount.substring(1) : amount).split('.');
  final whole = parts.first.isEmpty ? '0' : parts.first;
  final cents = '${parts.length > 1 ? parts[1] : ''}00'.substring(0, 2);
  final grouped = whole.replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  return '${negative ? '-' : ''}R\$ $grouped,$cents';
}

/// "2.000" -> "2"; "1.500" -> "1,5"; "0.250" -> "0,25".
String formatQuantity(String quantity) {
  final parts = quantity.split('.');
  final decimals = parts.length > 1
      ? parts[1].replaceFirst(RegExp(r'0+$'), '')
      : '';
  return decimals.isEmpty ? parts.first : '${parts.first},$decimals';
}

const _storeTypes = {
  'SUPERMARKET': 'Supermercado',
  'MINIMARKET': 'Mercadinho',
  'WHOLESALE': 'Atacado',
  'BAKERY': 'Padaria',
  'BUTCHER': 'Açougue',
  'GREENGROCER': 'Hortifruti',
  'PHARMACY': 'Farmácia',
  'OTHER': 'Outro',
};

String storeTypeLabel(String type) => _storeTypes[type] ?? 'Outro';

const _units = {'l': 'L'};

String formatSize(String quantity, String unit) =>
    '${formatQuantity(quantity)} ${_units[unit] ?? unit}';
