import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/widgets.dart';
import '../products/product.dart';
import '../products/products_controller.dart';
import '../stores/location_service.dart';
import '../stores/store.dart';
import '../stores/stores_controller.dart';
import 'contribution.dart';
import 'contributions_controller.dart';

enum _Step { start, working, review }

/// Photograph a price tag, check what was read, and only then send it as a price.
class ContributePage extends ConsumerStatefulWidget {
  const ContributePage({super.key, required this.store});

  final Store store;

  @override
  ConsumerState<ContributePage> createState() => _ContributePageState();
}

class _ContributePageState extends ConsumerState<ContributePage> {
  final _price = TextEditingController();
  _Step _step = _Step.start;
  String? _photoPath;
  Draft? _draft;
  Variant? _variant;
  bool _sending = false;
  bool _finished = false;

  @override
  void dispose() {
    _price.dispose();
    super.dispose();
  }

  Future<void> _capture() async {
    final photoSource = ref.read(photoSourceProvider);
    final reader = ref.read(textReaderProvider);
    final repository = ref.read(contributionsRepositoryProvider);
    final path = await attemptValue(context, photoSource.take);
    if (path == null || !mounted) return;
    setState(() {
      _step = _Step.working;
      _photoPath = path;
    });
    final draft = await attemptValue(context, () async {
      // Reading failing is not fatal: the shopper can still type what they see.
      final text = await reader.read(path).catchError((_) => '');
      return repository.createDraft(
        storeId: widget.store.id,
        photoPath: path,
        ocrText: text,
        capturedAt: DateTime.now(),
      );
    });
    if (!mounted) return;
    if (draft == null) {
      setState(() => _step = _Step.start);
      return;
    }
    setState(() {
      _draft = draft;
      _step = _Step.review;
      _variant = draft.suggestions.isEmpty
          ? null
          : draft.suggestions.first.variant;
      _price.text = draft.prices.isEmpty
          ? ''
          : draft.prices.first.value.replaceAll('.', ',');
    });
  }

  Future<void> _confirm() async {
    final draft = _draft;
    final variant = _variant;
    final price = parsePrice(_price.text);
    if (draft == null || variant == null || price == null) return;
    final repository = ref.read(contributionsRepositoryProvider);
    final location = ref.read(locationServiceProvider);
    setState(() => _sending = true);
    final ok = await attempt(context, () async {
      // Only to check the phone is near the store; if it is unavailable we still send.
      Coordinates? where;
      try {
        where = await location.current();
      } on LocationFailure {
        where = null;
      }
      await repository.confirm(
        draft.id,
        variantId: variant.id,
        price: price,
        lat: where?.lat,
        lon: where?.lon,
      );
    });
    if (!mounted) return;
    setState(() => _sending = false);
    if (ok) {
      _finished = true;
      notify(context, 'Obrigado! Seu preço foi enviado.');
      Navigator.of(context).pop();
    }
  }

  /// Leaving or cancelling deletes the photo on the server.
  Future<void> _discard() async {
    final draft = _draft;
    if (draft == null || _finished) return;
    _finished = true;
    try {
      await ref.read(contributionsRepositoryProvider).cancel(draft.id);
    } catch (_) {
      // The server also expires drafts on its own after 24 hours.
    }
  }

  Future<void> _pickOther() async {
    final picked = await showModalBottomSheet<Variant>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _ProductPicker(),
    );
    if (picked != null) setState(() => _variant = picked);
  }

  @override
  Widget build(BuildContext context) {
    final inReview = _step == _Step.review && !_finished;
    return PopScope(
      canPop: !inReview,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        await _discard();
        if (context.mounted) Navigator.of(context).pop();
      },
      child: Scaffold(
        appBar: AppBar(title: const Text('Contribuir com um preço')),
        body: switch (_step) {
          _Step.start => _Start(store: widget.store, onCapture: _capture),
          _Step.working => const _Working(),
          _Step.review => _Review(
            draft: _draft!,
            photoPath: _photoPath,
            variant: _variant,
            priceController: _price,
            sending: _sending,
            onPickPrice: (value) =>
                setState(() => _price.text = value.replaceAll('.', ',')),
            onPickVariant: (value) => setState(() => _variant = value),
            onPickOther: _pickOther,
            onChanged: () => setState(() {}),
            onConfirm: _confirm,
            onCancel: () async {
              await _discard();
              if (context.mounted) Navigator.of(context).pop();
            },
          ),
        },
      ),
    );
  }
}

class _Start extends StatelessWidget {
  const _Start({required this.store, required this.onCapture});

  final Store store;
  final VoidCallback onCapture;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 24),
        const Icon(Icons.photo_camera_outlined, size: 56),
        const SizedBox(height: 16),
        Text(
          store.name,
          textAlign: TextAlign.center,
          style: theme.textTheme.titleLarge,
        ),
        const SizedBox(height: 16),
        const Text(
          'Fotografe a etiqueta de preço de um produto que você está vendo '
          'agora nesta loja.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        Text(
          'O texto da etiqueta é lido no seu celular. Você confere tudo antes '
          'de enviar, e nada vira preço sem a sua confirmação.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 32),
        FilledButton.icon(
          onPressed: onCapture,
          icon: const Icon(Icons.photo_camera),
          label: const Text('Tirar foto da etiqueta'),
        ),
      ],
    );
  }
}

