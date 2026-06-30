import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/skills_data.dart';
import '../theme/app_theme.dart';
import 'chat_screen.dart';

class SkillPuzzleScreen extends StatefulWidget {
  final SkillCategory category;

  const SkillPuzzleScreen({super.key, required this.category});

  @override
  State<SkillPuzzleScreen> createState() => _SkillPuzzleScreenState();
}

class _SkillPuzzleScreenState extends State<SkillPuzzleScreen>
    with TickerProviderStateMixin {
  late final List<SkillPuzzle> _puzzles;
  int _index = 0;
  int _score = 0;
  int _streak = 0;

  // Answer state
  int? _picked;      // index of tapped option
  bool? _isCorrect;

  // Timer
  static const _timerSeconds = 45;
  int _remaining = _timerSeconds;
  Timer? _timer;

  // Animations
  late AnimationController _shakeCtrl;
  late AnimationController _bounceCtrl;

  @override
  void initState() {
    super.initState();
    _puzzles = List.of(widget.category.puzzles)..shuffle();
    _shakeCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 400));
    _bounceCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 300));
    _startTimer();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _shakeCtrl.dispose();
    _bounceCtrl.dispose();
    super.dispose();
  }

  void _startTimer() {
    _timer?.cancel();
    setState(() => _remaining = _timerSeconds);
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) { t.cancel(); return; }
      if (_isCorrect != null) return; // paused while showing answer
      setState(() => _remaining--);
      if (_remaining <= 0) {
        t.cancel();
        _pick(-1); // time up → wrong
      }
    });
  }

  void _pick(int idx) {
    if (_isCorrect != null) return; // already answered
    _timer?.cancel();

    final puzzle = _puzzles[_index];
    final correct = idx == puzzle.answerIndex;

    HapticFeedback.selectionClick();

    setState(() {
      _picked = idx;
      _isCorrect = correct;
      if (correct) {
        _score++;
        _streak++;
        _bounceCtrl.forward(from: 0);
      } else {
        _streak = 0;
        _shakeCtrl.forward(from: 0);
      }
    });
  }

  Future<void> _next() async {
    if (_index >= _puzzles.length - 1) {
      await _saveScore();
      if (!mounted) return;
      _showResults();
      return;
    }
    setState(() {
      _index++;
      _picked = null;
      _isCorrect = null;
    });
    _startTimer();
  }

  Future<void> _saveScore() async {
    final prefs = await SharedPreferences.getInstance();
    final key = 'skill_best_${widget.category.id}';
    final prev = prefs.getInt(key) ?? 0;
    if (_score > prev) await prefs.setInt(key, _score);
  }

  void _showResults() {
    showModalBottomSheet(
      context: context,
      isDismissible: false,
      enableDrag: false,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _ResultSheet(
        category: widget.category,
        score: _score,
        total: _puzzles.length,
        onRetry: () {
          Navigator.pop(context);
          setState(() {
            _puzzles.shuffle();
            _index = 0;
            _score = 0;
            _streak = 0;
            _picked = null;
            _isCorrect = null;
          });
          _startTimer();
        },
        onDone: () {
          Navigator.pop(context); // close sheet
          Navigator.pop(context); // go back to skills list
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final puzzle = _puzzles[_index];
    final total = _puzzles.length;
    final timerFraction = _remaining / _timerSeconds;

    return Scaffold(
      backgroundColor: AppTheme.cream,
      appBar: AppBar(
        title: Text(widget.category.title),
        backgroundColor: Colors.white,
        elevation: 0,
        actions: [
          // Score badge
          Center(
            child: Container(
              margin: const EdgeInsets.only(right: 16),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
              decoration: BoxDecoration(
                color: AppTheme.deepBlue.withOpacity(0.1),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                '$_score / ${_index + 1}',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: AppTheme.deepBlue,
                ),
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          // ── Progress bar ─────────────────────────────────────────────────
          LinearProgressIndicator(
            value: (_index + 1) / total,
            minHeight: 3,
            backgroundColor: Colors.grey.shade100,
            valueColor:
                const AlwaysStoppedAnimation<Color>(AppTheme.deepBlue),
          ),

          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
              child: Column(
                children: [
                  // ── Timer + question number ───────────────────────────────
                  Row(
                    children: [
                      Text(
                        'Q${_index + 1} of $total',
                        style: const TextStyle(
                            fontSize: 12, color: AppTheme.lightText),
                      ),
                      const Spacer(),
                      _TimerRing(
                        fraction: timerFraction,
                        seconds: _remaining,
                        answered: _isCorrect != null,
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),

                  // ── Streak badge ──────────────────────────────────────────
                  if (_streak >= 2)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: AnimatedBuilder(
                        animation: _bounceCtrl,
                        builder: (_, child) => Transform.scale(
                          scale: 1.0 + _bounceCtrl.value * 0.08,
                          child: child,
                        ),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 6),
                          decoration: BoxDecoration(
                            color: AppTheme.saffron.withOpacity(0.12),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                                color: AppTheme.saffron.withOpacity(0.3)),
                          ),
                          child: Text(
                            '🔥 $_streak in a row!',
                            style: const TextStyle(
                              color: AppTheme.saffron,
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ),
                    ),

                  // ── Question card ─────────────────────────────────────────
                  AnimatedBuilder(
                    animation: _shakeCtrl,
                    builder: (_, child) {
                      final offset = _shakeCtrl.status == AnimationStatus.forward
                          ? ((_shakeCtrl.value * 12) *
                              ((_shakeCtrl.value * 6).round().isEven ? 1 : -1))
                          : 0.0;
                      return Transform.translate(
                        offset: Offset(offset, 0),
                        child: child,
                      );
                    },
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(22),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.06),
                            blurRadius: 12,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: Text(
                        puzzle.question,
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.darkText,
                          height: 1.5,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // ── Options ───────────────────────────────────────────────
                  ...List.generate(puzzle.options.length, (i) {
                    final answered = _isCorrect != null;
                    final isCorrectOption = i == puzzle.answerIndex;
                    final isPicked = i == _picked;

                    Color bgColor = Colors.white;
                    Color borderColor = Colors.grey.shade200;
                    Color textColor = AppTheme.darkText;
                    IconData? trailingIcon;

                    if (answered) {
                      if (isCorrectOption) {
                        bgColor = const Color(0xFFe6f4ec);
                        borderColor = const Color(0xFF2d7a4f);
                        textColor = const Color(0xFF2d7a4f);
                        trailingIcon = Icons.check_circle_rounded;
                      } else if (isPicked) {
                        bgColor = Colors.red.shade50;
                        borderColor = Colors.red.shade300;
                        textColor = Colors.red.shade700;
                        trailingIcon = Icons.cancel_rounded;
                      } else {
                        bgColor = Colors.grey.shade50;
                        textColor = AppTheme.lightText;
                      }
                    }

                    return GestureDetector(
                      onTap: answered ? null : () => _pick(i),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 220),
                        margin: const EdgeInsets.only(bottom: 10),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 18, vertical: 16),
                        decoration: BoxDecoration(
                          color: bgColor,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: borderColor, width: 1.5),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                puzzle.options[i],
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                  color: textColor,
                                ),
                              ),
                            ),
                            if (trailingIcon != null)
                              Icon(trailingIcon,
                                  color: isCorrectOption
                                      ? const Color(0xFF2d7a4f)
                                      : Colors.red.shade400,
                                  size: 22),
                          ],
                        ),
                      ),
                    );
                  }),

                  // ── Explanation (shown after answer) ──────────────────────
                  if (_isCorrect != null) ...[
                    const SizedBox(height: 6),
                    AnimatedOpacity(
                      opacity: _isCorrect != null ? 1 : 0,
                      duration: const Duration(milliseconds: 300),
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: AppTheme.deepBlue.withOpacity(0.05),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                              color: AppTheme.deepBlue.withOpacity(0.12)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('💡 Why?',
                                style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: AppTheme.deepBlue)),
                            const SizedBox(height: 4),
                            Text(
                              puzzle.explanation,
                              style: const TextStyle(
                                  fontSize: 13,
                                  color: AppTheme.darkText,
                                  height: 1.5),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Ask Parth to explain + Next row
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => ChatScreen(
                                  initialMessage:
                                      'Explain this to me: ${puzzle.question}',
                                ),
                              ),
                            ),
                            icon: const Text('🤔', style: TextStyle(fontSize: 15)),
                            label: const Text('Ask Parth'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: AppTheme.deepBlue,
                              side: BorderSide(
                                  color: AppTheme.deepBlue.withOpacity(0.3)),
                              padding: const EdgeInsets.symmetric(vertical: 12),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: ElevatedButton(
                            onPressed: _next,
                            style: ElevatedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                            ),
                            child: Text(
                              _index >= _puzzles.length - 1
                                  ? 'See results'
                                  : 'Next →',
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Timer ring widget ─────────────────────────────────────────────────────────

class _TimerRing extends StatelessWidget {
  final double fraction;
  final int seconds;
  final bool answered;

  const _TimerRing(
      {required this.fraction,
      required this.seconds,
      required this.answered});

  @override
  Widget build(BuildContext context) {
    final color = fraction > 0.5
        ? AppTheme.deepBlue
        : fraction > 0.25
            ? AppTheme.saffron
            : Colors.red;

    return SizedBox(
      width: 42,
      height: 42,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CircularProgressIndicator(
            value: answered ? 0 : fraction,
            strokeWidth: 3.5,
            backgroundColor: Colors.grey.shade200,
            valueColor: AlwaysStoppedAnimation<Color>(
              answered ? Colors.grey.shade200 : color,
            ),
          ),
          Text(
            answered ? '✓' : '$seconds',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: answered ? Colors.grey.shade300 : color,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Results bottom sheet ──────────────────────────────────────────────────────

class _ResultSheet extends StatelessWidget {
  final SkillCategory category;
  final int score;
  final int total;
  final VoidCallback onRetry;
  final VoidCallback onDone;

  const _ResultSheet({
    required this.category,
    required this.score,
    required this.total,
    required this.onRetry,
    required this.onDone,
  });

  String get _resultEmoji {
    final pct = score / total;
    if (pct == 1.0) return '🏆';
    if (pct >= 0.8) return '🌟';
    if (pct >= 0.6) return '👍';
    return '💪';
  }

  String get _resultMessage {
    final pct = score / total;
    if (pct == 1.0) return 'Perfect! You aced it!';
    if (pct >= 0.8) return 'Excellent work!';
    if (pct >= 0.6) return 'Good job! Keep going.';
    if (pct >= 0.4) return 'Not bad — try again?';
    return 'Keep practising — you\'ll get there.';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_resultEmoji, style: const TextStyle(fontSize: 56)),
          const SizedBox(height: 12),
          Text(
            _resultMessage,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: AppTheme.darkText,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '$score out of $total correct',
            style: const TextStyle(fontSize: 15, color: AppTheme.lightText),
          ),
          const SizedBox(height: 24),
          // Score bar
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: score / total,
              minHeight: 12,
              backgroundColor: Colors.grey.shade100,
              valueColor: const AlwaysStoppedAnimation<Color>(AppTheme.saffron),
            ),
          ),
          const SizedBox(height: 28),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: onRetry,
                  child: const Text('Try again'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  onPressed: onDone,
                  child: const Text('Done ✓'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
