"""
Parth Meaning Graph — seed content.

A curated first pass at "the top of the pyramid": stories that have
survived because children (and the adults telling them) retained them —
Aesop, the Panchatantra, the Jataka tales, the Upanishads, the
Mahabharata and Ramayana, the Bible, and a few Shakespeare scenes for
the older end of the range. Not exhaustive — a seed, meant to be grown.

Every story is told up to its suspense hook and stops there on
purpose: Parth's role is to ask the question, not hand over the
moral. See DevelopmentalStage below for why the same story lands
differently at 5 than at 10.

Sources are traditional/public-domain narratives; synopses here are
original retellings, not quotations from any translation.
"""

# ── Traditions ──────────────────────────────────────────────────────────────

TRADITIONS = [
    dict(id="aesop", label="Aesop's Fables", region="Ancient Greece",
         era="~600 BCE", language="Greek (oral origin)"),
    dict(id="panchatantra", label="Panchatantra", region="India",
         era="~200 BCE", language="Sanskrit"),
    dict(id="jataka", label="Jataka Tales", region="India",
         era="~300 BCE", language="Pali"),
    dict(id="upanishads", label="Upanishads", region="India",
         era="~700 BCE", language="Sanskrit"),
    dict(id="mahabharata", label="Mahabharata", region="India",
         era="~400 BCE (compiled)", language="Sanskrit"),
    dict(id="ramayana", label="Ramayana", region="India",
         era="~500 BCE (compiled)", language="Sanskrit"),
    dict(id="bible", label="Bible", region="Levant",
         era="~1000 BCE – 100 CE", language="Hebrew / Greek"),
    dict(id="shakespeare", label="Shakespeare", region="England",
         era="~1600 CE", language="English"),
    dict(id="confucian", label="Confucian Analects", region="China",
         era="~500 BCE", language="Classical Chinese"),
]

# ── Developmental stages ─────────────────────────────────────────────────────
# Grounded loosely in Piaget (preoperational -> concrete -> formal
# operational), Kohlberg's simplified moral stages, theory-of-mind
# onset (~age 4-5), and the memory-systems story the user described:
# the hippocampus isn't online for durable autobiographical/narrative
# memory until ~age 3-4 (why nobody remembers being 1), which is why
# a story only becomes a *retained, retellable* thing from stage 2 on.

STAGES = [
    dict(id="sensorimotor_bonding", label="Sensorimotor Bonding", age_min=0, age_max=2,
         brain_process=("Thalamic sensory relay wires to the amygdala for emotional "
                         "salience before the hippocampus can hold an episode — a face, "
                         "a voice, a smell get tagged 'safe' or 'alarm' long before they "
                         "can be remembered as a story."),
         what_child_grasps="Presence vs. absence. Safety vs. threat. Rhythm and repetition (peekaboo)."),
    dict(id="symbolic_naming", label="Symbolic Naming", age_min=2, age_max=4,
         brain_process=("The hippocampus comes online for durable autobiographical "
                         "memory around this window — the end of 'infantile amnesia.' "
                         "Language explodes; the first metaphors appear ('the moon is "
                         "following me')."),
         what_child_grasps="Naming. Simple cause and effect. Animism — everything has feelings. The first real 'why'."),
    dict(id="moral_absolutism", label="Moral Absolutism", age_min=4, age_max=7,
         brain_process=("Prefrontal impulse control is still years from mature, but "
                         "hippocampal narrative memory is now strong enough to hold and "
                         "retell a whole story arc. Theory of mind (that others have "
                         "different beliefs) switches on around 4-5."),
         what_child_grasps=("Rules are fixed and outcomes matter more than intentions "
                             "(breaking five cups by accident feels 'worse' than one on "
                             "purpose). Clean good/bad characters land well here.")),
    dict(id="reciprocity_and_fairness", label="Reciprocity & Fairness", age_min=7, age_max=11,
         brain_process=("Increasing myelination of prefrontal-hippocampal-amygdala "
                         "circuits improves emotion regulation. Reversibility (Piaget) "
                         "lets a child mentally undo an action and imagine an alternative."),
         what_child_grasps=("Intention starts to matter as much as outcome. Rules can be "
                             "negotiated, not just obeyed. 'What if I were them' becomes "
                             "available — riddles and moral ambiguity start to land.")),
    dict(id="abstract_meaning", label="Abstract Meaning-Making", age_min=11, age_max=16,
         brain_process=("Prefrontal cortex continues maturing into the mid-20s, but "
                         "formal-operational reasoning — holding a principle above a "
                         "rule, tolerating paradox — becomes available now."),
         what_child_grasps=("Tragic irony. A principle that costs something. Existential "
                             "questions asked directly, not softened.")),
]
STAGE_ORDER = ["sensorimotor_bonding", "symbolic_naming", "moral_absolutism",
               "reciprocity_and_fairness", "abstract_meaning"]

