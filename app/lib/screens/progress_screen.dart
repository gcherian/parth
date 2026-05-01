import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/subject.dart';
import '../providers/chat_provider.dart';
import '../theme/app_theme.dart';

class ProgressScreen extends ConsumerWidget {
  const ProgressScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final messages = ref.watch(chatProvider).messages;
    final userCount = messages.where((m) => m.isUser).length;
    final aiCount = messages.length - userCount;

    final subjectCounts = <String, int>{};
    for (final msg in messages) {
      if (msg.subject != null) {
        subjectCounts[msg.subject!] = (subjectCounts[msg.subject!] ?? 0) + 1;
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Progress'),
        automaticallyImplyLeading: false,
      ),
      body: messages.isEmpty
          ? const _EmptyState()
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _StatsRow(questions: userCount, answers: aiCount),
                const SizedBox(height: 16),
                if (subjectCounts.isNotEmpty) ...[
                  _SubjectPieChart(subjectCounts: subjectCounts),
                  const SizedBox(height: 16),
                ],
                _AchievementsList(questions: userCount),
                const SizedBox(height: 24),
              ],
            ),
    );
  }
}

class _StatsRow extends StatelessWidget {
  final int questions;
  final int answers;

  const _StatsRow({required this.questions, required this.answers});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _StatTile(
            label: 'Questions\nAsked',
            value: '$questions',
            icon: Icons.help_outline_rounded,
            color: AppTheme.saffron,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatTile(
            label: 'Answers\nReceived',
            value: '$answers',
            icon: Icons.lightbulb_outline_rounded,
            color: AppTheme.deepBlue,
          ),
        ),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatTile({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withOpacity(0.07),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 26),
          const SizedBox(height: 10),
          Text(
            value,
            style: TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(fontSize: 12, color: AppTheme.lightText, height: 1.3)),
        ],
      ),
    );
  }
}

class _SubjectPieChart extends StatelessWidget {
  final Map<String, int> subjectCounts;

  const _SubjectPieChart({required this.subjectCounts});

  @override
  Widget build(BuildContext context) {
    final entries = subjectCounts.entries.toList();
    final total = entries.fold<int>(0, (s, e) => s + e.value);

    Subject _find(String id) => Subject.all.firstWhere(
          (s) => s.id == id,
          orElse: () => Subject.all.first,
        );

    return Container(
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Topics Explored',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.darkText),
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 190,
            child: PieChart(
              PieChartData(
                sections: entries.map((e) {
                  final subj = _find(e.key);
                  final pct = e.value / total;
                  return PieChartSectionData(
                    color: subj.color,
                    value: e.value.toDouble(),
                    title: '${(pct * 100).round()}%',
                    radius: 64,
                    titleStyle: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  );
                }).toList(),
                sectionsSpace: 2,
                centerSpaceRadius: 42,
              ),
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 14,
            runSpacing: 8,
            children: entries.map((e) {
              final subj = _find(e.key);
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(color: subj.color, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '${subj.name} (${e.value})',
                    style: const TextStyle(fontSize: 12, color: AppTheme.lightText),
                  ),
                ],
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _AchievementsList extends StatelessWidget {
  final int questions;

  const _AchievementsList({required this.questions});

  static const _achievements = [
    (emoji: '🌱', title: 'First Step', desc: 'Asked your first question', threshold: 1),
    (emoji: '🔍', title: 'Curious Mind', desc: 'Asked 10 questions', threshold: 10),
    (emoji: '📚', title: 'Scholar', desc: 'Asked 25 questions', threshold: 25),
    (emoji: '🏆', title: 'Knowledge Seeker', desc: 'Asked 50 questions', threshold: 50),
    (emoji: '⭐', title: 'Wisdom Master', desc: 'Asked 100 questions', threshold: 100),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Achievements',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.darkText),
          ),
          const SizedBox(height: 8),
          ..._achievements.map((a) {
            final unlocked = questions >= a.threshold;
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: unlocked
                          ? AppTheme.saffron.withOpacity(0.1)
                          : Colors.grey.shade100,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Center(
                      child: Text(
                        unlocked ? a.emoji : '🔒',
                        style: const TextStyle(fontSize: 20),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          a.title,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: unlocked ? AppTheme.darkText : AppTheme.lightText,
                          ),
                        ),
                        Text(
                          a.desc,
                          style: const TextStyle(fontSize: 12, color: AppTheme.lightText),
                        ),
                      ],
                    ),
                  ),
                  if (unlocked)
                    const Icon(Icons.check_circle_rounded, color: AppTheme.success, size: 20),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('📊', style: TextStyle(fontSize: 60)),
          SizedBox(height: 16),
          Text(
            'No progress yet!',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppTheme.darkText,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Start chatting with Parth to track\nyour learning journey!',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 14, color: AppTheme.lightText, height: 1.5),
          ),
        ],
      ),
    );
  }
}
