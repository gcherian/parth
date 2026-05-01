import 'package:flutter/material.dart';

import '../models/subject.dart';
import '../theme/app_theme.dart';
import '../widgets/subject_card.dart';
import 'chat_screen.dart';

class SubjectsScreen extends StatefulWidget {
  const SubjectsScreen({super.key});

  @override
  State<SubjectsScreen> createState() => _SubjectsScreenState();
}

class _SubjectsScreenState extends State<SubjectsScreen> {
  Subject? _expanded;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Subjects'),
        automaticallyImplyLeading: false,
      ),
      body: CustomScrollView(
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.all(16),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.05,
              ),
              delegate: SliverChildBuilderDelegate(
                (context, i) {
                  final subj = Subject.all[i];
                  return SubjectCard(
                    subject: subj,
                    isSelected: _expanded?.id == subj.id,
                    onTap: () => setState(
                      () => _expanded = _expanded?.id == subj.id ? null : subj,
                    ),
                  );
                },
                childCount: Subject.all.length,
              ),
            ),
          ),
          if (_expanded != null)
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              sliver: SliverToBoxAdapter(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  child: _TopicsPanel(key: ValueKey(_expanded!.id), subject: _expanded!),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _TopicsPanel extends StatelessWidget {
  final Subject subject;

  const _TopicsPanel({super.key, required this.subject});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: subject.color.withOpacity(0.18)),
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
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: subject.color.withOpacity(0.08),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
            ),
            child: Row(
              children: [
                Text(subject.emoji, style: const TextStyle(fontSize: 20)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    subject.name,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: subject.color,
                    ),
                  ),
                ),
                TextButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => ChatScreen(subject: subject)),
                  ),
                  icon: const Icon(Icons.chat_bubble_outline, size: 15),
                  label: const Text('Study Now'),
                  style: TextButton.styleFrom(
                    foregroundColor: subject.color,
                    textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
          ),
          ...subject.topics.map(
            (topic) => InkWell(
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ChatScreen(
                    subject: subject,
                    initialMessage: 'Explain $topic in simple words with an Indian example.',
                  ),
                ),
              ),
              borderRadius: BorderRadius.circular(8),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                child: Row(
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(color: subject.color, shape: BoxShape.circle),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(topic, style: const TextStyle(fontSize: 14, color: AppTheme.darkText)),
                    ),
                    const Icon(Icons.arrow_forward_ios, size: 12, color: AppTheme.lightText),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}