# ── Character archetypes ─────────────────────────────────────────────────────

ARCHETYPES = [
    dict(id="trickster", label="The Trickster",
         description="Wins through wit, not strength — often small, often underestimated."),
    dict(id="wise_fool", label="The Wise Fool",
         description="Looks lowly or naive but asks the one question everyone else avoided."),
    dict(id="faithful_companion", label="The Faithful Companion",
         description="Loyal through hardship, asks nothing in return."),
    dict(id="proud_ruler", label="The Proud Ruler",
         description="Authority whose pride or certainty precipitates their own fall."),
    dict(id="self_sacrificing_hero", label="The Self-Sacrificing Hero",
         description="Gives up something vital — status, safety, life itself — for others."),
    dict(id="unlikely_underdog", label="The Unlikely Underdog",
         description="Small or weak defeats large or strong, not by matching force with force."),
    dict(id="true_seeker", label="The True Seeker",
         description="Refuses the easy or flattering answer; insists on the real question."),
    dict(id="false_flatterer", label="The False Flatterer",
         description="Says what is wanted to hear rather than what is true."),
    dict(id="betrayer_transformed", label="The Betrayer, Transformed",
         description="Does real harm, then is changed by what follows — not let off, changed."),
]

# ── Concepts ──────────────────────────────────────────────────────────────────

CONCEPTS = [
    dict(id="humility_over_arrogance", label="Humility Over Arrogance",
         description="Steady, modest effort outlasts confident showmanship."),
    dict(id="patience_and_steady_effort", label="Patience & Steady Effort",
         description="What is slow and continuous can beat what is fast and interrupted."),
    dict(id="trust_and_cost_of_lying", label="Trust & the Cost of Lying",
         description="Trust is a resource that depletes with each false alarm — and doesn't refill on demand."),
    dict(id="rationalizing_failure", label="Rationalizing Failure",
         description="Deciding you never wanted the thing you couldn't reach."),
    dict(id="foresight_vs_present_pleasure", label="Foresight vs. Present Pleasure",
         description="What feels good now and what serves you later are often different choices."),
    dict(id="unlikely_reciprocity", label="Unlikely Reciprocity",
         description="A small kindness, once given, can return from a source too small to expect it from."),
    dict(id="gentle_persuasion_over_force", label="Gentle Persuasion Over Force",
         description="Warmth can loosen what force only makes grip tighter."),
    dict(id="wit_outsmarting_power", label="Wit Outsmarting Power",
         description="Cleverness lets the weaker party change the game instead of losing it."),
    dict(id="cost_of_false_identity", label="The Cost of a False Identity",
         description="Pretending to be more than you are works only until you act like what you pretend to be."),
    dict(id="greed_destroying_the_source", label="Greed Destroying the Source",
         description="Taking everything at once can destroy the thing that was going to keep giving."),
    dict(id="courage_to_ask_ultimate_question", label="The Courage to Ask the Ultimate Question",
         description="Choosing the true, hard question over any number of comfortable prizes."),
    dict(id="unity_behind_appearances", label="Unity Behind Appearances",
         description="Different things can share one unseen essence, invisible until you look the right way."),
    dict(id="duty_amid_moral_paralysis", label="Duty Amid Moral Paralysis",
         description="Acting rightly when every option in front of you looks like a loss."),
    dict(id="generosity_beyond_self_preservation", label="Generosity Beyond Self-Preservation",
         description="Giving away the very thing that protects you."),
    dict(id="wisdom_through_riddles", label="Wisdom Through Riddles",
         description="Some truths only arrive if you're willing to be questioned, not just to answer."),
    dict(id="danger_of_a_single_flaw", label="The Danger of a Single Flaw",
         description="One unexamined weakness can undo everything built around it."),
    dict(id="keeping_ones_word", label="Keeping One's Word",
         description="A promise costs the most exactly when it becomes inconvenient to keep."),
    dict(id="latent_potential_needing_awakening", label="Latent Potential Needing Awakening",
         description="Strength you forget you have doesn't help until someone reminds you of it."),
    dict(id="courage_of_the_underdog", label="Courage of the Underdog",
         description="Facing something enormous with only what you actually have, not what you'd need."),
    dict(id="compassion_beyond_tribe", label="Compassion Beyond Tribe",
         description="Care that crosses the line of 'my people' to reach whoever is actually hurt."),
    dict(id="forgiveness_transforming_betrayal", label="Forgiveness Transforming Betrayal",
         description="What was meant to harm can be answered in a way that changes its meaning."),
    dict(id="love_revealed_through_sacrifice", label="Love Revealed Through Sacrifice, Not Assertion",
         description="The realer claim is the one willing to lose, not the one that shouts loudest."),
    dict(id="unconditional_welcome", label="Unconditional Welcome",
         description="Being received before you've earned it back."),
    dict(id="quality_of_mercy", label="The Quality of Mercy",
         description="What the law allows and what compassion asks aren't always the same thing."),
    dict(id="true_love_vs_flattery", label="True Love vs. Flattery",
         description="What's real is often quieter than what's said out loud to please."),
    dict(id="perception_vs_reality", label="Perception vs. Reality",
         description="What we're sure we're seeing can be shaped by something we don't know is acting on us."),
    dict(id="golden_rule_reciprocity", label="The Golden Rule",
         description="Treating another by the same measure you'd want used on you — found, independently, almost everywhere."),
]

