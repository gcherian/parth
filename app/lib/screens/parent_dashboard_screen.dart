import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../providers/chat_provider.dart';
import '../theme/app_theme.dart';

class ParentDashboardScreen extends ConsumerStatefulWidget {
  const ParentDashboardScreen({super.key});

  @override
  ConsumerState<ParentDashboardScreen> createState() =>
      _ParentDashboardScreenState();
}

class _ParentDashboardScreenState extends ConsumerState<ParentDashboardScreen> {
  Map<String, dynamic>? _report;
  Map<String, dynamic>? _psyche;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    final chatState = ref.read(chatProvider);
    final learnerId = chatState.learnerId;
    final serverUrl = chatState.serverUrl ?? '';

    if (serverUrl.isEmpty) {
      setState(() {
        _error = 'No server URL configured. Go to Settings to add one.';
        _loading = false;
      });
      return;
    }

    final base = serverUrl.endsWith('/')
        ? serverUrl.substring(0, serverUrl.length - 1)
        : serverUrl;

    try {
      // Fetch report and psyche in parallel
      final results = await Future.wait([
        http
            .get(Uri.parse('$base/parent/$learnerId/report'))
            .timeout(const Duration(seconds: 15)),
        http
            .get(Uri.parse('$base/learner/$learnerId/psyche'))
            .timeout(const Duration(seconds: 10)),
      ]);

      if (results[0].statusCode == 200) {
        setState(() {
          _report = jsonDecode(results[0].body) as Map<String, dynamic>;
          if (results[1].statusCode == 200) {
            _psyche = jsonDecode(results[1].body) as Map<String, dynamic>;
          }
          _loading = false;
        });
      } else {
        setState(() {
          _error = 'Server returned ${results[0].statusCode}';
          _loading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Could not reach server: $e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Parent Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_outlined),
            onPressed: _fetch,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _ErrorView(message: _error!, onRetry: _fetch)
              : _ReportView(report: _report!, psyche: _psyche),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined,
                size: 64, color: AppTheme.lightText),
            const SizedBox(height: 16),
            Text(message,
                textAlign: TextAlign.center,
                style:
                    const TextStyle(color: AppTheme.lightText, fontSize: 14)),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReportView extends StatelessWidget {
  final Map<String, dynamic> report;
  final Map<String, dynamic>? psyche;

  const _ReportView({required this.report, this.psyche});

  @override
  Widget build(BuildContext context) {
    final name = report['learner_name'] as String? ?? 'Your child';
    final grade = report['grade'] as int? ?? 6;
    final totalQ = report['total_questions'] as int? ?? 0;
    final subjects =
        (report['subjects_covered'] as List?)?.cast<String>() ?? [];
    final strong =
        (report['strong_concepts'] as List?)?.cast<Map<String, dynamic>>() ??
            [];
    final weak =
        (report['weak_concepts'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final alerts =
        (report['recent_alerts'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final emotions = (report['recent_emotions'] as List?)?.cast<String>() ?? [];
    final readiness =
        (report['school_readiness'] as Map?)?.cast<String, dynamic>() ?? {};
    final ledger =
        (report['learning_ledger'] as Map?)?.cast<String, dynamic>() ?? {};
    final readinessScore = (readiness['score'] as num?)?.toInt() ?? 0;
    final readinessLabel = readiness['label'] as String? ?? 'Needs diagnostic';
    final topRisks =
        (readiness['top_risks'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final recallDue =
        (readiness['recall_due'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final recentMisconceptions = (ledger['recent_misconceptions'] as List?)
            ?.cast<Map<String, dynamic>>() ??
        [];
    final preferredAnchors =
        (ledger['preferred_anchors'] as List?)?.cast<Map<String, dynamic>>() ??
            [];

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        // ── Header card ────────────────────────────────────────────────────
        _Card(
          child: Row(
            children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: AppTheme.deepBlue,
                child: Text(
                  name.isNotEmpty ? name[0].toUpperCase() : 'S',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.bold),
                ),
              ),
              const SizedBox(width: 16),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name,
                      style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: AppTheme.darkText)),
                  Text('Grade $grade',
                      style: const TextStyle(
                          fontSize: 14, color: AppTheme.lightText)),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // ── Stats row ──────────────────────────────────────────────────────
        Row(
          children: [
            _StatTile(
                icon: Icons.quiz_outlined, label: 'Signals', value: '$totalQ'),
            const SizedBox(width: 12),
            _StatTile(
                icon: Icons.school_outlined,
                label: 'Readiness',
                value: '$readinessScore%'),
            const SizedBox(width: 12),
            _StatTile(
                icon: Icons.replay_circle_filled_outlined,
                label: 'Recall due',
                value: '${readiness['recall_due_count'] ?? recallDue.length}'),
          ],
        ),
        const SizedBox(height: 16),

        _ReadinessCard(
          score: readinessScore,
          label: readinessLabel,
          focus: readiness['test_focus'] as String? ?? '',
          topRisks: topRisks,
        ),
        const SizedBox(height: 16),

        _LearningLedgerCard(
          ledger: ledger,
          recentMisconceptions: recentMisconceptions,
          preferredAnchors: preferredAnchors,
        ),
        const SizedBox(height: 16),

        if (recallDue.isNotEmpty) ...[
          _SectionTitle('Recall Before It Fades'),
          const SizedBox(height: 8),
          ...recallDue.map((c) => _RecallTile(card: c)),
          const SizedBox(height: 16),
        ],

        // ── MBTI personality type ──────────────────────────────────────────
        if (psyche != null) ...[
          _MbtiCard(psyche: psyche!),
          const SizedBox(height: 16),
        ],

        // ── Recent mood ────────────────────────────────────────────────────
        if (emotions.isNotEmpty) ...[
          _SectionTitle('Recent Mood'),
          const SizedBox(height: 8),
          _Card(
            child: Wrap(
              spacing: 8,
              children: emotions
                  .map((e) => Chip(
                        label: Text(_emojiFor(e) + ' $e'),
                        backgroundColor: _colorFor(e).withAlpha(30),
                        labelStyle:
                            TextStyle(color: _colorFor(e), fontSize: 12),
                      ))
                  .toList(),
            ),
          ),
          const SizedBox(height: 16),
        ],

        // ── Subjects ───────────────────────────────────────────────────────
        if (subjects.isNotEmpty) ...[
          _SectionTitle('Subjects Studied'),
          const SizedBox(height: 8),
          _Card(
            child: Wrap(
              spacing: 8,
              children: subjects
                  .map((s) => Chip(
                        label: Text(s),
                        backgroundColor: AppTheme.deepBlue.withAlpha(20),
                        labelStyle: const TextStyle(
                            color: AppTheme.deepBlue, fontSize: 12),
                      ))
                  .toList(),
            ),
          ),
          const SizedBox(height: 16),
        ],

        // ── Mastery ────────────────────────────────────────────────────────
        if (strong.isNotEmpty) ...[
          _SectionTitle('Mastered Topics'),
          const SizedBox(height: 8),
          ...strong.map((c) => _ConceptRow(
                concept: c['concept_id'] as String,
                mastery: (c['p_mastery'] as num).toDouble(),
                color: AppTheme.success,
              )),
          const SizedBox(height: 16),
        ],

        if (weak.isNotEmpty) ...[
          _SectionTitle('Needs More Practice'),
          const SizedBox(height: 8),
          ...weak.map((c) => _ConceptRow(
                concept: c['concept_id'] as String,
                mastery: (c['p_mastery'] as num).toDouble(),
                color: AppTheme.saffron,
              )),
          const SizedBox(height: 16),
        ],

        // ── Alerts ─────────────────────────────────────────────────────────
        if (alerts.isNotEmpty) ...[
          _SectionTitle('Alerts'),
          const SizedBox(height: 8),
          ...alerts.map((a) => _AlertTile(alert: a)),
          const SizedBox(height: 16),
        ],

        if (totalQ == 0)
          const _Card(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'No learning sessions yet. Start with one school chapter so Parth can estimate readiness and the causes behind it.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppTheme.lightText, fontSize: 13),
              ),
            ),
          ),
      ],
    );
  }

  String _emojiFor(String emotion) => switch (emotion) {
        'excited' => '🤩',
        'confused' => '🤔',
        'disengaged' => '😴',
        'neutral' => '😊',
        _ => '😊',
      };

  Color _colorFor(String emotion) => switch (emotion) {
        'excited' => AppTheme.success,
        'confused' => AppTheme.saffron,
        'disengaged' => Colors.red,
        _ => AppTheme.deepBlue,
      };
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
          fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.darkText),
    );
  }
}

class _ReadinessCard extends StatelessWidget {
  final int score;
  final String label;
  final String focus;
  final List<Map<String, dynamic>> topRisks;

  const _ReadinessCard({
    required this.score,
    required this.label,
    required this.focus,
    required this.topRisks,
  });

  @override
  Widget build(BuildContext context) {
    final color = score >= 75
        ? AppTheme.success
        : score >= 55
            ? AppTheme.saffron
            : AppTheme.coral;

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.school_outlined,
                  color: AppTheme.deepBlue, size: 20),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'School Readiness',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.darkText,
                  ),
                ),
              ),
              Text(
                label,
                style: TextStyle(
                    fontSize: 12, color: color, fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Text(
                '$score%',
                style: TextStyle(
                  fontSize: 34,
                  fontWeight: FontWeight.w900,
                  color: color,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: (score / 100).clamp(0.0, 1.0),
                    minHeight: 8,
                    backgroundColor: color.withAlpha(30),
                    valueColor: AlwaysStoppedAnimation(color),
                  ),
                ),
              ),
            ],
          ),
          if (focus.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              focus,
              style: const TextStyle(
                  fontSize: 13, color: AppTheme.lightText, height: 1.45),
            ),
          ],
          if (topRisks.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text(
              'First risks to fix',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: AppTheme.darkText,
              ),
            ),
            const SizedBox(height: 6),
            ...topRisks.map((risk) => _RiskLine(risk: risk)),
          ],
        ],
      ),
    );
  }
}

