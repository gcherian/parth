import 'package:flutter/material.dart';

import '../models/puzzle.dart';
import '../services/puzzle_service.dart';
import '../theme/app_theme.dart';
import 'home_screen.dart';

// ── Sphere + portrait display constants ───────────────────────────────────────

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

const _sphereColor = {
  'philosophy_logic': Color(0xFF6366F1),
  'mathematics': Color(0xFF3B82F6),
  'physics': Color(0xFF0EA5E9),
  'biology_medicine': Color(0xFF22C55E),
  'chemistry': Color(0xFF84CC16),
  'astronomy_cosmology': Color(0xFFA855F7),
  'computer_science_ai': Color(0xFF06B6D4),
  'social_sciences': Color(0xFFF59E0B),
  'eastern_wisdom': Color(0xFFEC4899),
  'arts_interdisciplinary': Color(0xFFF97316),
};

const _telosEmoji = {
  'explorer': '🔭',
  'builder': '🔧',
  'philosopher': '💭',
  'artist': '🎨',
  'scientist': '🔬',
};

const _telosTitle = {
  'explorer': 'Explorer',
  'builder': 'Builder',
  'philosopher': 'Philosopher',
  'artist': 'Artist',
  'scientist': 'Scientist',
};

const _telosDesc = {
  'explorer':
      'Drawn to discovery. You ask why before how and want the deep reason something is true.',
  'builder':
      'You want to make things work. Doing comes first, and the reason can follow.',
  'philosopher':
      'You question assumptions and care about what should be true, not just what is true.',
  'artist':
      'You look for beauty, pattern, and surprise. Elegant ideas pull you in.',
  'scientist':
      'You want to verify. Evidence matters more than authority, and testing builds trust.',
};

const _errorIcon = {
  'growth': '🌱',
  'fixed': '🧱',
  'avoidant': '🌀',
  'perfectionist': '⭐',
  'unknown': '···',
};

const _errorName = {
  'growth': 'Growth mindset',
  'fixed': 'Fixed mindset',
  'avoidant': 'Avoidant pattern',
  'perfectionist': 'Perfectionist',
  'unknown': 'Observing',
};

const _errorDesc = {
  'growth':
      'Persists through difficulty. Parth can nudge with harder variants.',
  'fixed':
      'Needs competence anchored first. Parth says not yet and shifts strategy.',
  'avoidant':
      'Moves away when stuck. Parth follows the interest and reintroduces the concept indirectly.',
  'perfectionist':
      'Notices the one wrong part. Parth reframes what already worked and keeps moving.',
  'unknown':
      'Parth is still watching how difficulty changes the learning path.',
};

const _fallbackBridge = {
  'explorer': PuzzleBridge(
    domain: '',
    sphere: '',
    probability: 0,
    hook: '4 × (1 - 1/3 + 1/5 - 1/7 + …) = π',
    example:
        'Why does an infinite sum of fractions give the ratio of a circle? That question can become a whole journey.',
    telosFit: ['explorer'],
  ),
  'builder': PuzzleBridge(
    domain: '',
    sphere: '',
    probability: 0,
    hook:
        'Roll a ball forward one full turn. Divide the distance by its diameter.',
    example:
        'The answer is always π. Build the measurement first; the abstraction comes after.',
    telosFit: ['builder'],
  ),
  'philosopher': PuzzleBridge(
    domain: '',
    sphere: '',
    probability: 0,
    hook: 'A discrete sum can describe a continuous circle.',
    example:
        'π raises a strange question: why do counting, infinity, and curved space fit together at all?',
    telosFit: ['philosopher'],
  ),
  'artist': PuzzleBridge(
    domain: '',
    sphere: '',
    probability: 0,
    hook: 'A circle, a spiral, a rhythm, and a wave all keep meeting π.',
    example:
        'Parth starts with the pattern you can see or hear, then reveals the mathematics underneath.',
    telosFit: ['artist'],
  ),
  'scientist': PuzzleBridge(
    domain: '',
    sphere: '',
    probability: 0,
    hook: 'Measure the circumference. Measure the diameter. Divide.',
    example:
        'The same number appears every time. You do not have to believe the textbook before the evidence.',
    telosFit: ['scientist'],
  ),
};

// ── Screen ─────────────────────────────────────────────────────────────────────

class PortraitRevealScreen extends StatefulWidget {
  final String learnerId;
  final String serverUrl;

  const PortraitRevealScreen({
    super.key,
    required this.learnerId,
    required this.serverUrl,
  });