# ── Concept <-> Stage (GRASPABLE_AT) ─────────────────────────────────────────
# A concept can genuinely land at more than one stage, in a deeper form
# each time — listed earliest-first; the story is retold, not replaced.

CONCEPT_STAGES = {
    "humility_over_arrogance": ["moral_absolutism"],
    "patience_and_steady_effort": ["moral_absolutism"],
    "trust_and_cost_of_lying": ["moral_absolutism", "reciprocity_and_fairness"],
    "rationalizing_failure": ["moral_absolutism", "reciprocity_and_fairness"],
    "foresight_vs_present_pleasure": ["moral_absolutism"],
    "unlikely_reciprocity": ["moral_absolutism"],
    "gentle_persuasion_over_force": ["moral_absolutism", "reciprocity_and_fairness"],
    "wit_outsmarting_power": ["moral_absolutism", "reciprocity_and_fairness"],
    "cost_of_false_identity": ["reciprocity_and_fairness"],
    "greed_destroying_the_source": ["moral_absolutism", "reciprocity_and_fairness"],
    "courage_to_ask_ultimate_question": ["abstract_meaning"],
    "unity_behind_appearances": ["abstract_meaning"],
    "duty_amid_moral_paralysis": ["abstract_meaning"],
    "generosity_beyond_self_preservation": ["reciprocity_and_fairness", "abstract_meaning"],
    "wisdom_through_riddles": ["reciprocity_and_fairness", "abstract_meaning"],
    "danger_of_a_single_flaw": ["reciprocity_and_fairness", "abstract_meaning"],
    "keeping_ones_word": ["reciprocity_and_fairness"],
    "latent_potential_needing_awakening": ["moral_absolutism", "reciprocity_and_fairness"],
    "courage_of_the_underdog": ["moral_absolutism"],
    "compassion_beyond_tribe": ["reciprocity_and_fairness"],
    "forgiveness_transforming_betrayal": ["reciprocity_and_fairness", "abstract_meaning"],
    "love_revealed_through_sacrifice": ["reciprocity_and_fairness"],
    "unconditional_welcome": ["moral_absolutism", "reciprocity_and_fairness"],
    "quality_of_mercy": ["reciprocity_and_fairness", "abstract_meaning"],
    "true_love_vs_flattery": ["reciprocity_and_fairness"],
    "perception_vs_reality": ["reciprocity_and_fairness", "abstract_meaning"],
    "golden_rule_reciprocity": ["moral_absolutism", "reciprocity_and_fairness"],
}

# ── Concept <-> Concept (RELATED_TO) ─────────────────────────────────────────