class _LearningLedgerCard extends StatelessWidget {
  final Map<String, dynamic> ledger;
  final List<Map<String, dynamic>> recentMisconceptions;
  final List<Map<String, dynamic>> preferredAnchors;

  const _LearningLedgerCard({
    required this.ledger,
    required this.recentMisconceptions,
    required this.preferredAnchors,
  });

  @override
  Widget build(BuildContext context) {
    final conceptsTracked = ledger['concepts_tracked'] as int? ?? 0;
    final misconceptionCount = ledger['misconceptions_seen'] as int? ?? 0;
    final explanation = ledger['explanation'] as String? ??
        'Parth tracks mastery, recall, misconceptions, and examples that actually land.';

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.insights_outlined, color: AppTheme.deepBlue, size: 20),
              SizedBox(width: 8),
              Text(
                'Learning Ledger',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.darkText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            explanation,
            style: const TextStyle(
                fontSize: 13, color: AppTheme.lightText, height: 1.45),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _MiniMetric(label: 'Concepts', value: '$conceptsTracked'),
              const SizedBox(width: 10),
              _MiniMetric(
                  label: 'Misconceptions', value: '$misconceptionCount'),
            ],
          ),
          if (recentMisconceptions.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text(
              'Recent causes behind wrong marks',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: AppTheme.darkText,
              ),
            ),
            const SizedBox(height: 6),
            ...recentMisconceptions.map((m) => Text(
                  '- ${(m['misconception'] as String?) ?? ''}',
                  style:
                      const TextStyle(fontSize: 12, color: AppTheme.lightText),
                )),
          ],
          if (preferredAnchors.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: preferredAnchors
                  .map((a) => Chip(
                        label: Text((a['anchor'] as String? ?? '')
                            .replaceAll('_', ' ')),
                        backgroundColor: AppTheme.saffron.withAlpha(24),
                        labelStyle: const TextStyle(
                            color: AppTheme.darkText, fontSize: 12),
                      ))
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class _MiniMetric extends StatelessWidget {
  final String label;
  final String value;

  const _MiniMetric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: AppTheme.cardBg,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value,
                style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.darkText)),
            Text(label,
                style:
                    const TextStyle(fontSize: 11, color: AppTheme.lightText)),
          ],
        ),
      ),
    );
  }
}

