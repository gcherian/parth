// Data models for the cold start puzzle engine.

class PuzzleHookOption {
  final String puzzleId;
  final String sphere;
  final String hook;
  final String title;

  const PuzzleHookOption({
    required this.puzzleId,
    required this.sphere,
    required this.hook,
    required this.title,
  });

  factory PuzzleHookOption.fromJson(Map<String, dynamic> j) => PuzzleHookOption(
        puzzleId: j['puzzle_id'] as String? ?? '',
        sphere: j['sphere'] as String? ?? '',
        hook: j['hook'] as String? ?? '',
        title: j['title'] as String? ?? '',
      );
}

class PuzzleCardData {
  final String id;
  final String sphere;
  final String thinkerName;
  final String title;
  final String hook;
  final String challenge;
  final String materials;
  final String discover;
  final String goDeeper;

  const PuzzleCardData({
    required this.id,
    required this.sphere,
    required this.thinkerName,
    required this.title,
    required this.hook,
    required this.challenge,
    required this.materials,
    required this.discover,
    required this.goDeeper,
  });

  factory PuzzleCardData.fromJson(Map<String, dynamic> j) => PuzzleCardData(
        id: j['id'] as String? ?? '',
        sphere: j['sphere'] as String? ?? '',
        thinkerName: j['thinker_name'] as String? ?? '',
        title: j['title'] as String? ?? '',
        hook: j['hook'] as String? ?? '',
        challenge: j['challenge'] as String? ?? '',
        materials: j['materials'] as String? ?? '',
        discover: j['discover'] as String? ?? '',
        goDeeper: j['go_deeper'] as String? ?? '',
      );
}

enum ProbeMode { choice, puzzle, complete }

class ColdStartProbe {
  final int probeNumber;
  final ProbeMode mode;
  // choice mode
  final String? instruction;
  final PuzzleHookOption? optionA;
  final PuzzleHookOption? optionB;
  // puzzle mode
  final PuzzleCardData? puzzle;
  final String? specialInstruction;
  final String? followUp;

  const ColdStartProbe({
    required this.probeNumber,
    required this.mode,
    this.instruction,
    this.optionA,
    this.optionB,
    this.puzzle,
    this.specialInstruction,
    this.followUp,
  });

  factory ColdStartProbe.fromJson(Map<String, dynamic> outer) {
    final probeNumber = outer['probe_number'] as int? ?? 0;
    final outerMode = outer['mode'] as String? ?? '';
    final inner = (outer['probe'] as Map?)?.cast<String, dynamic>() ?? {};
    if (outerMode == 'normal' || inner.isEmpty) {
      return const ColdStartProbe(
        probeNumber: 5,
        mode: ProbeMode.complete,
      );
    }
    final innerMode = inner['mode'] as String? ?? 'puzzle';

    if (innerMode == 'choice') {
      final a = inner['option_a'];
      final b = inner['option_b'];
      return ColdStartProbe(
        probeNumber: probeNumber,
        mode: ProbeMode.choice,
        instruction: inner['instruction'] as String?,
        optionA: a != null
            ? PuzzleHookOption.fromJson((a as Map).cast<String, dynamic>())
            : null,
        optionB: b != null
            ? PuzzleHookOption.fromJson((b as Map).cast<String, dynamic>())
            : null,
      );
    }

    final pJson = inner['puzzle'] as Map?;
    return ColdStartProbe(
      probeNumber: probeNumber,
      mode: ProbeMode.puzzle,
      puzzle: pJson != null
          ? PuzzleCardData.fromJson(pJson.cast<String, dynamic>())
          : null,
      specialInstruction: inner['instruction'] as String?,
      followUp: inner['follow_up'] as String?,
    );
  }
}

double _asDouble(Object? value, [double fallback = 0]) {
  if (value is num) return value.toDouble();
  return fallback;
}

int _asInt(Object? value, [int fallback = 0]) {
  if (value is num) return value.toInt();
  return fallback;
}

Map<String, double> _doubleMap(Object? value) {
  final raw = (value as Map?) ?? {};
  final parsed = <String, double>{};
  raw.forEach((k, v) {
    if (v is num) parsed[k.toString()] = v.toDouble();
  });
  return parsed;
}

Map<String, String> _stringMap(Object? value) {
  final raw = (value as Map?) ?? {};
  final parsed = <String, String>{};
  raw.forEach((k, v) => parsed[k.toString()] = v.toString());
  return parsed;
}

class PuzzleRegisterBubble {
  final String domain;
  final double probability;
  final double radius;
  final bool isDominant;
  final String family;
  final String colorHex;

  const PuzzleRegisterBubble({
    required this.domain,
    required this.probability,
    required this.radius,
    required this.isDominant,
    required this.family,
    required this.colorHex,
  });

  factory PuzzleRegisterBubble.fromJson(Map<String, dynamic> json) {
    return PuzzleRegisterBubble(
      domain: json['domain'] as String? ?? '',
      probability: _asDouble(json['probability']),
      radius: _asDouble(json['radius']),
      isDominant: json['is_dominant'] as bool? ?? false,
      family: json['family'] as String? ?? 'other',
      colorHex: json['color'] as String? ?? '#9E9E9E',
    );
  }
}

