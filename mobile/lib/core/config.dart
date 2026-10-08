/// Build-time configuration, passed with `--dart-define`.
///
/// Development over USB: `adb reverse tcp:8001 tcp:8001`, then the phone reaches the API on
/// its own `localhost:8001`, so the defaults below work without Wi-Fi.
class AppConfig {
  const AppConfig._();

  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8001/api/v1',
  );

  /// Development only: use this position instead of the GPS (the demo data is in Fortaleza).
  /// Both must be set: `--dart-define=DEMO_LAT=-3.7385 --dart-define=DEMO_LON=-38.4965`.
  static const _demoLat = String.fromEnvironment('DEMO_LAT');
  static const _demoLon = String.fromEnvironment('DEMO_LON');

  static ({double lat, double lon})? get demoLocation {
    final lat = double.tryParse(_demoLat);
    final lon = double.tryParse(_demoLon);
    return (lat == null || lon == null) ? null : (lat: lat, lon: lon);
  }
}
