/// A store as the API describes it. Plain Dart: no generated code needed at this size.
class Store {
  const Store({
    required this.id,
    required this.name,
    required this.type,
    required this.neighborhood,
    required this.city,
    required this.distanceMeters,
    required this.merchantVerified,
  });

  factory Store.fromJson(Map<String, dynamic> json) {
    final merchant = json['merchant'] as Map<String, dynamic>?;
    return Store(
      id: json['id'] as String,
      name: json['name'] as String,
      type: (json['store_type'] as String?) ?? 'OTHER',
      neighborhood: (json['neighborhood'] as String?) ?? '',
      city: (json['city'] as String?) ?? '',
      distanceMeters: (json['distance_m'] as num?)?.toInt(),
      merchantVerified: (merchant?['is_verified'] as bool?) ?? false,
    );
  }

  final String id;
  final String name;
  final String type;
  final String neighborhood;
  final String city;
  final int? distanceMeters;

  /// Only a merchant that went through verification may show the verified badge.
  final bool merchantVerified;

  String get place =>
      [neighborhood, city].where((s) => s.isNotEmpty).join(' · ');
}
