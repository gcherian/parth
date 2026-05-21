import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/message.dart';

class AiService {
  // ── Local Parth server (primary) ───────────────────────────────────────────
  Future<String> sendToLocal({
    required String serverUrl,
    required String userMessage,
    required List<Message> history,
    required String subject,
    String learnerId = 'anonymous',
    String learnerName = '',
    int grade = 6,
    int attempt = 0,
  }) async {
    final base = serverUrl.endsWith('/')
        ? serverUrl.substring(0, serverUrl.length - 1)
        : serverUrl;

    final historyJson = history.takeLast(16).map((m) => {
          'role': m.isUser ? 'user' : 'assistant',
          'content': m.content,
        }).toList();

    try {
      final response = await http
          .post(
            Uri.parse('$base/chat'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'message': userMessage,
              'history': historyJson,
              'subject': subject,
              'learner_id': learnerId,
              'learner_name': learnerName,
              'grade': grade,
            }),
          )
          .timeout(const Duration(seconds: 180));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return data['response'] as String;
      } else if (response.statusCode == 429) {
        throw Exception('Ek minute ruko! Too many questions — please wait a moment.');
      } else {
        // Body may not be JSON when the connection was aborted mid-response
        String detail = 'Server error ${response.statusCode}';
        try {
          final data = jsonDecode(response.body) as Map<String, dynamic>;
          detail = (data['detail'] as String?) ?? detail;
        } catch (_) {}
        throw Exception(detail);
      }
    } on SocketException {
      // One automatic retry on network blip / tunnel drop
      if (attempt < 1) {
        await Future.delayed(const Duration(seconds: 2));
        return sendToLocal(
          serverUrl: serverUrl,
          userMessage: userMessage,
          history: history,
          subject: subject,
          learnerId: learnerId,
          learnerName: learnerName,
          grade: grade,
          attempt: attempt + 1,
        );
      }
      throw Exception('Connection lost — check your network and try again.');
    } on TimeoutException {
      throw Exception('Parth is thinking hard — please try again in a moment!');
    } on FormatException {
      throw Exception('Received an unexpected response — please try again.');
    }
  }

  // ── Anthropic Claude API (fallback) ────────────────────────────────────────
  static const String _anthropicUrl = 'https://api.anthropic.com/v1/messages';
  static const String _anthropicModel = 'claude-sonnet-4-6';
  static const String _apiKey =
      String.fromEnvironment('ANTHROPIC_API_KEY', defaultValue: '');

  static const String _systemPrompt =
      '''You are Parth (पार्थ), a warm and encouraging AI mentor for Indian school children aged 6–16.

Your teaching style:
- Use simple, age-appropriate language — never talk down, always uplift
- Ground examples in Indian everyday life: cricket, Diwali, monsoon, chai, samosas, Bollywood
- Celebrate effort: "Shabash!", "Wah! Bilkul sahi!", "You are getting it!"
- Break complex topics into small numbered steps
- For Maths: show working step by step with Indian-context word problems
- For Hindi: write Devanagari first, then explain in English
- End with ONE encouraging follow-up question to check understanding
- Keep responses concise (3–8 sentences unless a step-by-step is needed)
- Never discuss anything inappropriate for children''';

  Future<String> sendToAnthropic({
    required String userMessage,
    required List<Message> history,
    required String subject,
  }) async {
    final key = _apiKey.isNotEmpty ? _apiKey : '';
    if (key.isEmpty) {
      throw Exception(
          'No API key configured. Set up the local server or add your Anthropic key.');
    }

    final messages = history.takeLast(12).map((m) => {
          'role': m.isUser ? 'user' : 'assistant',
          'content': m.content,
        }).toList()
      ..add({'role': 'user', 'content': userMessage});

    try {
      final response = await http
          .post(
            Uri.parse(_anthropicUrl),
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': key,
              'anthropic-version': '2023-06-01',
            },
            body: jsonEncode({
              'model': _anthropicModel,
              'max_tokens': 1024,
              'system': '$_systemPrompt\n\nCurrent subject: $subject',
              'messages': messages,
            }),
          )
          .timeout(const Duration(seconds: 60));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final content = data['content'] as List<dynamic>;
        return (content.first as Map<String, dynamic>)['text'] as String;
      } else {
        String error = 'Unknown error';
        try {
          final body = jsonDecode(response.body) as Map<String, dynamic>;
          error = ((body['error'] as Map<String, dynamic>?))?['message'] as String? ?? error;
        } catch (_) {}
        throw Exception('Anthropic error ${response.statusCode}: $error');
      }
    } on SocketException {
      throw Exception('No internet connection.');
    } on TimeoutException {
      throw Exception('Request timed out — please try again.');
    }
  }

  // ── Unified entry point ────────────────────────────────────────────────────
  Future<String> sendMessage({
    required String userMessage,
    required List<Message> history,
    required String subject,
    String? localServerUrl,
    String learnerId = 'anonymous',
    String learnerName = '',
    int grade = 6,
  }) async {
    if (localServerUrl != null && localServerUrl.isNotEmpty) {
      return sendToLocal(
        serverUrl: localServerUrl,
        userMessage: userMessage,
        history: history,
        subject: subject,
        learnerId: learnerId,
        learnerName: learnerName,
        grade: grade,
      );
    }
    return sendToAnthropic(
      userMessage: userMessage,
      history: history,
      subject: subject,
    );
  }
}

extension<T> on List<T> {
  List<T> takeLast(int n) => length <= n ? this : sublist(length - n);
}
