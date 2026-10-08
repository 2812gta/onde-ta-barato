/// The cart as the API prices it. Every amount stays decimal TEXT ("24.00"): money is never
/// converted to a double, so what the shopper sees is exactly what the server computed.
class CartLine {
  const CartLine({
    required this.id,
    required this.variantId,
    required this.label,
    required this.brand,
    required this.quantity,
    required this.inBasket,
    required this.priced,
    required this.unitPrice,
    required this.gross,
    required this.net,
    required this.savings,
    required this.promotion,
    required this.unconfirmedPotential,
    required this.freshness,
    required this.conflict,
  });

  factory CartLine.fromJson(Map<String, dynamic> json) => CartLine(
    id: json['id'] as String,
    variantId: json['variant_id'] as String,
    label: json['label'] as String,
    brand: json['brand'] as String?,
    quantity: json['quantity'] as String,
    inBasket: json['in_basket'] as bool,
    priced: json['priced'] as bool,
    unitPrice: json['unit_price'] as String?,
    gross: json['gross'] as String?,
    net: json['net'] as String?,
    savings: json['savings'] as String?,
    promotion: json['promotion'] as String?,
    unconfirmedPotential: json['unconfirmed_potential'] as String?,
    freshness: json['freshness'] as String?,
    conflict: (json['conflict'] as bool?) ?? false,
  );

  final String id;
  final String variantId;
  final String label;
  final String? brand;
  final String quantity;
  final bool inBasket;
  final bool priced;
  final String? unitPrice;
  final String? gross;
  final String? net;
  final String? savings;

  /// Title of the promotion that changed the price (verified merchants only).
  final String? promotion;
  final String? unconfirmedPotential;
  final String? freshness;
  final bool conflict;

  bool get stale => priced && freshness != null && freshness != 'CURRENT';

  bool get hasSavings =>
      savings != null && savings != '0.00' && savings!.isNotEmpty;

  bool get hasUnconfirmedPotential =>
      unconfirmedPotential != null && unconfirmedPotential != '0.00';
}

class CartTotals {
  const CartTotals({
    required this.gross,
    required this.total,
    required this.savings,
    required this.unconfirmedPotential,
    required this.unpricedCount,
  });

  factory CartTotals.fromJson(Map<String, dynamic> json) => CartTotals(
    gross: json['gross'] as String,
    total: json['total'] as String,
    savings: json['savings'] as String,
    unconfirmedPotential: json['unconfirmed_potential'] as String,
    unpricedCount: (json['unpriced_count'] as num).toInt(),
  );

  final String gross;
  final String total;
  final String savings;
  final String unconfirmedPotential;
  final int unpricedCount;

  bool get hasSavings => savings != '0.00';
  bool get hasUnconfirmedPotential => unconfirmedPotential != '0.00';
}

class CartStore {
  const CartStore({required this.id, required this.name});

  factory CartStore.fromJson(Map<String, dynamic> json) =>
      CartStore(id: json['id'] as String, name: json['name'] as String);

  final String id;
  final String name;
}

class Cart {
  const Cart({
    required this.id,
    required this.status,
    required this.store,
    required this.paymentCondition,
    required this.items,
    required this.totals,
    required this.warnings,
  });

  factory Cart.fromJson(Map<String, dynamic> json) => Cart(
    id: json['id'] as String?,
    status: json['status'] as String,
    store: json['store'] == null
        ? null
        : CartStore.fromJson(json['store'] as Map<String, dynamic>),
    paymentCondition: json['payment_condition'] as String,
    items: [
      for (final item in json['items'] as List<dynamic>)
        CartLine.fromJson(item as Map<String, dynamic>),
    ],
    totals: CartTotals.fromJson(json['totals'] as Map<String, dynamic>),
    warnings: [for (final w in json['warnings'] as List<dynamic>) w as String],
  );

  /// Null while the shopper has no open cart (reading never creates one).
  final String? id;
  final String status;
  final CartStore? store;
  final String paymentCondition;
  final List<CartLine> items;
  final CartTotals totals;
  final List<String> warnings;

  bool get isEmpty => items.isEmpty;
  bool get closed => status == 'CLOSED';
}

const paymentOptions = {
  'NORMAL': 'Normal',
  'PIX': 'Pix',
  'DEBIT': 'Débito',
  'CREDIT': 'Crédito',
};
