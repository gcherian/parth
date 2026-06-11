"""
Agent registry — 15-agent learner harness.

Dispatch order follows the inter-agent event dependency graph:
  EmotionCompass first  → emits distress.detected / engagement.high / curiosity.active
  CurriculumCartographer → no deps; fills coverage map
  MasteryTracker        → BKT + SAINT+ event log; emits concept.weak
  MisconceptionHunter   → emits misconception.active
  LanguageBridge        → emits lang.preference
  BeliefCoach           → sole psyche writer; emits confidence.bias
  ChallengeCalibrator   → reads distress.detected, concept.weak
  MemoryKeeper          → SM-2 review schedule + episodic memory
  TransferWeaver        → reads analogy scores; emits analogy.suggested
  RegisterTuner         → reads lang.preference; emits register.profile
  HumorDelightGuide     → reads distress.detected; emits delight.approved
  InquiryAlchemist      → curiosity threads + SEL repair (reads distress.detected)
  FamilyAlliance        → consent-gated caregiver context (reads mastery + emotion)
  RhythmTimeSteward     → pacing and peak-focus window
  PatternCreationGuide  → wonder questions + cross-scale pattern tracking (last — reads episodes+threads)

Research foundations embedded in each agent:
  Pavlik et al. — ITS domain/student/pedagogical model decomposition
  Shen et al. — interpretable KT before complex models (Mastery Tracker)
  Kapur & Bielaczyc — productive failure (Challenge Calibrator)
  Dunlosky et al. — retrieval practice and spaced practice as primitives (Memory Keeper)
  García & Lin — translanguaging; never punish code-switching (Language Bridge)
  CASEL — SEL boundaries; family partnership (Inquiry Alchemist, Family Alliance)
  NGSS Appendix G — crosscutting patterns across domains (Pattern & Creation Guide)
"""
from __future__ import annotations
from kernel.agent import LearnerAgent

from modules.learner_state.agents.emotion_compass       import EmotionCompassAgent
from modules.learner_state.agents.curriculum_cartographer import CurriculumCartographerAgent
from modules.learner_state.agents.mastery_tracker        import MasteryTrackerAgent
from modules.learner_state.agents.misconception_hunter   import MisconceptionHunterAgent
from modules.learner_state.agents.language_bridge        import LanguageBridgeAgent
from modules.learner_state.agents.belief_coach           import BeliefCoachAgent
from modules.learner_state.agents.challenge_calibrator   import ChallengeCalibratorAgent
from modules.learner_state.agents.memory_keeper          import MemoryKeeperAgent
from modules.learner_state.agents.transfer_weaver        import TransferWeaverAgent
from modules.learner_state.agents.register_tuner         import RegisterTunerAgent
from modules.learner_state.agents.humor_delight_guide    import HumorDelightGuideAgent
from modules.learner_state.agents.inquiry_alchemist      import InquiryAlchemistAgent
from modules.learner_state.agents.family_alliance        import FamilyAllianceAgent
from modules.learner_state.agents.rhythm_time_steward    import RhythmTimeStewardAgent
from modules.learner_state.agents.pattern_creation_guide import PatternCreationGuideAgent


def build_agent_registry() -> list[LearnerAgent]:
    """Return all 15 agents in inter-agent dependency order."""
    return [
        EmotionCompassAgent(),         # 01 — affect vector; distress/engagement events first
        CurriculumCartographerAgent(), # 02 — coverage map; no event deps
        MasteryTrackerAgent(),         # 03 — BKT + SAINT+ log; emits concept.weak
        MisconceptionHunterAgent(),    # 04 — emits misconception.active
        LanguageBridgeAgent(),         # 05 — emits lang.preference
        BeliefCoachAgent(),            # 06 — sole psyche writer; emits confidence.bias
        ChallengeCalibratorAgent(),    # 07 — reads distress.detected + concept.weak
        MemoryKeeperAgent(),           # 08 — SM-2 + episodic memory
        TransferWeaverAgent(),         # 09 — analogy scores + history
        RegisterTunerAgent(),          # 10 — tone/register; emits register.profile
        HumorDelightGuideAgent(),      # 11 — reads distress.detected; emits delight.approved
        InquiryAlchemistAgent(),       # 12 — curiosity threads + SEL repair
        FamilyAllianceAgent(),         # 13 — consent-gated caregiver context
        RhythmTimeStewardAgent(),      # 14 — pacing and peak-focus
        PatternCreationGuideAgent(),   # 15 — wonder questions; last (reads episodes + threads)
    ]
