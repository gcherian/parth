import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../models/message.dart';
import '../models/subject.dart';
import '../services/ai_service.dart';
import '../utils/server_config.dart';

class ChatState {
  final List<Message> messages;
  final bool isLoading;
  final Subject? currentSubject;
  final String? error;
  final String? serverUrl;
  final String learnerId;
  final String learnerName;
  final int grade;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    this.currentSubject,
    this.error,
    this.serverUrl,
    this.learnerId = 'anonymous',
    this.learnerName = '',
    this.grade = 6,
  });

  ChatState copyWith({
    List<Message>? messages,
    bool? isLoading,
    Subject? currentSubject,
    String? error,
    bool clearError = false,
    String? serverUrl,
    bool clearServerUrl = false,
    String? learnerId,
    String? learnerName,
    int? grade,
  }) => ChatState(
    messages: messages ?? this.messages,
    isLoading: isLoading ?? this.isLoading,
    currentSubject: currentSubject ?? this.currentSubject,
    error: clearError ? null : error ?? this.error,
    serverUrl: clearServerUrl ? null : serverUrl ?? this.serverUrl,
    learnerId: learnerId ?? this.learnerId,
    learnerName: learnerName ?? this.learnerName,
    grade: grade ?? this.grade,
  );

  bool get usingLocalServer => serverUrl != null && serverUrl!.isNotEmpty;
}

class ChatNotifier extends StateNotifier<ChatState> {
  final AiService _ai;
  final _uuid = const Uuid();
  late final Future<void> _initFuture;

  ChatNotifier(this._ai) : super(const ChatState()) {
    _initFuture = _init();
  }

  Future<void> _init() async {
    _loadHistory();
    await _loadServerUrl();
    await _loadLearnerIdentity();
  }

  void _loadHistory() {
    final box = Hive.box('messages');
    final raw = box.get('chat_history', defaultValue: <dynamic>[]) as List;
    final msgs = raw
        .map((e) => Message.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    state = state.copyWith(messages: msgs);
  }

  Future<void> _loadServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('server_url') ?? '';
    final url = resolveServerUrl(saved);
    if (url != saved) await prefs.setString('server_url', url);
    state = state.copyWith(serverUrl: url);
  }

  Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_url', url.trim());
    state = state.copyWith(serverUrl: url.trim());
  }

  Future<void> _loadLearnerIdentity() async {
    final prefs = await SharedPreferences.getInstance();
    // Generate a stable ID if somehow onboarding was skipped.
    var id = prefs.getString('learner_id') ?? '';
    if (id.isEmpty) {
      id = const Uuid().v4();
      await prefs.setString('learner_id', id);
    }
    final name = prefs.getString('user_name') ?? '';
    final grade = prefs.getInt('grade') ?? 6;
    state = state.copyWith(learnerId: id, learnerName: name, grade: grade);
  }

  void _persist(List<Message> messages) {
    Hive.box(
      'messages',
    ).put('chat_history', messages.map((m) => m.toJson()).toList());
  }

  void setSubject(Subject subject) {
    state = state.copyWith(currentSubject: subject, clearError: true);
  }

  Future<void> sendMessage(String content) async {
    if (content.trim().isEmpty) return;
    await _initFuture;

    final userMsg = Message(
      id: _uuid.v4(),
      content: content.trim(),
      isUser: true,
      timestamp: DateTime.now(),
      subject: state.currentSubject?.id,
    );

    final withUser = [...state.messages, userMsg];
    state = state.copyWith(
      messages: withUser,
      isLoading: true,
      clearError: true,
    );

    try {
      final reply = await _ai.sendMessage(
        userMessage: content,
        history: state.messages,
        subject: state.currentSubject?.name ?? 'General',
        localServerUrl: state.serverUrl,
        learnerId: state.learnerId,
        learnerName: state.learnerName,
        grade: state.grade,
      );

      final aiMsg = Message(
        id: _uuid.v4(),
        content: reply,
        isUser: false,
        timestamp: DateTime.now(),
        subject: state.currentSubject?.id,
      );

      final finalMsgs = [...withUser, aiMsg];
      state = state.copyWith(messages: finalMsgs, isLoading: false);
      _persist(finalMsgs);
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString().replaceFirst('Exception: ', ''),
      );
    }
  }

  void clearChat() {
    state = ChatState(
      serverUrl: state.serverUrl,
      learnerId: state.learnerId,
      learnerName: state.learnerName,
      grade: state.grade,
      currentSubject: state.currentSubject,
    );
    _persist([]);
  }
}

final aiServiceProvider = Provider<AiService>((ref) => AiService());

final chatProvider = StateNotifierProvider<ChatNotifier, ChatState>((ref) {
  return ChatNotifier(ref.watch(aiServiceProvider));
});
