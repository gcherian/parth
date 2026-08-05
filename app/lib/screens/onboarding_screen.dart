import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../services/puzzle_service.dart';
import '../theme/app_theme.dart';
import '../utils/server_config.dart';
import 'puzzle_onboarding_screen.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _service = PuzzleService();
  final _nameController = TextEditingController();
  int _grade = 6; // default to Grade 6 — deck's primary target
  bool _loading = false;

  // Step 1 = child name/grade; Step 2 = parent consent (required, not a nudge)
  int _step = 1;
  String _learnerId = '';
  String _serverUrl = '';
  bool _consenting = false;
  String? _consentError;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _saveChildAndAdvance() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter your name!'),
          backgroundColor: AppTheme.saffron,
        ),
      );
      return;
    }

    setState(() => _loading = true);
    final prefs = await SharedPreferences.getInstance();

    final existingId = prefs.getString('learner_id');
    final id = (existingId == null || existingId.isEmpty)
        ? const Uuid().v4()
        : existingId;
    await prefs.setString('learner_id', id);
    await prefs.setString('user_name', name);
    await prefs.setInt('grade', _grade);

    final savedUrl = prefs.getString('server_url') ?? '';
    final serverUrl = resolveServerUrl(savedUrl);
    if (serverUrl != savedUrl) await prefs.setString('server_url', serverUrl);

    setState(() {
      _learnerId = id;
      _serverUrl = serverUrl;
      _loading = false;
      _step = 2;
    });
  }

  /// The consent gate: nothing about this child is collected — no puzzle
  /// probes, no data — until this succeeds. /learner/consent must be called
  /// before /puzzle/next or /puzzle/respond will accept anything for this
  /// learner_id.
  Future<void> _grantConsentAndBegin() async {
    final prefs = await SharedPreferences.getInstance();

    // No server configured — nothing is collected anywhere yet, so there's
    // nothing to gate. Match the existing "skip puzzle onboarding when no
    // server configured" behavior rather than blocking on an unreachable call.
    if (_serverUrl.isEmpty) {
      await prefs.setBool('onboarded', true);
      if (!mounted) return;
      _navigateToPuzzles();
      return;
    }

    setState(() {
      _consenting = true;
      _consentError = null;
    });
    try {
      await _service.grantConsent(
        learnerId: _learnerId,
        name: _nameController.text.trim(),
        grade: _grade,
        serverUrl: _serverUrl,
      );
      await prefs.setBool('onboarded', true);
      if (!mounted) return;
      _navigateToPuzzles();
    } catch (e) {
      setState(() {
        _consenting = false;
        _consentError = 'Could not save consent. Please check your connection and try again.';
      });
    }
  }

  void _navigateToPuzzles() {
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) => const PuzzleOnboardingScreen(),
        transitionsBuilder: (_, anim, __, child) =>
            FadeTransition(opacity: anim, child: child),
        transitionDuration: const Duration(milliseconds: 350),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [AppTheme.cream, Colors.white],
          ),
        ),
        child: SafeArea(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 320),
            child: _step == 1 ? _buildChildStep() : _buildParentNudgeStep(),
          ),
        ),
      ),
    );
  }

  // ── Step 1: child name + grade ────────────────────────────────────────────
  Widget _buildChildStep() {
    return Padding(
      key: const ValueKey('step1'),
      padding: const EdgeInsets.fromLTRB(28, 24, 28, 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Center(child: Text('🙏', style: TextStyle(fontSize: 60))),
          const SizedBox(height: 20),
          const Center(
            child: Text(
              'Namaste!',
              style: TextStyle(
                fontSize: 34,
                fontWeight: FontWeight.bold,
                color: AppTheme.deepBlue,
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Center(
            child: Text(
              "I'm Parth, your personal AI mentor.\nLet's get to know each other!",
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 15, color: AppTheme.lightText, height: 1.55),
            ),
          ),
          const SizedBox(height: 36),
          const Text(
            "What's your name?",
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.darkText),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(
              hintText: 'Enter your name…',
              prefixIcon: Icon(Icons.person_outline, color: AppTheme.deepBlue),
            ),
            textCapitalization: TextCapitalization.words,
            autofocus: true,
          ),
          const SizedBox(height: 24),
          const Text(
            'Which grade are you in?',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.darkText),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: List.generate(5, (i) {
              final g = i + 6; // Grades 6–10
              final selected = _grade == g;
              return GestureDetector(
                onTap: () => setState(() => _grade = g),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: selected ? AppTheme.deepBlue : Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: selected ? AppTheme.deepBlue : Colors.grey.shade300,
                    ),
                    boxShadow: selected
                        ? [
                            BoxShadow(
                              color: AppTheme.deepBlue.withOpacity(0.3),
                              blurRadius: 8,
                              offset: const Offset(0, 2),
                            ),
                          ]
                        : [],
                  ),
                  child: Center(
                    child: Text(
                      'Gr $g',
                      style: TextStyle(
                        color: selected ? Colors.white : AppTheme.darkText,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ),
              );
            }),
          ),
          const Spacer(),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _loading ? null : _saveChildAndAdvance,
              child: _loading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                    )
                  : const Text('Next →'),
            ),
          ),
        ],
      ),
    );
  }

  // ── Step 2: parent invite nudge ───────────────────────────────────────────
  Widget _buildParentNudgeStep() {
    final shortCode = _learnerId.isNotEmpty
        ? _learnerId.substring(0, 8).toUpperCase()
        : '--------';

    return Padding(
      key: const ValueKey('step2'),
      padding: const EdgeInsets.fromLTRB(28, 32, 28, 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Center(
            child: Text('👨‍👩‍👧', style: TextStyle(fontSize: 60)),
          ),
          const SizedBox(height: 20),
          const Center(
            child: Text(
              'Tell your parent about Parth',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: AppTheme.deepBlue,
              ),
            ),
          ),
          const SizedBox(height: 12),
          const Center(
            child: Text(
              'Parth works best when a parent is involved.\nThey can follow your progress and be your guide — without being a tutor.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: AppTheme.lightText, height: 1.6),
            ),
          ),
          const SizedBox(height: 32),
          // Share code card
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
            decoration: BoxDecoration(
              color: AppTheme.deepBlue.withOpacity(0.05),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppTheme.deepBlue.withOpacity(0.15)),
            ),
            child: Column(
              children: [
                const Text(
                  'Your join code',
                  style: TextStyle(fontSize: 13, color: AppTheme.lightText),
                ),
                const SizedBox(height: 8),
                Text(
                  shortCode,
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.deepBlue,
                    letterSpacing: 4,
                  ),
                ),
                const SizedBox(height: 12),
                GestureDetector(
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: shortCode));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Code copied! Share it with your parent.'),
                        duration: Duration(seconds: 2),
                      ),
                    );
                  },
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.copy_rounded,
                          size: 16, color: AppTheme.deepBlue.withOpacity(0.6)),
                      const SizedBox(width: 6),
                      Text(
                        'Copy code',
                        style: TextStyle(
                          fontSize: 13,
                          color: AppTheme.deepBlue.withOpacity(0.7),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Center(
            child: Text(
              'Your parent enters this code at parth.ai/parent to get started.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
                color: AppTheme.lightText.withOpacity(0.7),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.deepBlue.withOpacity(0.04),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              'Parent or guardian: by tapping below, you agree to let '
              '${_nameController.text.trim().isEmpty ? "your child" : _nameController.text.trim()} '
              'use Parth, including AI conversations and progress tracking. '
              'You can review or withdraw this anytime from the parent dashboard.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: AppTheme.darkText.withOpacity(0.85), height: 1.5),
            ),
          ),
          if (_consentError != null) ...[
            const SizedBox(height: 12),
            Text(
              _consentError!,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13, color: Colors.red),
            ),
          ],
          const Spacer(),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _consenting ? null : _grantConsentAndBegin,
              child: _consenting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                    )
                  : const Text('I agree — let\'s begin →'),
            ),
          ),
        ],
      ),
    );
  }
}
