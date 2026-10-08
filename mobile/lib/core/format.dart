/// "350 m" below one kilometre, "1,2 km" above (Brazilian decimal comma).
String formatDistance(int? meters) {
  if (meters == null) return '';
  if (meters < 1000) return '$meters m';
  final km = (meters / 1000).toStringAsFixed(1).replaceAll('.', ',');
  return '${km.endsWith(',0') ? km.substring(0, km.length - 2) : km} km';
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