CONCEPT_RELATIONS = [
    ("quality_of_mercy", "compassion_beyond_tribe", "reinforcement", "both widen the circle of who deserves care"),
    ("quality_of_mercy", "danger_of_a_single_flaw", "tension", "mercy is what a strict reading of the rule would deny"),
    ("humility_over_arrogance", "patience_and_steady_effort", "reinforcement", "the tortoise needs both to win"),
    ("rationalizing_failure", "foresight_vs_present_pleasure", "tension", "one excuses not trying; the other rewards trying anyway"),
    ("true_love_vs_flattery", "love_revealed_through_sacrifice", "reinforcement", "both distinguish real love from its performance"),
    ("forgiveness_transforming_betrayal", "compassion_beyond_tribe", "reinforcement", "both extend care past where it was 'earned'"),
    ("wit_outsmarting_power", "courage_of_the_underdog", "reinforcement", "two different tools for the same mismatch"),
    ("wisdom_through_riddles", "courage_to_ask_ultimate_question", "reinforcement", "both value the question over a quick answer"),
    ("generosity_beyond_self_preservation", "duty_amid_moral_paralysis", "reinforcement", "both act rightly at real personal cost"),
    ("cost_of_false_identity", "perception_vs_reality", "tension", "one is about deceiving others, the other about being deceived"),
    ("golden_rule_reciprocity", "compassion_beyond_tribe", "reinforcement", "reciprocity extended past your own group"),
    ("greed_destroying_the_source", "foresight_vs_present_pleasure", "reinforcement", "both weigh now against later"),
    ("keeping_ones_word", "duty_amid_moral_paralysis", "reinforcement", "a promise is a duty that outlives the mood you made it in"),
    ("latent_potential_needing_awakening", "courage_of_the_underdog", "tension", "one says the underdog was never really outmatched"),
]

# ── Stories ───────────────────────────────────────────────────────────────────
# Each: id, title, tradition, age_min/max, synopsis (told up to the hook),
# suspense_hook (the question Parth or a parent asks and lets sit),
# embodies: [(concept_id, centrality)], features: [(archetype_id, role)]

