import 'package:flutter/material.dart';

class Subject {
  final String id;
  final String name;
  final String emoji;
  final Color color;
  final String description;
  final List<String> topics;

  const Subject({
    required this.id,
    required this.name,
    required this.emoji,
    required this.color,
    required this.description,
    required this.topics,
  });

  static const List<Subject> all = [
    Subject(
      id: 'math',
      name: 'Mathematics',
      emoji: '📐',
      color: Color(0xFF1A237E),
      description: 'Numbers, shapes & patterns',
      topics: ['Arithmetic', 'Algebra', 'Geometry', 'Fractions', 'Statistics'],
    ),
    Subject(
      id: 'science',
      name: 'Science',
      emoji: '🔬',
      color: Color(0xFF1B5E20),
      description: 'Explore the natural world',
      topics: ['Physics', 'Chemistry', 'Biology', 'Environment', 'Space'],
    ),
    Subject(
      id: 'english',
      name: 'English',
      emoji: '📚',
      color: Color(0xFF4A148C),
      description: 'Read, write & communicate',
      topics: ['Grammar', 'Comprehension', 'Writing', 'Vocabulary', 'Poetry'],
    ),
    Subject(
      id: 'hindi',
      name: 'Hindi',
      emoji: '🗣️',
      color: Color(0xFFBF360C),
      description: 'हिंदी भाषा सीखें',
      topics: ['व्याकरण', 'पाठ', 'निबंध', 'कविता', 'कहानी'],
    ),
    Subject(
      id: 'history',
      name: 'History',
      emoji: '🏛️',
      color: Color(0xFF4E342E),
      description: "India's rich past & heritage",
      topics: [
        'Ancient India',
        'Medieval India',
        'Freedom Struggle',
        'Modern India',
        'World History',
      ],
    ),
    Subject(
      id: 'geography',
      name: 'Geography',
      emoji: '🗺️',
      color: Color(0xFF006064),
      description: 'Maps, rivers & landscapes',
      topics: ['Maps & Directions', 'Climate', 'Rivers & Mountains', 'Indian States', 'World Geography'],
    ),
  ];
}