class PuzzleRegister {
  final String learnerId;
  final int nMessages;
  final String questionStyle;
  final double confidence;
  final String dominantDomain;
  final List<PuzzleRegisterBubble> bubbles;

  const PuzzleRegister({
    required this.learnerId,
    required this.nMessages,
    required this.questionStyle,
    required this.confidence,
    required this.dominantDomain,
    required this.bubbles,
  });

  static const empty = PuzzleRegister(
    learnerId: '',
    nMessages: 0,
    questionStyle: 'unknown',
    confidence: 0,
    dominantDomain: '',
    bubbles: [],
  );

  factory PuzzleRegister.fromJson(Map<String, dynamic> json) {
    final rawBubbles = (json['bubbles'] as List?) ?? [];
    return PuzzleRegister(
      learnerId: json['learner_id'] as String? ?? '',
      nMessages: _asInt(json['n_messages']),
      questionStyle: json['question_style'] as String? ?? 'unknown',
      confidence: _asDouble(json['confidence']),
      dominantDomain: json['dominant_domain'] as String? ?? '',
      bubbles: rawBubbles
          .whereType<Map>()
          .map((b) => PuzzleRegisterBubble.fromJson(b.cast<String, dynamic>()))
          .toList(),
    );
  }

  List<PuzzleRegisterBubble> get topBubbles => bubbles.take(6).toList();
}

class PuzzleBridge {
  final String domain;
  final String sphere;
  final double probability;
  final String hook;
  final String example;
  final List<String> telosFit;

  const PuzzleBridge({
    required this.domain,
    required this.sphere,
    required this.probability,
    required this.hook,
    required this.example,
    required this.telosFit,
  });

  static const empty = PuzzleBridge(
    domain: '',
    sphere: '',
    probability: 0,
    hook: '',
    example: '',
    telosFit: [],
  );

  factory PuzzleBridge.fromJson(Map<String, dynamic> json) {
    final raw = (json['bridge'] as Map?)?.cast<String, dynamic>() ?? json;
    return PuzzleBridge(
      domain: raw['domain'] as String? ?? '',
      sphere: raw['sphere'] as String? ?? '',
      probability: _asDouble(raw['prob']),
      hook: raw['hook'] as String? ?? '',
      example: raw['example'] as String? ?? '',
      telosFit: ((raw['telos_fit'] ?? raw['best_for_telos']) as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
    );
  }

  bool get hasContent => hook.isNotEmpty || example.isNotEmpty;
}

class PuzzlePortrait {
  final String learnerId;
  final String primarySphere;
  final String secondarySphere;
  final Map<String, String> zpdLevels;
  final String errorResponse;
  final double crossDomainCuriosity;
  final Map<String, double> sphereAffinity;
  final String provisionalTelos;
  final double confidence;
  final int interactionsUsed;
  final int grade;
  final double languageRatio;
  final PuzzleRegister register;

  const PuzzlePortrait({
    required this.learnerId,
    required this.primarySphere,
    required this.secondarySphere,
    required this.zpdLevels,
    required this.errorResponse,
    required this.crossDomainCuriosity,
    required this.sphereAffinity,
    required this.provisionalTelos,
    required this.confidence,
    required this.interactionsUsed,
    required this.grade,
    required this.languageRatio,
    required this.register,
  });

  factory PuzzlePortrait.fromJson(Map<String, dynamic> json) {
    final p = (json['portrait'] as Map?)?.cast<String, dynamic>() ?? {};
    final registerJson =
        (json['register'] as Map?)?.cast<String, dynamic>() ?? {};
    return PuzzlePortrait(
      learnerId: p['learner_id'] as String? ?? '',
      primarySphere: p['primary_sphere'] as String? ?? '',
      secondarySphere: p['secondary_sphere'] as String? ?? '',
      zpdLevels: _stringMap(p['zpd_levels']),
      errorResponse: p['error_response'] as String? ?? 'unknown',
      crossDomainCuriosity: _asDouble(p['cross_domain_curiosity'], 0.5),
      sphereAffinity: _doubleMap(p['sphere_affinity']),
      provisionalTelos: p['provisional_telos'] as String? ?? 'explorer',
      confidence: _asDouble(p['confidence']),
      interactionsUsed: _asInt(p['interactions_used']),
      grade: _asInt(p['grade']),
      languageRatio: _asDouble(p['language_ratio'], 1.0),
      register: registerJson.isNotEmpty
          ? PuzzleRegister.fromJson(registerJson)
          : PuzzleRegister.empty,
    );
  }

  List<MapEntry<String, double>> get topSpheres {
    if (sphereAffinity.isEmpty) return [];
    final entries = sphereAffinity.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    // Only return spheres that genuinely diverged from neutral (5.0)
    final top = entries.where((e) => e.value >= 5.0).take(3).toList();
    return top.isNotEmpty ? top : entries.take(2).toList();
  }
}
