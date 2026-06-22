import 'dart:convert';
import 'dart:async';

import 'package:http/http.dart' as http;

import '../models/puzzle.dart';

class PuzzleService {
  static const _appKey =
      String.fromEnvironment('PARTH_API_KEY', defaultValue: '');

  String _base(String serverUrl) {
    final url = serverUrl.trim();
    return url.endsWith('/') ? url.substring(0, url.length - 1) : url;
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_appKey.isNotEmpty) 'X-Parth-Key': _appKey,
      };

  Map<String, String> get _getHeaders =>
      _appKey.isNotEmpty ? {'X-Parth-Key': _appKey} : {};

  Future<ColdStartProbe> nextPuzzle({
    required String learnerId,
    required int grade,
    required String serverUrl,
  }) async {
    final r = await http
        .get(
          Uri.parse('${_base(serverUrl)}/puzzle/next/$learnerId?grade=$grade'),
          headers: _getHeaders,
        )
        .timeout(const Duration(seconds: 25));
    if (r.statusCode != 200) {
      throw Exception('Server returned ${r.statusCode}');
    }
    final data = jsonDecode(r.body) as Map<String, dynamic>;
    if (data.containsKey('error')) {
      throw Exception(data['error'].toString());
    }
    return ColdStartProbe.fromJson(data);
  }

  Future<void> respond({
    required String learnerId,
    required String puzzleId,
    required String response,
    required int timeSeconds,
    required bool reachedDeeper,
    required int grade,
    required String serverUrl,
  }) async {
    await http
        .post(
          Uri.parse('${_base(serverUrl)}/puzzle/respond'),
          headers: _headers,
          body: jsonEncode({
            'learner_id': learnerId,
            'puzzle_id': puzzleId,
            'response': response,
            'time_seconds': timeSeconds,
            'reached_deeper': reachedDeeper,
            'grade': grade,
          }),
        )
        .timeout(const Duration(seconds: 30));
  }

  Future<PuzzlePortrait> getPortrait({
    required String learnerId,
    required String serverUrl,
  }) async {
    final r = await http
        .get(
          Uri.parse('${_base(serverUrl)}/puzzle/portrait/$learnerId'),
          headers: _getHeaders,
        )
        .timeout(const Duration(seconds: 15));
    if (r.statusCode != 200) {
      throw Exception('Server returned ${r.statusCode}');
    }
    return PuzzlePortrait.fromJson(
        jsonDecode(r.body) as Map<String, dynamic>);
  }
}
