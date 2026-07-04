import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../models/puzzle.dart';
import '../services/puzzle_service.dart';
import '../theme/app_theme.dart';
import 'portrait_reveal_screen.dart';

// ── Sphere metadata ────────────────────────────────────────────────────────────

const _sphereEmoji = {
  'philosophy_logic': '🧠',
  'mathematics': '∑',
  'physics': '⚡',
  'biology_medicine': '🌿',
  'chemistry': '⚗️',
  'astronomy_cosmology': '🌌',
  'computer_science_ai': '💻',
  'social_sciences': '🏛️',
  'eastern_wisdom': '☯️',
  'arts_interdisciplinary': '🎨',
};

const _sphereName = {
  'philosophy_logic': 'Philosophy & Logic',
  'mathematics': 'Mathematics',
  'physics': 'Physics',
  'biology_medicine': 'Biology & Medicine',
  'chemistry': 'Chemistry',
  'astronomy_cosmology': 'Astronomy & Space',
  'computer_science_ai': 'Technology & AI',
  'social_sciences': 'Social Sciences',
  'eastern_wisdom': 'Eastern Wisdom',
  'arts_interdisciplinary': 'Arts & Humanities',
};

String _sphereLabel(String sphere) =>
    '${_sphereEmoji[sphere] ?? '🔍'}  ${_sphereName[sphere] ?? sphere}';

// ── Screen ─────────────────────────────────────────────────────────────────────

class PuzzleOnboardingScreen extends StatefulWidget {
  const PuzzleOnboardingScreen({super.key});

  @override
  State<PuzzleOnboardingScreen> createState() => _PuzzleOnboardingScreenState();
}

class _PuzzleOnboardingScreenState extends State<PuzzleOnboardingScreen> {
  final _service = PuzzleService();
  final _responseCtrl = TextEditingController();

  String _learnerId = '';
  String _serverUrl = '';
  int _grade = 6;

  int _probeIndex = 0; // 0-4
  ColdStartProbe? _probe;
  bool _loadingProbe = true;
  String? _error;
  DateTime _probeStart = DateTime.now();

  // Puzzle card state
  bool _submitting = false;
  bool _submitted = false;
  bool _revealed = false;
  bool _completing = false;
  String? _completionError;

