import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'capture.dart';
import 'contributions_repository.dart';

final contributionsRepositoryProvider = Provider<ContributionsRepository>(
  (ref) => ContributionsRepository(ref.watch(apiClientProvider)),
);

final photoSourceProvider = Provider<PhotoSource>(
  (ref) => const CameraPhotoSource(),
);

final textReaderProvider = Provider<TextReader>(
  (ref) => const MlKitTextReader(),
);
