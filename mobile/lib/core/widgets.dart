import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/auth_controller.dart';
import 'network/api_client.dart';

/// Sign-out button shared by the top-level screens.
class LogoutButton extends ConsumerWidget {
  const LogoutButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => IconButton(
    tooltip: 'Sair',
    icon: const Icon(Icons.logout),
    onPressed: () => ref.read(authControllerProvider.notifier).logout(),
  );
}

/// What to show when a load fails: the worded message and a retry. No technical detail.
class ProblemView extends StatelessWidget {
  const ProblemView({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  String get message => error is ApiException
      ? (error as ApiException).message
      : 'Não foi possível carregar. Tente de novo.';

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 64),
        const Icon(Icons.cloud_off_outlined, size: 48),
        const SizedBox(height: 16),
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        Center(
          child: TextButton(
            onPressed: onRetry,
            child: const Text('Tentar de novo'),
          ),
        ),
      ],
    );
  }
}

/// Centered hint for an empty screen.
class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 64),
        Icon(icon, size: 48),
        const SizedBox(height: 16),
        Text(text, textAlign: TextAlign.center),
      ],
    );
  }
}

/// Runs a user action; a failure becomes a short message instead of an unhandled exception.
Future<bool> attempt(
  BuildContext context,
  Future<void> Function() action,
) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    await action();
    return true;
  } catch (error) {
    _showFailure(messenger, error);
    return false;
  }
}

void _showFailure(ScaffoldMessengerState messenger, Object error) {
  final text = error is ApiException
      ? error.message
      : 'Não foi possível concluir. Tente de novo.';
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}

/// Like [attempt], but returns the action's result, or null when it failed (the message was
/// already shown). A legitimately null result is indistinguishable from a failure.
Future<T?> attemptValue<T>(
  BuildContext context,
  Future<T> Function() action,
) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    return await action();
  } catch (error) {
    _showFailure(messenger, error);
    return null;
  }
}

void notify(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}