class _RiskLine extends StatelessWidget {
  final Map<String, dynamic> risk;

  const _RiskLine({required this.risk});

  @override
  Widget build(BuildContext context) {
    final concept = (risk['concept_id'] as String? ?? '').replaceAll('_', ' ');
    final mastery = ((risk['p_mastery'] as num?)?.toDouble() ?? 0.0) * 100;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        '$concept - ${mastery.round()}% ready',
        style: const TextStyle(fontSize: 12, color: AppTheme.lightText),
      ),
    );
  }
}

class _RecallTile extends StatelessWidget {
  final Map<String, dynamic> card;

  const _RecallTile({required this.card});

  @override
  Widget build(BuildContext context) {
    final concept = (card['concept_id'] as String? ?? '').replaceAll('_', ' ');
    final reps = card['repetitions'] as int? ?? 0;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: _Card(
        child: Row(
          children: [
            const Icon(Icons.replay_circle_filled_outlined,
                color: AppTheme.saffron, size: 22),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                concept,
                style: const TextStyle(fontSize: 13, color: AppTheme.darkText),
              ),
            ),
            Text(
              '$reps recalls',
              style: const TextStyle(fontSize: 11, color: AppTheme.lightText),
            ),
          ],
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final Widget child;
  const _Card({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(13),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _StatTile(
      {required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: _Card(
        child: Column(
          children: [
            Icon(icon, color: AppTheme.deepBlue, size: 22),
            const SizedBox(height: 6),
            Text(value,
                style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.darkText)),
            const SizedBox(height: 2),
            Text(label,
                style:
                    const TextStyle(fontSize: 11, color: AppTheme.lightText)),
          ],
        ),
      ),
    );
  }
}

class _ConceptRow extends StatelessWidget {
  final String concept;
  final double mastery;
  final Color color;

  const _ConceptRow(
      {required this.concept, required this.mastery, required this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(concept.replaceAll('_', ' '),
                style: const TextStyle(fontSize: 14, color: AppTheme.darkText)),
          ),
          const SizedBox(width: 12),
          SizedBox(
            width: 80,
            child: LinearProgressIndicator(
              value: mastery.clamp(0.0, 1.0),
              backgroundColor: color.withAlpha(40),
              valueColor: AlwaysStoppedAnimation(color),
              minHeight: 6,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const SizedBox(width: 8),
          Text('${(mastery * 100).toInt()}%',
              style: TextStyle(
                  fontSize: 12, color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _MbtiCard extends StatelessWidget {
  final Map<String, dynamic> psyche;
  const _MbtiCard({required this.psyche});

  @override
  Widget build(BuildContext context) {
    final mbti = psyche['mbti'] as Map<String, dynamic>?;
    final sampleCount = psyche['sample_count'] as int? ?? 0;

    if (mbti == null || mbti['type'] == null) {
      return _Card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.psychology_outlined,
                    color: AppTheme.deepBlue, size: 20),
                SizedBox(width: 8),
                Text('Personality Profile',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.darkText)),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              'Building profile… $sampleCount interactions so far. '
              'Needs 15 to estimate type.',
              style: const TextStyle(fontSize: 13, color: AppTheme.lightText),
            ),
            const SizedBox(height: 6),
            LinearProgressIndicator(
              value: (sampleCount / 15.0).clamp(0.0, 1.0),
              backgroundColor: AppTheme.deepBlue.withAlpha(30),
              valueColor: const AlwaysStoppedAnimation(AppTheme.deepBlue),
              minHeight: 5,
              borderRadius: BorderRadius.circular(3),
            ),
          ],
        ),
      );
    }

    final typeCode = mbti['type'] as String;
    final typeName = mbti['name'] as String? ?? '';
    final confidence = mbti['confidence'] as String? ?? 'low';
    final examples = (mbti['examples'] as List?)?.cast<String>() ?? [];
    final pedagogy = mbti['pedagogy'] as String? ?? '';

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.psychology_outlined,
                  color: AppTheme.deepBlue, size: 20),
              const SizedBox(width: 8),
              const Text('Personality Profile',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.darkText)),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppTheme.deepBlue.withAlpha(20),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(confidence,
                    style: const TextStyle(
                        fontSize: 11, color: AppTheme.deepBlue)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(typeCode,
                  style: const TextStyle(
                      fontSize: 42,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.deepBlue,
                      letterSpacing: 4)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(typeName,
                    style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.darkText)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (pedagogy.isNotEmpty)
            Text(pedagogy,
                style: const TextStyle(
                    fontSize: 13, color: AppTheme.lightText, height: 1.5)),
          if (examples.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text('Famous ${typeCode}s:',
                style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.darkText)),
            const SizedBox(height: 4),
            Text(examples.join(' · '),
                style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.lightText,
                    fontStyle: FontStyle.italic)),
          ],
          const SizedBox(height: 10),
          Text(
            mbti['note'] as String? ?? '',
            style: const TextStyle(fontSize: 11, color: AppTheme.lightText),
          ),
        ],
      ),
    );
  }
}

class _AlertTile extends StatelessWidget {
  final Map<String, dynamic> alert;

  const _AlertTile({required this.alert});

  @override
  Widget build(BuildContext context) {
    final type = alert['alert_type'] as String? ?? '';
    final message = alert['message'] as String? ?? '';
    final acknowledged = alert['acknowledged'] as bool? ?? false;

    final isStruggling = type == 'struggling';
    final color = isStruggling ? AppTheme.saffron : AppTheme.success;
    final icon = isStruggling
        ? Icons.warning_amber_outlined
        : Icons.emoji_events_outlined;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: color.withAlpha(20),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withAlpha(80)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(message,
                      style: const TextStyle(
                          fontSize: 13, color: AppTheme.darkText)),
                  if (acknowledged)
                    const Text('Acknowledged',
                        style:
                            TextStyle(fontSize: 11, color: AppTheme.lightText)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