STORIES = [
    dict(id="tortoise_and_hare", title="The Tortoise and the Hare", tradition="aesop",
         age_min=4, age_max=8,
         synopsis=("A hare laughs at a tortoise for being slow and challenges her to a "
                    "race. So sure of winning, the hare dashes ahead, then stops to nap "
                    "in the shade. The tortoise never stops moving — she just never speeds up."),
         suspense_hook="The hare is so far ahead he can't even see the tortoise anymore. Does he still need to worry?",
         embodies=[("humility_over_arrogance", "primary"), ("patience_and_steady_effort", "primary")],
         features=[("unlikely_underdog", "tortoise"), ("proud_ruler", "hare")]),

    dict(id="boy_who_cried_wolf", title="The Boy Who Cried Wolf", tradition="aesop",
         age_min=4, age_max=8,
         synopsis=("A shepherd boy, bored watching his sheep, shouts 'Wolf!' twice for "
                    "fun and watches the whole village come running for nothing. The "
                    "third time, a wolf actually comes."),
         suspense_hook="He shouts 'Wolf!' as loud as he can. Why isn't anyone coming this time?",
         embodies=[("trust_and_cost_of_lying", "primary")],
         features=[]),

    dict(id="fox_and_grapes", title="The Fox and the Grapes", tradition="aesop",
         age_min=4, age_max=9,
         synopsis=("A fox spots a high bunch of grapes and jumps again and again, but "
                    "can't reach them. Walking away, he mutters that they were probably "
                    "sour anyway."),
         suspense_hook="He never even tasted them. How does he know they were sour?",
         embodies=[("rationalizing_failure", "primary")],
         features=[("trickster", "fox")]),

    dict(id="ant_and_grasshopper", title="The Ant and the Grasshopper", tradition="aesop",
         age_min=4, age_max=8,
         synopsis=("All summer, the grasshopper sings while the ant hauls food to her "
                    "nest, grain by grain. Winter comes. The grasshopper has a song and "
                    "an empty larder; the ant has a full one."),
         suspense_hook="The grasshopper knocks on the ant's door, hungry and cold. What should the ant do?",
         embodies=[("foresight_vs_present_pleasure", "primary")],
         features=[]),

    dict(id="lion_and_mouse", title="The Lion and the Mouse", tradition="aesop",
         age_min=4, age_max=8,
         synopsis=("A lion lets a mouse go instead of eating it, half-amused when the "
                    "mouse promises to repay him someday — what could a mouse possibly "
                    "do for a lion? Later, the lion is caught in a hunter's net."),
         suspense_hook="The lion is roaring and thrashing, but the ropes only get tighter. Who could possibly help him now?",
         embodies=[("unlikely_reciprocity", "primary")],
         features=[("self_sacrificing_hero", "mouse")]),

    dict(id="north_wind_and_sun", title="The North Wind and the Sun", tradition="aesop",
         age_min=5, age_max=9,
         synopsis=("The Wind and the Sun argue over who is stronger and agree on a test: "
                    "whoever can make a traveler take off his coat wins. The Wind blows "
                    "as hard as it can."),
         suspense_hook="The harder the Wind blows, the tighter the traveler pulls his coat around himself. Why isn't this working?",
         embodies=[("gentle_persuasion_over_force", "primary")],
         features=[]),

    dict(id="monkey_and_crocodile", title="The Monkey and the Crocodile", tradition="panchatantra",
         age_min=5, age_max=9,
         synopsis=("A monkey and a crocodile become friends; the monkey shares fruit "
                    "from his tree every day. The crocodile's wife, tasting the fruit, "
                    "wants the monkey's heart, which she believes must be sweeter still. "
                    "The crocodile invites the monkey onto his back to cross the river."),
         suspense_hook="Halfway across, the crocodile admits the truth: he's taking the monkey to his wife, for his heart. The monkey is stuck on the crocodile's back in the middle of the river. What does he say?",
         embodies=[("wit_outsmarting_power", "primary")],
         features=[("trickster", "monkey")]),

    dict(id="blue_jackal", title="The Blue Jackal", tradition="panchatantra",
         age_min=6, age_max=10,
         synopsis=("A jackal, fleeing dogs, falls into a vat of blue dye and comes out "
                    "an unearthly blue. The other animals, never having seen this colour, "
                    "assume he must be a king sent by the forest gods and make him their ruler."),
         suspense_hook="One night, the jackal hears real jackals howling nearby — and feels the howl rising in his own throat. If he joins in, everyone will know exactly what he is. What does he do?",
         embodies=[("cost_of_false_identity", "primary")],
         features=[("trickster", "jackal")]),

    dict(id="golden_goose", title="The Goose That Laid the Golden Eggs", tradition="panchatantra",
         age_min=4, age_max=8,
         synopsis=("A farmer's goose lays one golden egg every single day, and within a "
                    "year he is rich. But one egg a day feels too slow now."),
         suspense_hook="The farmer picks up his axe and looks at the goose. If all the gold is inside her, why wait?",
         embodies=[("greed_destroying_the_source", "primary")],
         features=[]),

    dict(id="monkey_king_bridge", title="The Monkey King's Bridge", tradition="jataka",
         age_min=6, age_max=11,
         synopsis=("A troop of monkeys feasts in a mango tree overhanging a river, ruled "
                    "kindly by their Monkey King. When the king of the land discovers the "
                    "tree and surrounds it with archers, the only escape is across the "
                    "river — too wide for the troop to jump."),
         suspense_hook="The Monkey King stretches his own body from the tree to a branch on the far bank, close but not quite touching, and tells his troop to run across him. He is out of rope, out of time, and there is nothing left to bridge the last gap but himself. What happens to him?",
         embodies=[("generosity_beyond_self_preservation", "primary")],
         features=[("self_sacrificing_hero", "monkey king")]),

    dict(id="nachiketa_and_yama", title="Nachiketa and the Lord of Death", tradition="upanishads",
         age_min=9, age_max=15,
         synopsis=("A boy named Nachiketa is sent to the house of Death by his father's "
                    "careless words, and waits three days at Death's door. Death, "
                    "impressed, offers him any three wishes to make up for the wait. "
                    "Nachiketa asks for wealth, then long life for his family — and Death "
                    "grants both easily. For the third wish, Nachiketa asks: what happens "
                    "to a person after they die?"),
         suspense_hook="Death tries to buy him off — kingdoms, riches, the longest life ever lived, anything except the answer. Nachiketa has already been offered everything a person could want. Why does he keep refusing?",
         embodies=[("courage_to_ask_ultimate_question", "primary")],
         features=[("true_seeker", "Nachiketa")]),

    dict(id="svetaketu_salt", title="Svetaketu and the Salt Water", tradition="upanishads",
         age_min=7, age_max=12,
         synopsis=("A father asks his son Svetaketu to dissolve salt in a cup of water "
                    "overnight, then bring it back. In the morning, the salt has vanished "
                    "completely — but the father asks him to taste the water anyway."),
         suspense_hook="Svetaketu can't see the salt anywhere in the cup — but he can taste it in every part of the water, top, middle, and bottom. If it's not visible anywhere, but it's present everywhere, where exactly is it?",
         embodies=[("unity_behind_appearances", "primary")],
         features=[("true_seeker", "Svetaketu")]),

    dict(id="arjuna_despair", title="Arjuna's Despair at Kurukshetra", tradition="mahabharata",
         age_min=10, age_max=16,
         synopsis=("Arjuna, the great archer, stands in his chariot between two armies "
                    "about to fight each other — and sees, on the other side, his own "
                    "teachers, cousins, and grandfather. His bow slips from his hand."),
         suspense_hook="Every choice in front of Arjuna leads to people he loves getting hurt — fighting them, or failing the side he's promised to stand with. Krishna, his charioteer, says only: 'get up and act.' How can acting be right when every action leads somewhere painful?",
         embodies=[("duty_amid_moral_paralysis", "primary")],
         features=[]),

    dict(id="karnas_charity", title="Karna's Armor", tradition="mahabharata",
         age_min=9, age_max=15,
         synopsis=("Karna was born wearing golden armor and earrings fused to his skin, "
                    "making him unbeatable in battle. Indra, wanting to protect his own "
                    "son (Karna's rival Arjuna), disguises himself as a beggar and asks "
                    "Karna for alms on the one morning Karna has sworn to refuse no one."),
         suspense_hook="Karna already knows who the beggar really is, and what he's really asking for. He could refuse just this once and no one would blame him. He picks up the knife anyway. Why keep a promise to a stranger when it costs you the one thing protecting your life?",
         embodies=[("generosity_beyond_self_preservation", "primary"), ("keeping_ones_word", "secondary")],
         features=[("self_sacrificing_hero", "Karna")]),

    dict(id="yaksha_prashna", title="The Yaksha's Questions", tradition="mahabharata",
         age_min=9, age_max=15,
         synopsis=("Yudhishthira's four brothers drink from a forest lake guarded by a "
                    "Yaksha spirit and fall down dead, having ignored his warning to "
                    "answer his questions first. Yudhishthira arrives and finds all four "
                    "bodies. The Yaksha offers to answer one question — or to ask "
                    "Yudhishthira questions instead, and revive one brother if he answers well."),
         suspense_hook="One of the Yaksha's questions is: 'What is the most wondrous thing in the world?' Yudhishthira answers: 'Day after day, people die, and yet the living wish to live forever, as though they alone were exempt.' What did he mean by that?",
         embodies=[("wisdom_through_riddles", "primary")],
         features=[("true_seeker", "Yudhishthira")]),

    dict(id="game_of_dice", title="The Game of Dice", tradition="mahabharata",
         age_min=10, age_max=16,
         synopsis=("Yudhishthira, otherwise wise and just, cannot resist a game of dice. "
                    "Invited to play against a cheat, he keeps playing past every "
                    "sensible stopping point, wagering his wealth, his kingdom, his "
                    "brothers, and finally himself."),
         suspense_hook="He has already lost his kingdom. He keeps playing. What is he actually trying to win back at this point — the kingdom, or the feeling of not having lost?",
         embodies=[("danger_of_a_single_flaw", "primary")],
         features=[("proud_ruler", "Yudhishthira")]),

    dict(id="ramas_exile", title="Rama's Exile", tradition="ramayana",
         age_min=8, age_max=14,
         synopsis=("On the eve of Rama's coronation, his stepmother Kaikeyi calls in an "
                    "old promise from his father the king: her son crowned instead, and "
                    "Rama sent into the forest for fourteen years. The king is bound by "
                    "his own word, and devastated."),
         suspense_hook="Rama could refuse to go — the whole kingdom would support him, and even his father is silently hoping he will refuse. He starts packing for the forest instead. Why honor a promise that was never really his to keep?",
         embodies=[("keeping_ones_word", "primary")],
         features=[("self_sacrificing_hero", "Rama")]),

    dict(id="hanuman_forgets_strength", title="Hanuman Forgets His Own Strength", tradition="ramayana",
         age_min=6, age_max=11,
         synopsis=("As a child, Hanuman was so powerful and mischievous that sages "
                    "cursed him to forget his own strength until someone reminded him of "
                    "it. Years later, searching for Sita across the ocean, the monkey "
                    "army is stuck at the shore — the sea is too wide for any of them to cross."),
         suspense_hook="Jambavan turns to Hanuman and reminds him of who he really is and what he can really do — powers Hanuman has completely forgotten he has. Can you actually forget your own strength?",
         embodies=[("latent_potential_needing_awakening", "primary")],
         features=[("faithful_companion", "Hanuman")]),

    dict(id="david_and_goliath", title="David and Goliath", tradition="bible",
         age_min=6, age_max=11,
         synopsis=("The Philistine champion Goliath, over nine feet tall, challenges "
                    "Israel's army to send one man to fight him. No soldier will step "
                    "forward. A shepherd boy named David, too young to be a soldier at "
                    "all, volunteers — and refuses the armor he's offered, taking only "
                    "his sling."),
         suspense_hook="Goliath is laughing at him. David is a shepherd boy with a sling and five stones against a giant in full armor. What does David know that everyone watching doesn't?",
         embodies=[("courage_of_the_underdog", "primary")],
         features=[("unlikely_underdog", "David"), ("proud_ruler", "Goliath")]),

    dict(id="good_samaritan", title="The Good Samaritan", tradition="bible",
         age_min=6, age_max=12,
         synopsis=("A man is beaten and left half-dead on the road. A priest sees him "
                    "and crosses to the other side. A temple assistant does the same. "
                    "Then a Samaritan — from a group the injured man's people looked "
                    "down on — comes by."),
         suspense_hook="The two men who were supposed to help, by their own religion's standards, walked past. The one man with every reason to walk past too — old rivalry, old contempt — stops. Why him?",
         embodies=[("compassion_beyond_tribe", "primary")],
         features=[]),

    dict(id="joseph_and_brothers", title="Joseph and His Brothers", tradition="bible",
         age_min=8, age_max=14,
         synopsis=("Jealous of their father's favorite son, Joseph's brothers sell him "
                    "into slavery and tell their father he was killed by a wild animal. "
                    "Years later, Joseph — now Egypt's second most powerful man — comes "
                    "face to face with the same brothers, who don't recognize him and "
                    "are begging him, a stranger, for food."),
         suspense_hook="Joseph has total power over the men who sold him into slavery, and they have no idea who he is. What does he do with that power?",
         embodies=[("forgiveness_transforming_betrayal", "primary")],
         features=[("betrayer_transformed", "the brothers")]),

    dict(id="solomon_two_mothers", title="Solomon and the Two Mothers", tradition="bible",
         age_min=7, age_max=13,
         synopsis=("Two women, living together, each recently had a baby; one baby died "
                    "in the night, and now both women claim the living child is hers. "
                    "There are no witnesses. King Solomon, asked to judge, calls for a sword."),
         suspense_hook="Solomon orders the living baby cut in half, one half to each woman. One woman agrees it's fair. The other begs him to stop and give the baby to the other woman instead, whole. Which one is the real mother, and how does Solomon know?",
         embodies=[("love_revealed_through_sacrifice", "primary"), ("wisdom_through_riddles", "secondary")],
         features=[("true_seeker", "Solomon")]),

    dict(id="prodigal_son", title="The Prodigal Son", tradition="bible",
         age_min=6, age_max=12,
         synopsis=("A younger son demands his inheritance early, leaves home, and wastes "
                    "it all until he's feeding pigs to survive. He decides to go home and "
                    "ask to be taken back, not as a son, but as a hired servant — that's "
                    "the most he thinks he can ask for."),
         suspense_hook="While the son is still far down the road, rehearsing his apology, his father sees him and starts running to meet him. Why doesn't the father wait to hear the apology first?",
         embodies=[("unconditional_welcome", "primary")],
         features=[("betrayer_transformed", "the son")]),

    dict(id="merchant_of_venice_mercy", title="Portia's Mercy Speech", tradition="shakespeare",
         age_min=10, age_max=16,
         synopsis=("Shylock has lent Antonio money on a contract that lets him cut a "
                    "pound of flesh from Antonio's chest if the debt isn't repaid on "
                    "time. The debt is late. In court, disguised as a young lawyer, "
                    "Portia confirms the contract is completely legal — then asks Shylock "
                    "to consider mercy instead."),
         suspense_hook="Portia says the contract entitles Shylock to exactly what it says — no more, no less: flesh, but not one drop of blood, since the contract never mentioned blood. What does that technicality actually mean for Shylock's claim?",
         embodies=[("quality_of_mercy", "primary")],
         features=[]),

    dict(id="king_lear_cordelia", title="Cordelia's Silence", tradition="shakespeare",
         age_min=10, age_max=16,
         synopsis=("Old King Lear asks his three daughters to declare how much they "
                    "love him, before he divides his kingdom between them by the size of "
                    "their answer. Goneril and Regan give lavish speeches. Cordelia, who "
                    "loves him most, says she loves him exactly as a daughter should — "
                    "no more, no less — and won't perform more than that."),
         suspense_hook="Cordelia's answer is the shortest and the plainest of the three, and it costs her everything — Lear disowns her on the spot. Why does the daughter who loves him best refuse to say the biggest words?",
         embodies=[("true_love_vs_flattery", "primary")],
         features=[("false_flatterer", "Goneril and Regan")]),

    dict(id="midsummer_love_potion", title="The Love-Potion Confusion", tradition="shakespeare",
         age_min=8, age_max=13,
         synopsis=("In an enchanted forest, a mischievous fairy squeezes a flower's juice "
                    "onto the eyes of sleeping lovers, meant to fix one mismatched pair — "
                    "but the wrong person gets the juice first, and by morning nearly "
                    "everyone loves the wrong person, with total, sudden conviction."),
         suspense_hook="Everyone under the spell is completely certain about who they love — no doubt at all. Is being sure of something the same as it being true?",
         embodies=[("perception_vs_reality", "primary")],
         features=[]),

    dict(id="confucius_silver_rule", title="Confucius and the One Word", tradition="confucian",
         age_min=8, age_max=14,
         synopsis=("A student asks Confucius if there is one single word that could "
                    "guide a person for their whole life. Confucius answers: 'reciprocity' "
                    "— do not do to others what you would not want done to yourself."),
         suspense_hook="One word, for an entire life. Out of everything Confucius could have said, why that one?",
         embodies=[("golden_rule_reciprocity", "primary")],
         features=[("wise_fool", "Confucius")]),
]

