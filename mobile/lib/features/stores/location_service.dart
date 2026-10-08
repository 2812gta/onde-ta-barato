import 'package:geolocator/geolocator.dart';

import '../../core/config.dart';

enum LocationProblem { serviceOff, denied, deniedForever, unavailable }

class LocationFailure implements Exception {
  const LocationFailure(this.problem);

  final LocationProblem problem;

  String get message => switch (problem) {
    LocationProblem.serviceOff =>
      'A localização do aparelho está desligada. Ative-a para ver as lojas perto de você.',
    LocationProblem.denied =>
      'Precisamos da sua localização para mostrar as lojas próximas.',
    LocationProblem.deniedForever =>
      'A permissão de localização foi negada. Ative-a nas configurações do aplicativo.',
    LocationProblem.unavailable =>
      'Não foi possível obter sua localização agora. Tente de novo.',
  };
}

typedef Coordinates = ({double lat, double lon});

/// The position is used for the request and never stored by the app.
class LocationService {
  const LocationService();

  Future<Coordinates> current() async {
    final demo = AppConfig.demoLocation;
    if (demo != null) return demo;

    if (!await Geolocator.isLocationServiceEnabled()) {
      throw const LocationFailure(LocationProblem.serviceOff);
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.deniedForever) {
      throw const LocationFailure(LocationProblem.deniedForever);
    }
    if (permission == LocationPermission.denied) {
      throw const LocationFailure(LocationProblem.denied);
    }
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 15),
        ),
      );
      return (lat: position.latitude, lon: position.longitude);
    } catch (_) {
      throw const LocationFailure(LocationProblem.unavailable);
    }
  }

  Future<void> openSettings(LocationProblem problem) => switch (problem) {
    LocationProblem.serviceOff => Geolocator.openLocationSettings(),
    _ => Geolocator.openAppSettings(),
  };
}
