import '../../core/format.dart';

/// A purchasable presentation (e.g. "Arroz Branco 5 kg"). Prices attach to this, never to the
/// bare product, so a unit price can compare sizes honestly.
class Variant {
  const Variant({
    required this.id,
    required this.name,
    required this.brand,
    required this.label,
    required this.quantity,
    required this.unit,
  });

  factory Variant.fromJson(Map<String, dynamic> json) => Variant(
    id: json['id'] as String,
    name: json['name'] as String,
    brand: json['brand'] as String?,
    label: (json['label'] as String?) ?? '',
    quantity: json['quantity'] as String,
    unit: json['unit'] as String,
  );

  final String id;
  final String name;
  final String? brand;
  final String label;
  final String quantity;
  final String unit;

  /// "Arroz Branco · Grão Dourado · Tipo 1 · 5 kg"
  String get title => [
    name,
    if (brand != null && brand!.isNotEmpty) brand!,
    if (label.isNotEmpty) label,
    formatSize(quantity, unit),
  ].join(' · ');
}

class StoreQuote {
  const StoreQuote({
    required this.rank,
    required this.storeId,
    required this.storeName,
    required this.distanceMeters,
    required this.merchantVerified,
    required this.price,
    required this.priceRange,
    required this.conflict,
    required this.unitPriceText,
    required this.freshness,
    required this.ageHours,
    required this.confidence,
  });

  factory StoreQuote.fromJson(Map<String, dynamic> json) {
    final store = json['store'] as Map<String, dynamic>;
    final range = json['price_range'] as List<dynamic>?;
    return StoreQuote(
      rank: (json['rank'] as num).toInt(),
      storeId: store['id'] as String,
      storeName: store['name'] as String,
      distanceMeters: (store['distance_m'] as num?)?.toInt(),
      merchantVerified: (store['merchant_verified'] as bool?) ?? false,
      price: json['price'] as String,
      priceRange: range == null
          ? null
          : (range[0] as String, range[1] as String),
      conflict: (json['price_conflict'] as bool?) ?? false,
      unitPriceText:
          (json['unit_price'] as Map<String, dynamic>)['display'] as String,
      freshness: json['freshness'] as String,
      ageHours: (json['age_hours'] as num).toDouble(),
      confidence: (json['confidence'] as num).toDouble(),
    );
  }

  final int rank;
  final String storeId;
  final String storeName;
  final int? distanceMeters;
  final bool merchantVerified;
  final String price;
  final (String, String)? priceRange;
  final bool conflict;

  /// Already formatted by the server ("R$ 5,02/kg"); this is the basis of the ranking.
  final String unitPriceText;
  final String freshness;
  final double ageHours;
  final double confidence;

  bool get stale => freshness != 'CURRENT';
}

class Comparison {
  const Comparison({
    required this.label,
    required this.notes,
    required this.results,
  });

  factory Comparison.fromJson(Map<String, dynamic> json) => Comparison(
    label: json['label'] as String?,
    notes: [for (final n in json['notes'] as List<dynamic>) n as String],
    results: [
      for (final r in json['results'] as List<dynamic>)
        StoreQuote.fromJson(r as Map<String, dynamic>),
    ],
  );

  /// "Lowest price found in our base" is only present when it is true to say so.
  final String? label;
  final List<String> notes;
  final List<StoreQuote> results;
}
