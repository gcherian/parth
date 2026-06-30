import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/skills_data.dart';
import '../theme/app_theme.dart';
import 'skill_puzzle_screen.dart';

class SkillsScreen extends StatefulWidget {
  const SkillsScreen({super.key});

  @override
  State<SkillsScreen> createState() => _SkillsScreenState();
}

class _SkillsScreenState extends State<SkillsScreen> {
  // best score per category — stored as "skill_best_<id>"
  final Map<String, int> _best = {};

  @override
  void initState() {
    super.initState();
    _loadScores();
  }

  Future<void> _loadScores() async {
    final prefs = await SharedPreferences.getInstance();
    final scores = <String, int>{};
    for (final cat in allSkillCategories) {
      scores[cat.id] = prefs.getInt('skill_best_${cat.id}') ?? 0;
    }
    if (mounted) setState(() => _best.addAll(scores));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 140,
            pinned: true,
            automaticallyImplyLeading: false,
            flexibleSpace: FlexibleSpaceBar(
              background: Container(
                decoration: const BoxDecoration(gradient: AppTheme.heroGradient),
                child: const SafeArea(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(22, 20, 22, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Text(
                          '⚡ Skills',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 28,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        SizedBox(height: 4),
                        Text(
                          'Train your mind — one puzzle at a time',
                          style: TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 80),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                const _DailyChallengeBanner(),
                const SizedBox(height: 20),
                const Text(
                  'Choose a skill to practise',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppTheme.darkText,
                  ),
                ),
                const SizedBox(height: 12),
                ...allSkillCategories.map((cat) => _CategoryCard(
                      category: cat,
                      bestScore: _best[cat.id] ?? 0,
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => SkillPuzzleScreen(category: cat),
                          ),
                        );
                        _loadScores(); // refresh scores on return
                      },
                    )),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Daily challenge banner ────────────────────────────────────────────────────

class _DailyChallengeBanner extends StatelessWidget {
  const _DailyChallengeBanner();

  @override
  Widget build(BuildContext context) {
    // Pick a category based on day of week for the "daily" feel
    final todayCat = allSkillCategories[DateTime.now().weekday % allSkillCategories.length];
    return GestureDetector(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => SkillPuzzleScreen(category: todayCat)),
      ),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF1a3a6b), Color(0xFF2d5fa3)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(18),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF1a3a6b).withOpacity(0.3),
              blurRadius: 14,
              offset: const Offset(0, 5),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.15),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Center(
                child: Text(todayCat.emoji,
                    style: const TextStyle(fontSize: 26)),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "Today's Challenge",
                    style: TextStyle(
                      color: Colors.white60,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    todayCat.title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${todayCat.puzzles.length} puzzles',
                    style: const TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                ],
              ),
            ),
            const Icon(Icons.play_circle_fill_rounded,
                color: Colors.white, size: 34),
          ],
        ),
      ),
    );
  }
}

// ── Category card ─────────────────────────────────────────────────────────────

class _CategoryCard extends StatelessWidget {
  final SkillCategory category;
  final int bestScore;
  final VoidCallback onTap;

  const _CategoryCard({
    required this.category,
    required this.bestScore,
    required this.onTap,
  });

  Color get _accentColor {
    switch (category.id) {
      case 'numbers': return const Color(0xFF2d7a4f);
      case 'verbal':  return const Color(0xFF5b4fcf);
      case 'logic':   return const Color(0xFFd97706);
      case 'odd_one_out': return const Color(0xFFe8762a);
      case 'teasers': return const Color(0xFF1a3a6b);
      default:        return AppTheme.deepBlue;
    }
  }

  @override
  Widget build(BuildContext context) {
    final total = category.puzzles.length;
    final progress = bestScore / total;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.05),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: _accentColor.withOpacity(0.1),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Center(
                child: Text(category.emoji,
                    style: const TextStyle(fontSize: 26)),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    category.title,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.darkText,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    category.tagline,
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.lightText),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: progress.clamp(0.0, 1.0),
                            minHeight: 5,
                            backgroundColor: Colors.grey.shade100,
                            valueColor:
                                AlwaysStoppedAnimation<Color>(_accentColor),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        bestScore == 0
                            ? '${total} puzzles'
                            : 'Best: $bestScore/$total',
                        style: TextStyle(
                          fontSize: 11,
                          color: bestScore == 0
                              ? AppTheme.lightText
                              : _accentColor,
                          fontWeight: bestScore == 0
                              ? FontWeight.normal
                              : FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Icon(Icons.chevron_right_rounded,
                color: Colors.grey.shade300, size: 22),
          ],
        ),
      ),
    );
  }
}
