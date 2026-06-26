"""
15-agent learner harness — registry and dependency-ordered dispatch list.

Architecture
------------
All agents extend kernel.agent.BaseAgent, which provides:
  • _observe(signals, conn)  — post-generation DB write (domain logic only)
  • _read(conn, learner_id)  — pre-generation context string for LLM prompt
  • emit(signals)            — publishes events onto the inter-agent bus

BaseAgent.observe() and BaseAgent.read() wrap the underscore methods with
structured warning logs so agent failures are visible without crashing the
pipeline. No agent is allowed to fail silently.

Dispatch order follows the inter-agent event dependency graph:

  Layer 0 — independent observers (no event deps; fire first)
    01 EmotionCompass        → distress.detected / engagement.high / curiosity.active
    02 CurriculumCartographer→ no events; fills coverage map
    03 MasteryTracker        → concept.weak
    04 MisconceptionHunter   → misconception.active
    05 LanguageBridge        → lang.preference
    06 BeliefCoach           → confidence.bias  (sole psyche writer)

  Layer 1 — event-aware (read Layer 0 events)
    07 ChallengeCalibrator   → difficulty.adjust  (reads distress.detected, concept.weak)
    08 MemoryKeeper          → SM-2 review + episodic memory
    09 TransferWeaver        → analogy.suggested
    10 RegisterTuner         → register.profile  (reads lang.preference)
    11 HumorDelightGuide     → delight.approved  (reads distress.detected)

  Layer 2 — integrators (read Layer 0 + 1 events)
    12 InquiryAlchemist      → curiosity threads + SEL repair
    13 FamilyAlliance        → consent-gated caregiver context
    14 RhythmTimeSteward     → pacing and peak-focus window

  Layer 3 — synthesiser (reads episodes + curiosity threads; always last)
    15 PatternCreationGuide  → wonder questions + cross-scale pattern tracking

Research foundations
--------------------
  Pavlik et al.     — ITS domain/student/pedagogical model decomposition
  Shen et al.       — interpretable KT first; SAINT+ as upgrade path (MasteryTracker)
  Kapur & Bielaczyc — productive failure (ChallengeCalibrator)
  Dunlosky et al.   — retrieval practice + spaced practice as primitives (MemoryKeeper)
  García & Lin      — translanguaging; unified linguistic repertoire (LanguageBridge)
  Dweck             — growth mindset (BeliefCoach)
  CASEL             — SEL boundaries; family partnership (InquiryAlchemist, FamilyAlliance)
  NGSS Appendix G   — crosscutting patterns across domains (PatternCreationGuide)
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
