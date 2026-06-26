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

enum ProbeMode { choice, puzzle }

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
    final inner = (outer['probe'] as Map?)?.cast<String, dynamic>() ?? {};
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

class PuzzlePortrait {
  final String primarySphere;
  final Map<String, double> sphereAffinity;
  final String provisionalTelos;

  const PuzzlePortrait({
    required this.primarySphere,
    required this.sphereAffinity,
    required this.provisionalTelos,
  });

  factory PuzzlePortrait.fromJson(Map<String, dynamic> json) {
    final p = (json['portrait'] as Map?)?.cast<String, dynamic>() ?? {};
    final rawAff = (p['sphere_affinity'] as Map?) ?? {};
    final aff = <String, double>{};
    rawAff.forEach((k, v) => aff[k.toString()] = (v as num).toDouble());
    return PuzzlePortrait(
      primarySphere: p['primary_sphere'] as String? ?? '',
      sphereAffinity: aff,
      provisionalTelos: p['provisional_telos'] as String? ?? 'explorer',
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