  // Choice card state — ID currently being processed
  String? _processingId;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final prefs = await SharedPreferences.getInstance();
    _learnerId = prefs.getString('learner_id') ?? '';
    if (_learnerId.isEmpty) {
      _learnerId = const Uuid().v4();
      await prefs.setString('learner_id', _learnerId);
    }
    _serverUrl = prefs.getString('server_url') ?? '';
    _grade = prefs.getInt('grade') ?? 6;
    await _fetchProbe();
  }

  Future<void> _fetchProbe() async {
    setState(() {
      _loadingProbe = true;
      _error = null;
    });
    try {
      final probe = await _service.nextPuzzle(
        learnerId: _learnerId,
        grade: _grade,
        serverUrl: _serverUrl,
      );
      setState(() {
        _probe = probe;
        _loadingProbe = false;
        _probeStart = DateTime.now();
        _submitted = false;
        _revealed = false;
        _processingId = null;
        _completionError = null;
        _responseCtrl.clear();
      });
    } catch (e) {
      setState(() {
        _loadingProbe = false;
        _error = _serverUrl.isEmpty
            ? 'No server configured. Please go to Settings and add the server URL.'
            : 'Could not reach Parth server. Check your connection.';
      });
    }
  }

  Future<void> _onChoicePicked(PuzzleHookOption option) async {
    setState(() => _processingId = option.puzzleId);
    try {
      await _service.respond(
        learnerId: _learnerId,
        puzzleId: option.puzzleId,
        response: 'I chose this one',
        timeSeconds: DateTime.now().difference(_probeStart).inSeconds,
        reachedDeeper: false,
        grade: _grade,
        serverUrl: _serverUrl,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _processingId = null);
      _showError('Could not save that choice. Please try again.');
      return;
    }
    _advance();
  }

  Future<void> _onPuzzleSubmit() async {
    final text = _responseCtrl.text.trim();
    if (text.isEmpty) return;
    setState(() => _submitting = true);
    try {
      await _service.respond(
        learnerId: _learnerId,
        puzzleId: _probe!.puzzle!.id,
        response: text,
        timeSeconds: DateTime.now().difference(_probeStart).inSeconds,
        reachedDeeper: false,
        grade: _grade,
        serverUrl: _serverUrl,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _submitting = false);
      _showError('Could not save your response. Please try again.');
      return;
    }
    setState(() {
      _submitting = false;
      _submitted = true;
    });
  }

  void _onReveal() => setState(() => _revealed = true);

  void _advance() {
    if (_probeIndex >= 4) {
      _completeColdStart();
      return;
    }
    setState(() => _probeIndex++);
    _fetchProbe();
  }

  Future<void> _completeColdStart() async {
    if (_completing) return;
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _completing = true;
      _completionError = null;
    });

    final name = prefs.getString('user_name') ?? '';
    final grade = prefs.getInt('grade') ?? _grade;
    try {
      await _service.registerLearner(
        learnerId: _learnerId,
        name: name,
        grade: grade,
        serverUrl: _serverUrl,
      );
      await prefs.setBool('learner_registered', true);
      await prefs.setBool('cold_start_done', true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _completing = false;
        _completionError =
            'Could not finish setup. Check your connection and try again.';
      });
      return;
    }

    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => PortraitRevealScreen(
        learnerId: _learnerId,
        serverUrl: _serverUrl,
      ),
    ));
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: AppTheme.saffron,
      ),
    );
  }

  @override
  void dispose() {
    _responseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgWarm,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _TopBar(probeIndex: _probeIndex),
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 380),
                transitionBuilder: (child, anim) => FadeTransition(
                  opacity: anim,
                  child: SlideTransition(
                    position: Tween<Offset>(
                            begin: const Offset(0.04, 0), end: Offset.zero)
                        .animate(anim),
                    child: child,
                  ),
                ),
                child: _loadingProbe
                    ? const _LoadingCard(key: ValueKey('loading'))
                    : _error != null
                        ? _ErrorCard(
                            key: const ValueKey('error'),
                            message: _error!,
                            onRetry: _fetchProbe,
                          )
                        : _probe!.mode == ProbeMode.choice
                            ? _ChoiceCard(
                                key: ValueKey('choice_$_probeIndex'),
                                probe: _probe!,
                                processingId: _processingId,
                                onChoose: _processingId != null
                                    ? null
                                    : _onChoicePicked,
                              )
                            : _PuzzleCard(
                                key: ValueKey('puzzle_$_probeIndex'),
                                probe: _probe!,
                                controller: _responseCtrl,
                                submitted: _submitted,
                                revealed: _revealed,
                                submitting: _submitting,
                                onSubmit: (_submitting || _submitted)
                                    ? null
                                    : _onPuzzleSubmit,
                                onReveal: _onReveal,
                                onNext:
                                    _revealed && !_completing ? _advance : null,
                                nextBusy: _completing,
                                nextLabel:
                                    _probeIndex >= 4 ? 'Enter Parth' : 'Next →',
                                errorText: _completionError,
                              ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Top bar with progress dots ─────────────────────────────────────────────────

class _TopBar extends StatelessWidget {
  final int probeIndex;
  const _TopBar({required this.probeIndex});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Parth is getting to know you',
            style: TextStyle(
              color: AppTheme.bodyText,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.3,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: List.generate(5, (i) {
              final done = i < probeIndex;
              final active = i == probeIndex;
              return Padding(
                padding: const EdgeInsets.only(right: 8),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  curve: Curves.easeOut,
                  width: active ? 28 : 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: done || active
                        ? AppTheme.violet
                        : AppTheme.violet.withOpacity(0.18),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              );
            }),
          ),
        ],
      ),
    );
  }
}

// ── Loading card ───────────────────────────────────────────────────────────────

class _LoadingCard extends StatelessWidget {
  const _LoadingCard({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: AppTheme.violet),
          SizedBox(height: 20),
          Text(
            'Parth is thinking…',
            style: TextStyle(color: AppTheme.bodyText, fontSize: 15),
          ),
        ],
      ),
    );
  }
}

// ── Error card ─────────────────────────────────────────────────────────────────