  @override
  State<PortraitRevealScreen> createState() => _PortraitRevealScreenState();
}

class _PortraitRevealScreenState extends State<PortraitRevealScreen>
    with SingleTickerProviderStateMixin {
  final _service = PuzzleService();

  PuzzlePortrait? _portrait;
  PuzzleBridge _bridge = PuzzleBridge.empty;
  bool _loading = true;

  bool _showIntro = false;
  bool _showConfidence = false;
  bool _showTelos = false;
  bool _showError = false;
  bool _showRegister = false;
  bool _showSpheres = false;
  bool _showBridge = false;
  bool _showButton = false;

  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat(reverse: true);
    _pulse = Tween<double>(begin: 0.97, end: 1.03).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
    _load();
  }

  Future<void> _load() async {
    late final PuzzlePortrait portrait;
    try {
      portrait = await _service.getPortrait(
        learnerId: widget.learnerId,
        serverUrl: widget.serverUrl,
      );
    } catch (_) {
      portrait = const PuzzlePortrait(
        learnerId: '',
        primarySphere: '',
        secondarySphere: '',
        zpdLevels: {},
        errorResponse: 'unknown',
        crossDomainCuriosity: 0.5,
        sphereAffinity: {},
        provisionalTelos: 'explorer',
        confidence: 0,
        interactionsUsed: 0,
        grade: 0,
        languageRatio: 1,
        register: PuzzleRegister.empty,
      );
    }

    var bridge = _fallbackBridgeFor(portrait.provisionalTelos);
    if (portrait.learnerId.isNotEmpty) {
      try {
        final fetchedBridge = await _service.getBridge(
          conceptId: 'pi',
          learnerId: widget.learnerId,
          serverUrl: widget.serverUrl,
        );
        if (fetchedBridge.hasContent) bridge = fetchedBridge;
      } catch (_) {}
    }

    if (!mounted) return;
    setState(() {
      _portrait = portrait;
      _bridge = bridge;
      _loading = false;
    });
    await _runRevealSequence();
  }

  Future<void> _runRevealSequence() async {
    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    setState(() => _showIntro = true);

    await Future.delayed(const Duration(milliseconds: 700));
    if (!mounted) return;
    setState(() => _showConfidence = true);

    await Future.delayed(const Duration(milliseconds: 900));
    if (!mounted) return;
    setState(() => _showTelos = true);

    await Future.delayed(const Duration(milliseconds: 650));
    if (!mounted) return;
    setState(() => _showError = true);

    await Future.delayed(const Duration(milliseconds: 650));
    if (!mounted) return;
    setState(() => _showRegister = true);

    await Future.delayed(const Duration(milliseconds: 650));
    if (!mounted) return;
    setState(() => _showSpheres = true);

    await Future.delayed(const Duration(milliseconds: 650));
    if (!mounted) return;
    setState(() => _showBridge = true);

    await Future.delayed(const Duration(milliseconds: 500));
    if (!mounted) return;
    setState(() => _showButton = true);
  }

  PuzzleBridge _fallbackBridgeFor(String telos) =>
      _fallbackBridge[telos] ?? _fallbackBridge['explorer']!;

  void _goHome() {
    Navigator.of(context).pushAndRemoveUntil(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) => const HomeScreen(),
        transitionsBuilder: (_, anim, __, child) =>
            FadeTransition(opacity: anim, child: child),
        transitionDuration: const Duration(milliseconds: 400),
      ),
      (_) => false,
    );
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFF241045), AppTheme.violet, Color(0xFF163A4F)],
          ),
        ),
        child: SafeArea(
          child: _loading
              ? const Center(
                  child: CircularProgressIndicator(color: Colors.white54),
                )
              : _buildReveal(_portrait!),
        ),
      ),
    );
  }

  Widget _buildReveal(PuzzlePortrait portrait) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(22, 34, 22, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          ScaleTransition(
            scale: _pulse,
            child: Container(
              width: 76,
              height: 76,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.12),
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white.withValues(alpha: 0.16)),
              ),
              child: const Center(
                child: Text('🪞', style: TextStyle(fontSize: 36)),
              ),
            ),
          ),
          const SizedBox(height: 22),
          _AnimatedReveal(
            visible: _showIntro,
            child: Column(
              children: [
                const Text(
                  'Portrait Complete',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    height: 1.1,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'From ${_interactionText(portrait.interactionsUsed)}. No form. No test. Just curiosity.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.72),
                    fontSize: 15,
                    height: 1.45,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          _AnimatedReveal(
            visible: _showConfidence,
            slide: 0.08,
            child: _ConfidencePanel(portrait: portrait),
          ),
          const SizedBox(height: 14),
          _AnimatedReveal(
            visible: _showTelos,
            slide: 0.08,
            child: _TelosPanel(telos: portrait.provisionalTelos),
          ),
          const SizedBox(height: 14),
          _AnimatedReveal(
            visible: _showError,
            slide: 0.08,
            child: _ErrorPanel(errorResponse: portrait.errorResponse),
          ),
          const SizedBox(height: 14),
          _AnimatedReveal(
            visible: _showRegister,
            slide: 0.08,
            child: _RegisterPanel(register: portrait.register),
          ),
          const SizedBox(height: 14),
          _AnimatedReveal(
            visible: _showSpheres,
            slide: 0.08,
            child: _SpherePanel(portrait: portrait),
          ),
          const SizedBox(height: 14),
          _AnimatedReveal(
            visible: _showBridge,
            slide: 0.08,
            child: _BridgePanel(bridge: _bridge),
          ),
          const SizedBox(height: 26),
          _AnimatedReveal(
            visible: _showButton,
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.mango,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 18),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(18),
                  ),
                  elevation: 8,
                  shadowColor: AppTheme.mango.withValues(alpha: 0.5),
                  textStyle: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                onPressed: _showButton ? _goHome : null,
                icon: const Icon(Icons.arrow_forward_rounded),
                label: const Text('Continue'),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _interactionText(int interactions) {
    final count = interactions > 0 ? interactions : 5;
    return '$count interaction${count == 1 ? '' : 's'}';
  }
}

class _AnimatedReveal extends StatelessWidget {
  final bool visible;
  final Widget child;
  final double slide;

  const _AnimatedReveal({
    required this.visible,
    required this.child,
    this.slide = 0.12,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      opacity: visible ? 1 : 0,
      duration: const Duration(milliseconds: 560),
      child: AnimatedSlide(
        offset: visible ? Offset.zero : Offset(0, slide),
        duration: const Duration(milliseconds: 560),
        curve: Curves.easeOutCubic,
        child: IgnorePointer(ignoring: !visible, child: child),
      ),
    );
  }
}

class _PortraitCard extends StatelessWidget {
  final Widget child;

  const _PortraitCard({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.18),
          width: 1.2,
        ),
      ),
      child: child,
    );
  }
}