class _Working extends StatelessWidget {
  const _Working();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Lendo a etiqueta…'),
        ],
      ),
    );
  }
}

class _Review extends StatelessWidget {
  const _Review({
    required this.draft,
    required this.photoPath,
    required this.variant,
    required this.priceController,
    required this.sending,
    required this.onPickPrice,
    required this.onPickVariant,
    required this.onPickOther,
    required this.onChanged,
    required this.onConfirm,
    required this.onCancel,
  });

  final Draft draft;
  final String? photoPath;
  final Variant? variant;
  final TextEditingController priceController;
  final bool sending;
  final ValueChanged<String> onPickPrice;
  final ValueChanged<Variant> onPickVariant;
  final VoidCallback onPickOther;
  final VoidCallback onChanged;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final price = parsePrice(priceController.text);
    final ready = price != null && variant != null && !sending;
    final suggested = draft.suggestions.map((s) => s.variant.id).toSet();
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (photoPath != null)
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: SizedBox(
              height: 140,
              child: Image.file(
                File(photoPath!),
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) =>
                    const Center(child: Icon(Icons.image_not_supported)),
              ),
            ),
          ),
        const SizedBox(height: 16),
        Text('Confira o que lemos', style: theme.textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          'Isto é uma sugestão. Corrija o que estiver errado.',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        Text('Preço', style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        if (draft.prices.isEmpty)
          const Text(
            'Não conseguimos ler o preço. Digite o valor que você viu.',
          )
        else
          Wrap(
            spacing: 8,
            children: [
              for (final reading in draft.prices)
                ChoiceChip(
                  label: Text('${reading.raw} · lido na etiqueta'),
                  selected: parsePrice(priceController.text) == reading.value,
                  onSelected: (_) => onPickPrice(reading.value),
                ),
            ],
          ),
        const SizedBox(height: 8),
        TextField(
          controller: priceController,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: 'Preço na etiqueta (R\$)',
            border: const OutlineInputBorder(),
            errorText: priceController.text.isNotEmpty && price == null
                ? 'Informe um valor como 24,90.'
                : null,
          ),
          onChanged: (_) => onChanged(),
        ),
        const SizedBox(height: 24),
        Text('Produto', style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        if (draft.suggestions.isEmpty && variant == null)
          const Text('Não identificamos o produto. Escolha um na busca.'),
        RadioGroup<String>(
          groupValue: variant?.id,
          onChanged: (id) {
            if (id == null) return;
            final match = [
              for (final s in draft.suggestions) s.variant,
              ?variant,
            ].firstWhere((v) => v.id == id);
            onPickVariant(match);
          },
          child: Column(
            children: [
              for (final suggestion in draft.suggestions)
                RadioListTile<String>(
                  value: suggestion.variant.id,
                  title: Text(suggestion.variant.title),
                  subtitle: Text(
                    suggestion.byBarcode
                        ? 'Código de barras lido na etiqueta'
                        : 'Sugestão pelo nome (confira)',
                  ),
                ),
              if (variant != null && !suggested.contains(variant!.id))
                RadioListTile<String>(
                  value: variant!.id,
                  title: Text(variant!.title),
                  subtitle: const Text('Escolhido por você'),
                ),
            ],
          ),
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: onPickOther,
            icon: const Icon(Icons.search),
            label: const Text('Buscar outro produto'),
          ),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: ready ? onConfirm : null,
          child: sending
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Confirmar e enviar'),
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: sending ? null : onCancel,
          child: const Text('Cancelar contribuição'),
        ),
        const SizedBox(height: 8),
        Text(
          'Pode haver diferença no caixa. Só envie o que você viu na loja.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall,
        ),
      ],
    );
  }
}

/// Search the catalog when the suggestion is wrong or missing.
class _ProductPicker extends ConsumerStatefulWidget {
  const _ProductPicker();

  @override
  ConsumerState<_ProductPicker> createState() => _ProductPickerState();
}

class _ProductPickerState extends ConsumerState<_ProductPicker> {
  Future<List<Variant>>? _results;

  void _search(String query) {
    setState(() {
      _results = ref.read(productsRepositoryProvider).search(query);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 16,
        right: 16,
        top: 16,
      ),
      child: SizedBox(
        height: 420,
        child: Column(
          children: [
            TextField(
              autofocus: true,
              textInputAction: TextInputAction.search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar produto ou marca',
                border: OutlineInputBorder(),
              ),
              onSubmitted: _search,
            ),
            const SizedBox(height: 8),
            Expanded(
              child: _results == null
                  ? const Center(child: Text('Digite e toque em buscar.'))
                  : FutureBuilder<List<Variant>>(
                      future: _results,
                      builder: (context, snapshot) {
                        if (snapshot.connectionState != ConnectionState.done) {
                          return const Center(
                            child: CircularProgressIndicator(),
                          );
                        }
                        final list = snapshot.data;
                        if (list == null) {
                          return const Center(
                            child: Text('Não foi possível buscar.'),
                          );
                        }
                        if (list.isEmpty) {
                          return const Center(
                            child: Text('Nenhum produto encontrado.'),
                          );
                        }
                        return ListView(
                          children: [
                            for (final variant in list)
                              ListTile(
                                title: Text(variant.title),
                                onTap: () => Navigator.of(context).pop(variant),
                              ),
                          ],
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