class _ErrorCard extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorCard({super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🔌', style: TextStyle(fontSize: 48)),
            const SizedBox(height: 16),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: AppTheme.bodyText, fontSize: 15, height: 1.5),
            ),
            const SizedBox(height: 24),
            ElevatedButton(onPressed: onRetry, child: const Text('Try again')),
          ],
        ),
      ),
    );
  }
}

// ── Choice card ────────────────────────────────────────────────────────────────

class _ChoiceCard extends StatelessWidget {
  final ColdStartProbe probe;
  final String? processingId;
  final void Function(PuzzleHookOption)? onChoose;

  const _ChoiceCard({
    super.key,
    required this.probe,
    required this.processingId,
    required this.onChoose,
  });

  @override
  Widget build(BuildContext context) {
    final optA = probe.optionA;
    final optB = probe.optionB;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            probe.instruction ?? 'Which of these makes you more curious?',
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: AppTheme.darkText,
              height: 1.35,
            ),
          ),
          const SizedBox(height: 24),
          if (optA != null)
            _ChoiceOption(
              option: optA,
              loading: processingId == optA.puzzleId,
              disabled: processingId != null,
              onTap: onChoose != null ? () => onChoose!(optA) : null,
            ),
          const SizedBox(height: 16),
          Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                color: AppTheme.violet.withOpacity(0.08),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Text(
                'OR',
                style: TextStyle(
                  color: AppTheme.violet,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1,
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          if (optB != null)
            _ChoiceOption(
              option: optB,
              loading: processingId == optB.puzzleId,
              disabled: processingId != null,
              onTap: onChoose != null ? () => onChoose!(optB) : null,
            ),
        ],
      ),
    );
  }
}

class _ChoiceOption extends StatelessWidget {
  final PuzzleHookOption option;
  final bool loading;
  final bool disabled;
  final VoidCallback? onTap;

  const _ChoiceOption({
    required this.option,
    required this.loading,
    required this.disabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: disabled ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        decoration: BoxDecoration(
          color: loading ? AppTheme.violet.withOpacity(0.06) : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: loading
                ? AppTheme.violet
                : disabled
                    ? Colors.grey.shade200
                    : AppTheme.violet.withOpacity(0.22),
            width: loading ? 2 : 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: AppTheme.violet.withOpacity(disabled ? 0 : 0.07),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _sphereLabel(option.sphere),
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: AppTheme.violet.withOpacity(0.7),
                letterSpacing: 0.5,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              option.hook,
              style: TextStyle(
                fontSize: 15,
                height: 1.55,
                color: disabled && !loading
                    ? AppTheme.lightText
                    : AppTheme.darkText,
                fontStyle: FontStyle.italic,
              ),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerRight,
              child: loading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: AppTheme.violet),
                    )
                  : Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color:
                            disabled ? Colors.grey.shade100 : AppTheme.violet,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        'This one →',
                        style: TextStyle(
                          color: disabled ? AppTheme.lightText : Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Puzzle card ────────────────────────────────────────────────────────────────

class _PuzzleCard extends StatelessWidget {
  final ColdStartProbe probe;
  final TextEditingController controller;
  final bool submitted;
  final bool revealed;
  final bool submitting;
  final VoidCallback? onSubmit;
  final VoidCallback onReveal;
  final VoidCallback? onNext;
  final bool nextBusy;
  final String nextLabel;
  final String? errorText;

  const _PuzzleCard({
    super.key,
    required this.probe,
    required this.controller,
    required this.submitted,
    required this.revealed,
    required this.submitting,
    required this.onSubmit,
    required this.onReveal,
    required this.onNext,
    required this.nextBusy,
    required this.nextLabel,
    required this.errorText,
  });

  @override
  Widget build(BuildContext context) {
    final puzzle = probe.puzzle;
    if (puzzle == null) return const SizedBox.shrink();

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Sphere badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(
              color: AppTheme.violet.withOpacity(0.08),
              borderRadius: BorderRadius.circular(30),
            ),
            child: Text(
              _sphereLabel(puzzle.sphere),
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: AppTheme.violet,
                letterSpacing: 0.3,
              ),
            ),
          ),

          const SizedBox(height: 20),

          // Hook
          Text(
            puzzle.hook,
            style: const TextStyle(
              fontSize: 18,
              fontStyle: FontStyle.italic,
              height: 1.55,
              color: AppTheme.darkText,
              fontWeight: FontWeight.w600,
            ),
          ),

          // Optional special instruction (bridge probes)
          if (probe.specialInstruction != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppTheme.mango.withOpacity(0.08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                    color: AppTheme.mango.withOpacity(0.25), width: 1),
              ),
              child: Text(
                '✨  ${probe.specialInstruction}',
                style: const TextStyle(
                  fontSize: 13,
                  color: AppTheme.darkText,
                  height: 1.5,
                ),
              ),
            ),
          ],

