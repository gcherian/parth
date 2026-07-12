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
        title: const Text('My Learning'),
        automaticallyImplyLeading: false,
      ),
      body: messages.isEmpty
          ? const _EmptyState()
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const _LearningFrameCard(),
                const SizedBox(height: 16),
                _StatsRow(questions: userCount, answers: aiCount),
                const SizedBox(height: 16),
                if (subjectCounts.isNotEmpty) ...[
                  _SubjectPieChart(subjectCounts: subjectCounts),
                  const SizedBox(height: 16),
                ],
                _LearningSignalsCard(
                    questions: userCount, subjects: subjectCounts.length),
                const SizedBox(height: 24),
              ],
            ),
    );
  }
}

class _LearningFrameCard extends StatelessWidget {
  const _LearningFrameCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.deepBlue.withAlpha(31)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(13),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Marks show the result. Understanding explains the result.',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w800,
              color: AppTheme.darkText,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Parth tracks what you understood, what needs another try, and what should be tested again before school tests.',
            style: TextStyle(
                fontSize: 13, color: AppTheme.lightText, height: 1.45),
          ),
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
            label: 'Questions\nUnpacked',
            value: '$questions',
            icon: Icons.help_outline_rounded,
            color: AppTheme.saffron,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatTile(
            label: 'Answers\nTested',
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
        color: color.withAlpha(18),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withAlpha(46)),
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
          Text(label,
              style: const TextStyle(
                  fontSize: 12, color: AppTheme.lightText, height: 1.3)),
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
            color: Colors.black.withAlpha(13),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Subjects Connected',
            style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.bold,
                color: AppTheme.darkText),
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
                    decoration: BoxDecoration(
                        color: subj.color, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '${subj.name} (${e.value})',
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.lightText),
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

class _LearningSignalsCard extends StatelessWidget {
  final int questions;
  final int subjects;

  const _LearningSignalsCard({required this.questions, required this.subjects});

  List<_Signal> get _signals => [
        _Signal(
          icon: Icons.psychology_alt_outlined,
          title: 'Understanding map',
          desc: questions == 0
              ? 'Parth needs a few questions to see how you think.'
              : 'Parth is learning which explanations make concepts click.',
          active: questions >= 1,
        ),
        _Signal(
          icon: Icons.replay_circle_filled_outlined,
          title: 'Recall to test again',
          desc: questions >= 5
              ? 'Some ideas should be checked later so they stick for tests.'
              : 'After a few more questions, Parth can start planning recall.',
          active: questions >= 5,
        ),
        _Signal(
          icon: Icons.school_outlined,
          title: 'School readiness',
          desc: subjects >= 1
              ? 'Your school result improves when weak steps are found early.'
              : 'Choose a subject to begin building test readiness.',
          active: subjects >= 1,
        ),
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
            color: Colors.black.withAlpha(13),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Learning Signals',
            style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.bold,
                color: AppTheme.darkText),
          ),
          const SizedBox(height: 8),
          ..._signals.map((signal) {
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: signal.active
                          ? AppTheme.saffron.withAlpha(26)
                          : Colors.grey.shade50,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: signal.active
                            ? AppTheme.saffron.withAlpha(77)
                            : Colors.grey.shade200,
                      ),
                    ),
                    child: Center(
                      child: Icon(
                        signal.icon,
                        color: signal.active
                            ? AppTheme.saffron
                            : AppTheme.lightText,
                        size: 22,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          signal.title,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: signal.active
                                ? AppTheme.darkText
                                : AppTheme.lightText,
                          ),
                        ),
                        Text(
                          signal.desc,
                          style: TextStyle(
                            fontSize: 12,
                            color: signal.active
                                ? AppTheme.lightText
                                : AppTheme.lightText.withAlpha(153),
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (signal.active)
                    const Icon(Icons.check_circle_rounded,
                        color: AppTheme.success, size: 20),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _Signal {
  final IconData icon;
  final String title;
  final String desc;
  final bool active;

  const _Signal({
    required this.icon,
    required this.title,
    required this.desc,
    required this.active,
  });
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
            'No learning map yet',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppTheme.darkText,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Start with one school topic.\nParth will map what is clear and what needs testing again.',
            textAlign: TextAlign.center,
            style:
                TextStyle(fontSize: 14, color: AppTheme.lightText, height: 1.5),
          ),
        ],
      ),
    );
  }
}
