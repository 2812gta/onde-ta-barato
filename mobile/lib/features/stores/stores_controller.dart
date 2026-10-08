import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'location_service.dart';
import 'store.dart';
import 'stores_repository.dart';

final storesRepositoryProvider = Provider<StoresRepository>(
  (ref) => StoresRepository(ref.watch(apiClientProvider)),
);

final locationServiceProvider = Provider<LocationService>(
  (ref) => const LocationService(),
);

const radiusOptionsKm = [2.0, 5.0, 10.0, 25.0];

class RadiusController extends Notifier<double> {
  @override
  double build() => 5;

  void select(double km) => state = km;
}

final radiusProvider = NotifierProvider<RadiusController, double>(
  RadiusController.new,
);

/// Stores around the shopper. Changing the radius or invalidating this reloads it.
final nearbyStoresProvider = FutureProvider.autoDispose<List<Store>>((
  ref,
) async {
  final radius = ref.watch(radiusProvider);
  final position = await ref.read(locationServiceProvider).current();
  return ref
      .read(storesRepositoryProvider)
      .nearby(lat: position.lat, lon: position.lon, radiusKm: radius);
});
