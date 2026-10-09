import '../products/product.dart';

/// Where a piece of what we read comes from. The screen must never present an inference as
/// if it were read from the label.
enum Origin {
  fact,
  inference;

  static Origin parse(String? value) =>
      value == 'FACT' ? Origin.fact : Origin.inference;
}

/// A price printed on the label, exactly as the phone read it.
class PriceReading {
  const PriceReading({
    required this.value,
    required this.raw,
    required this.hasCurrency,
  });

  factory PriceReading.fromJson(Map<String, dynamic> json) => PriceReading(
    value: json['value'] as String,
    raw: json['raw'] as String,
    hasCurrency: (json['has_currency'] as bool?) ?? false,
  );

  /// Normalized with a dot ("24.90").
  final String value;
  final String raw;
  final bool hasCurrency;
}

/// A catalog product we suggest for what was read. The shopper decides.
class VariantSuggestion {
  const VariantSuggestion({
    required this.variant,
    required this.basis,
    required this.origin,
  });

  factory VariantSuggestion.fromJson(Map<String, dynamic> json) =>
      VariantSuggestion(
        variant: Variant.fromJson(json),
        basis: json['basis'] as String,
        origin: Origin.parse(json['origin'] as String?),
      );

  final Variant variant;

  /// `GTIN` (the barcode was read) or `TEXT` (words in common).
  final String basis;
  final Origin origin;

  bool get byBarcode => basis == 'GTIN';
}

/// A contribution waiting for the shopper's confirmation. Nothing is a price yet.
class Draft {
  const Draft({
    required this.id,
    required this.prices,
    required this.suggestions,
  });

  factory Draft.fromJson(Map<String, dynamic> json) {
    final reading = json['reading'] as Map<String, dynamic>;
    return Draft(
      id: json['id'] as String,
      prices: [
        for (final p in reading['prices'] as List<dynamic>)
          PriceReading.fromJson(p as Map<String, dynamic>),
      ],
      suggestions: [
        for (final s in json['suggested_variants'] as List<dynamic>)
          VariantSuggestion.fromJson(s as Map<String, dynamic>),
      ],
    );
  }

  final String id;
  final List<PriceReading> prices;
  final List<VariantSuggestion> suggestions;
}

/// Turns what the shopper typed ("24,90", "R$ 1.249,90") into the API's "24.90", or null
/// when it is not a usable price.
String? parsePrice(String input) {
  var text = input.trim().replaceAll(RegExp(r'^R\$\s*'), '');
  if (text.isEmpty) return null;
  if (text.contains(',')) {
    text = text.replaceAll('.', '').replaceAll(',', '.');
  }
  if (!RegExp(r'^\d{1,5}(\.\d{1,2})?$').hasMatch(text)) return null;
  final value = double.parse(text);
  if (value <= 0) return null;
  return value.toStringAsFixed(2);
}
