class ListSummary {
  const ListSummary({
    required this.id,
    required this.name,
    required this.itemCount,
    required this.checkedCount,
  });

  factory ListSummary.fromJson(Map<String, dynamic> json) => ListSummary(
    id: json['id'] as String,
    name: json['name'] as String,
    itemCount: (json['item_count'] as num?)?.toInt() ?? 0,
    checkedCount: (json['checked_count'] as num?)?.toInt() ?? 0,
  );

  final String id;
  final String name;
  final int itemCount;
  final int checkedCount;
}

class ListItem {
  const ListItem({
    required this.id,
    required this.variantId,
    required this.label,
    required this.brand,
    required this.quantity,
    required this.checked,
  });

  factory ListItem.fromJson(Map<String, dynamic> json) => ListItem(
    id: json['id'] as String,
    variantId: json['variant_id'] as String,
    label: json['label'] as String,
    brand: json['brand'] as String?,
    quantity: json['quantity'] as String,
    checked: json['checked'] as bool,
  );

  final String id;
  final String variantId;
  final String label;
  final String? brand;

  /// Decimal text exactly as the server sent it ("2.000").
  final String quantity;
  final bool checked;
}

class ShoppingListDetail {
  const ShoppingListDetail({
    required this.id,
    required this.name,
    required this.items,
  });

  factory ShoppingListDetail.fromJson(Map<String, dynamic> json) =>
      ShoppingListDetail(
        id: json['id'] as String,
        name: json['name'] as String,
        items: [
          for (final item in json['items'] as List<dynamic>)
            ListItem.fromJson(item as Map<String, dynamic>),
        ],
      );

  final String id;
  final String name;
  final List<ListItem> items;
}
