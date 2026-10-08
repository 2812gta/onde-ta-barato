import 'package:flutter/material.dart';

/// Green: saving money. Material 3 derives the whole palette (light and dark) from one seed.
abstract final class AppTheme {
  static const _seed = Color(0xFF1B8A4B);

  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) => ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: _seed, brightness: brightness),
    appBarTheme: const AppBarTheme(centerTitle: false),
  );
}