# ── Story <-> Story (ECHOES) — cross-tradition kinship ───────────────────────

ECHOES = [
    ("monkey_and_crocodile", "fox_and_grapes", "cleverness turning a trap into an exit"),
    ("golden_goose", "game_of_dice", "one greedy or compulsive act destroying an entire steady gain"),
    ("david_and_goliath", "monkey_and_crocodile", "the small party wins by changing the terms, not the size, of the fight"),
    ("good_samaritan", "joseph_and_brothers", "care extended to someone with every reason to be refused it"),
    ("solomon_two_mothers", "yaksha_prashna", "the wise judge's real test is hidden inside an apparently simple question"),
    ("prodigal_son", "joseph_and_brothers", "the wronged or waiting party responds with welcome instead of score-settling"),
    ("merchant_of_venice_mercy", "solomon_two_mothers", "a legal or literal reading of a rule gives way to a deeper judgment"),
    ("nachiketa_and_yama", "svetaketu_salt", "a father-or-teacher figure withholds an easy answer to make room for real understanding"),
    ("karnas_charity", "monkey_king_bridge", "giving away exactly the thing that was protecting you"),
    ("tortoise_and_hare", "hanuman_forgets_strength", "what you have (pace, strength) matters less than whether you actually use it"),
    ("king_lear_cordelia", "midsummer_love_potion", "declared or performed love isn't proof of real love"),
    ("ramas_exile", "karnas_charity", "keeping a promise or duty at real personal cost, without being forced to"),
    ("boy_who_cried_wolf", "blue_jackal", "a false signal (a cry, a color) works until reality catches up with it"),
    ("confucius_silver_rule", "good_samaritan", "the same reciprocity ethic, arrived at independently in different traditions"),
]
