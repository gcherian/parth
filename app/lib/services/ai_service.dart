import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/message.dart';

class AiService {
  // ── Local Parth server (primary) ───────────────────────────────────────────
  Future<String> sendToLocal({
    required String serverUrl,
    required String userMessage,
    required List<Message> history,
    required String subject,
  }) async {
    final url = serverUrl.endsWith('/') ? serverUrl.substring(0, serverUrl.length - 1) : serverUrl;

    final historyJson = history.takeLast(16).map((m) => {
          'role': m.isUser ? 'user' : 'assistant',
          'content': m.content,
        }).toList();

    final response = await http
        .post(
          Uri.parse('$url/chat'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'message': userMessage,
            'history': historyJson,
            'subject': subject,
          }),
        )
        .timeout(const Duration(seconds: 180));

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['response'] as String;
    } else if (response.statusCode == 429) {
      throw Exception('Ek minute ruko! Too many questions — please wait a moment.');
    } else {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(data['detail'] ?? 'Server error ${response.statusCode}');
    }
  }

  // ── Anthropic Claude API (fallback) ────────────────────────────────────────
  static const String _anthropicUrl = 'https://api.anthropic.com/v1/messages';
  static const String _anthropicModel = 'claude-sonnet-4-6';
  static const String _apiKey = String.fromEnvironment('ANTHROPIC_API_KEY', defaultValue: '');

  static const String _systemPrompt = '''You are Parth (पार्थ), a warm and encouraging AI mentor for Indian school children aged 6–16.

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
      throw Exception('No API key configured. Set up the local server or add your Anthropic key.');
    }

    final messages = history.takeLast(12).map((m) => {
          'role': m.isUser ? 'user' : 'assistant',
          'content': m.content,
        }).toList()
      ..add({'role': 'user', 'content': userMessage});

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
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final error = (body['error'] as Map<String, dynamic>?)?['message'] ?? 'Unknown error';
      throw Exception('Anthropic error ${response.statusCode}: $error');
    }
  }

  // ── Unified entry point ────────────────────────────────────────────────────
  // Tries local server first; falls back to Anthropic if server URL is empty.
  Future<String> sendMessage({
    required String userMessage,
    required List<Message> history,
    required String subject,
    String? localServerUrl,
  }) async {
    if (localServerUrl != null && localServerUrl.isNotEmpty) {
      return sendToLocal(
        serverUrl: localServerUrl,
        userMessage: userMessage,
        history: history,
        subject: subject,
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