class _ConfidencePanel extends StatelessWidget {
  final PuzzlePortrait portrait;

  const _ConfidencePanel({required this.portrait});

  @override
  Widget build(BuildContext context) {
    final confidence = portrait.confidence.clamp(0.0, 1.0).toDouble();
    final word = confidence < .2
        ? 'LEARNING'
        : confidence < .5
            ? 'FORMING'
            : confidence < .8
                ? 'CONFIDENT'
                : 'SHARP';
    return _PortraitCard(
      child: Row(
        children: [
          SizedBox(
            width: 92,
            height: 92,
            child: Stack(
              alignment: Alignment.center,
              children: [
                SizedBox(
                  width: 82,
                  height: 82,
                  child: CircularProgressIndicator(
                    value: confidence,
                    strokeWidth: 8,
                    backgroundColor: Colors.white.withValues(alpha: 0.14),
                    color: AppTheme.mango,
                  ),
                ),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '${(confidence * 100).round()}%',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 21,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    Text(
                      word,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.56),
                        fontSize: 10,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionLabel('Portrait Confidence'),
                const SizedBox(height: 7),
                Text(
                  '${portrait.interactionsUsed > 0 ? portrait.interactionsUsed : 5} signals shaped this first portrait.',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    height: 1.25,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  'Parth can personalize now, and the portrait will sharpen with every session.',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.68),
                    fontSize: 13,
                    height: 1.45,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TelosPanel extends StatelessWidget {
  final String telos;

  const _TelosPanel({required this.telos});

  @override
  Widget build(BuildContext context) {
    final title = _telosTitle[telos] ?? _telosTitle['explorer']!;
    return _PortraitCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _telosEmoji[telos] ?? _telosEmoji['explorer']!,
            style: const TextStyle(fontSize: 46),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionLabel('Provisional Telos'),
                const SizedBox(height: 8),
                Text(
                  'You are ${_articleFor(title)} $title',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 23,
                    height: 1.15,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 9),
                Text(
                  _telosDesc[telos] ?? _telosDesc['explorer']!,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.72),
                    fontSize: 14,
                    height: 1.5,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  final String errorResponse;

  const _ErrorPanel({required this.errorResponse});

  @override
  Widget build(BuildContext context) {
    final key =
        _errorName.containsKey(errorResponse) ? errorResponse : 'unknown';
    return _PortraitCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 48,
            height: 48,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              _errorIcon[key]!,
              style: const TextStyle(fontSize: 26),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionLabel('Error Response Pattern'),
                const SizedBox(height: 7),
                Text(
                  _errorName[key]!,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 19,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  _errorDesc[key]!,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.7),
                    fontSize: 13,
                    height: 1.45,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RegisterPanel extends StatelessWidget {
  final PuzzleRegister register;

  const _RegisterPanel({required this.register});

  @override
  Widget build(BuildContext context) {
    final bubbles = register.topBubbles;
    return _PortraitCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionLabel('Language Register'),
          const SizedBox(height: 8),
          Text(
            register.dominantDomain.isNotEmpty
                ? 'Parth can bridge through ${register.dominantDomain}.'
                : 'Parth is still finding the language that feels natural.',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              height: 1.25,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 14),
          if (bubbles.isEmpty)
            const _SoftText(
                'Register bubbles will appear as responses accumulate.')
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: bubbles.map((bubble) {
                final color = _colorFromHex(bubble.colorHex);
                return Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: color.withValues(
                        alpha: bubble.isDominant ? 0.28 : 0.14),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                      color: color.withValues(
                          alpha: bubble.isDominant ? 0.85 : 0.45),
                    ),
                  ),
                  child: Text(
                    bubble.domain,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                );
              }).toList(),
            ),
        ],
      ),
    );
  }
}

class _SpherePanel extends StatelessWidget {
  final PuzzlePortrait portrait;

  const _SpherePanel({required this.portrait});

  @override
  Widget build(BuildContext context) {
    final spheres = portrait.sphereAffinity.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final shown = spheres.take(5).toList();
    return _PortraitCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionLabel('Sphere Affinity'),
          const SizedBox(height: 9),
          if (shown.isEmpty)
            const _SoftText(
                'Your curiosity is wide open. The next session will add stronger signals.')
          else
            ...shown.map((entry) {
              final sphere = entry.key;
              final value = entry.value.clamp(0.0, 10.0).toDouble();
              final color = _sphereColor[sphere] ?? AppTheme.sky;
              final level = portrait.zpdLevels[sphere] ?? 'beginner';
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${_sphereEmoji[sphere] ?? '🔍'}  ${_sphereName[sphere] ?? sphere}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        Text(
                          '${value.toStringAsFixed(1)} · $level',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.58),
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(999),
                      child: LinearProgressIndicator(
                        value: value / 10,
                        minHeight: 7,
                        color: color,
                        backgroundColor: Colors.white.withValues(alpha: 0.13),
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

class _BridgePanel extends StatelessWidget {
  final PuzzleBridge bridge;

  const _BridgePanel({required this.bridge});

  @override
  Widget build(BuildContext context) {
    final via = bridge.domain.isNotEmpty ? ' via ${bridge.domain}' : '';
    return _PortraitCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel('How Parth would explain π$via'),
          const SizedBox(height: 10),
          Text(
            bridge.hook.isNotEmpty
                ? bridge.hook
                : 'Parth will choose a bridge from the register that fits you best.',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              height: 1.35,
              fontWeight: FontWeight.w900,
            ),
          ),
          if (bridge.example.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              bridge.example,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.72),
                fontSize: 14,
                height: 1.52,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String label;

  const _SectionLabel(this.label);

  @override
  Widget build(BuildContext context) {
    return Text(
      label.toUpperCase(),
      style: TextStyle(
        color: AppTheme.mango.withValues(alpha: 0.92),
        fontSize: 11,
        letterSpacing: 0.7,
        fontWeight: FontWeight.w900,
      ),
    );
  }
}

class _SoftText extends StatelessWidget {
  final String text;

  const _SoftText(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: Colors.white.withValues(alpha: 0.68),
        fontSize: 13,
        height: 1.45,
        fontWeight: FontWeight.w600,
      ),
    );
  }
}

String _articleFor(String title) {
  final first = title.isEmpty ? '' : title[0].toLowerCase();
  return 'aeiou'.contains(first) ? 'an' : 'a';
}

Color _colorFromHex(String hex) {
  final clean = hex.replaceFirst('#', '');
  try {
    final value = int.parse(clean.length == 6 ? 'FF$clean' : clean, radix: 16);
    return Color(value);
  } catch (_) {
    return AppTheme.sky;
  }
}
