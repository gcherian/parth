import 'package:flutter/material.dart';

import '../models/puzzle.dart';
import '../services/puzzle_service.dart';
import '../theme/app_theme.dart';
import 'home_screen.dart';

// ── Sphere + telos display constants ──────────────────────────────────────────

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

const _telosEmoji = {
  'explorer': '🧭',
  'builder': '🔨',
  'philosopher': '💭',
  'artist': '🎨',
  'scientist': '🔬',
};

const _telosTitle = {
  'explorer': 'The Explorer',
  'builder': 'The Builder',
  'philosopher': 'The Philosopher',
  'artist': 'The Artist',
  'scientist': 'The Scientist',
};

const _telosDesc = {
  'explorer':
      'You love discovery, asking why, and following curiosity wherever it leads.',
  'builder':
      'You love creating things, solving problems, and making ideas real.',
  'philosopher':
      'You love deep questions, ideas, and understanding the world beneath the surface.',
  'artist':
      'You love beauty, patterns, and expressing what you see and feel.',
  'scientist':
      'You love evidence, experiments, and finding out how things really work.',
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
  bool _loading = true;

  // Staged animation flags
  bool _showIntro = false;
  bool _showTelos = false;
  bool _showSpheres = false;
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
    try {
      final portrait = await _service.getPortrait(
        learnerId: widget.learnerId,
        serverUrl: widget.serverUrl,
      );
      setState(() {
        _portrait = portrait;
        _loading = false;
      });
    } catch (_) {
      // Show a graceful fallback portrait if the server is unavailable
      setState(() {
        _portrait = const PuzzlePortrait(
          primarySphere: '',
          sphereAffinity: {},
          provisionalTelos: 'explorer',
        );
        _loading = false;
      });
    }
    await _runRevealSequence();
  }

  Future<void> _runRevealSequence() async {
    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    setState(() => _showIntro = true);

    await Future.delayed(const Duration(milliseconds: 1200));
    if (!mounted) return;
    setState(() => _showTelos = true);

    await Future.delayed(const Duration(milliseconds: 800));
    if (!mounted) return;
    setState(() => _showSpheres = true);

    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    setState(() => _showButton = true);
  }

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
            colors: [Color(0xFF2D0B6B), AppTheme.violet, Color(0xFF4A2080)],
          ),
        ),
        child: SafeArea(
          child: _loading
              ? const Center(
                  child: CircularProgressIndicator(color: Colors.white54))
              : _buildReveal(),
        ),
      ),
    );
  }

  Widget _buildReveal() {
    final telos = _portrait!.provisionalTelos;
    final topSpheres = _portrait!.topSpheres;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(28, 40, 28, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Owl icon
          ScaleTransition(
            scale: _pulse,
            child: Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.12),
                shape: BoxShape.circle,
              ),
              child: const Center(
                  child: Text('🦉', style: TextStyle(fontSize: 40))),
            ),
          ),
          const SizedBox(height: 24),

          // Intro text
          AnimatedOpacity(
            opacity: _showIntro ? 1 : 0,
            duration: const Duration(milliseconds: 600),
            child: const Text(
              'Parth has been watching\nhow you think.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white70,
                fontSize: 16,
                height: 1.5,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          const SizedBox(height: 32),

          // Telos card
          AnimatedOpacity(
            opacity: _showTelos ? 1 : 0,
            duration: const Duration(milliseconds: 700),
            child: AnimatedSlide(
              offset: _showTelos ? Offset.zero : const Offset(0, 0.15),
              duration: const Duration(milliseconds: 600),
              curve: Curves.easeOutCubic,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(28),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(28),
                  border: Border.all(
                      color: Colors.white.withOpacity(0.18), width: 1.5),
                ),
                child: Column(
                  children: [
                    Text(
                      _telosEmoji[telos] ?? '🧭',
                      style: const TextStyle(fontSize: 52),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      (_telosTitle[telos] ?? 'The Explorer').toUpperCase(),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 1.5,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _telosDesc[telos] ??
                          'You love discovery and asking why.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.82),
                        fontSize: 15,
                        height: 1.55,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

          const SizedBox(height: 28),

          // Sphere chips
          AnimatedOpacity(
            opacity: _showSpheres ? 1 : 0,
            duration: const Duration(milliseconds: 600),
            child: AnimatedSlide(
              offset:
                  _showSpheres ? Offset.zero : const Offset(0, 0.1),
              duration: const Duration(milliseconds: 500),
              curve: Curves.easeOutCubic,
              child: Column(
                children: [
                  Text(
                    topSpheres.isNotEmpty
                        ? 'Your curiosity pulls toward…'
                        : 'Your curiosity is wide open.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.65),
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    alignment: WrapAlignment.center,
                    children: topSpheres.map((e) {
                      final sphere = e.key;
                      return Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 10),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.14),
                          borderRadius: BorderRadius.circular(30),
                          border: Border.all(
                              color: Colors.white.withOpacity(0.25)),
                        ),
                        child: Text(
                          '${_sphereEmoji[sphere] ?? '🔍'}  ${_sphereName[sphere] ?? sphere}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 48),

          // CTA button
          AnimatedOpacity(
            opacity: _showButton ? 1 : 0,
            duration: const Duration(milliseconds: 500),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.mango,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 18),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(24)),
                  elevation: 8,
                  shadowColor: AppTheme.mango.withOpacity(0.5),
                  textStyle: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w800),
                ),
                onPressed: _showButton ? _goHome : null,
                child: const Text('Let\'s learn together! 🚀'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