          const SizedBox(height: 20),

          // Challenge box
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: AppTheme.cardBg,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'THE CHALLENGE',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    color: AppTheme.lightText,
                    letterSpacing: 1.2,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  puzzle.challenge,
                  style: const TextStyle(
                    fontSize: 15,
                    height: 1.6,
                    color: AppTheme.darkText,
                  ),
                ),
                if (puzzle.materials.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    '🛠  ${puzzle.materials}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppTheme.lightText,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ],
              ],
            ),
          ),

          const SizedBox(height: 20),

          // Response input (hidden after submit)
          AnimatedCrossFade(
            duration: const Duration(milliseconds: 300),
            crossFadeState: submitted
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            firstChild: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: controller,
                  decoration: const InputDecoration(
                    hintText: 'What do you think? Write anything…',
                  ),
                  maxLines: 4,
                  minLines: 3,
                  textInputAction: TextInputAction.newline,
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: onSubmit,
                    child: submitting
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                color: Colors.white, strokeWidth: 2),
                          )
                        : const Text('Submit'),
                  ),
                ),
              ],
            ),
            secondChild: const SizedBox.shrink(),
          ),

          // Discover button (shown after submit, before reveal)
          if (submitted && !revealed) ...[
            const SizedBox(height: 8),
            _GlowButton(
              label: 'Discover ✨',
              onTap: onReveal,
            ),
          ],

          // Discover reveal (slides in after tap)
          AnimatedSize(
            duration: const Duration(milliseconds: 450),
            curve: Curves.easeOutCubic,
            child: revealed
                ? _DiscoverReveal(
                    text: puzzle.discover,
                    followUp: probe.followUp,
                    onNext: onNext,
                    nextBusy: nextBusy,
                    nextLabel: nextLabel,
                    errorText: errorText,
                  )
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}

// ── Glow button (for Discover) ─────────────────────────────────────────────────

class _GlowButton extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  const _GlowButton({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [AppTheme.mint, Color(0xFF00A87A)],
          ),
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: AppTheme.mint.withOpacity(0.4),
              blurRadius: 16,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Text(
          label,
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 17,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.3,
          ),
        ),
      ),
    );
  }
}

// ── Discover reveal ────────────────────────────────────────────────────────────

class _DiscoverReveal extends StatelessWidget {
  final String text;
  final String? followUp;
  final VoidCallback? onNext;
  final bool nextBusy;
  final String nextLabel;
  final String? errorText;

  const _DiscoverReveal({
    required this.text,
    required this.followUp,
    required this.onNext,
    required this.nextBusy,
    required this.nextLabel,
    required this.errorText,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                AppTheme.mint.withOpacity(0.10),
                AppTheme.violet.withOpacity(0.06),
              ],
            ),
            borderRadius: BorderRadius.circular(20),
            border:
                Border.all(color: AppTheme.mint.withOpacity(0.35), width: 1.5),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'DISCOVER',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  color: AppTheme.mint,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                text,
                style: const TextStyle(
                  fontSize: 15,
                  height: 1.65,
                  color: AppTheme.darkText,
                ),
              ),
              if (followUp != null) ...[
                const SizedBox(height: 14),
                Text(
                  '💭  $followUp',
                  style: const TextStyle(
                    fontSize: 14,
                    fontStyle: FontStyle.italic,
                    color: AppTheme.bodyText,
                    height: 1.5,
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        if (errorText != null) ...[
          Text(
            errorText!,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppTheme.saffron,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
        ],
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: onNext,
            child: nextBusy
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                        color: Colors.white, strokeWidth: 2),
                  )
                : Text(nextLabel),
          ),
        ),
      ],
    );
  }
}
