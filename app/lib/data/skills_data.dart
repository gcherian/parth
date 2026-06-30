// Skill puzzles in the style of Philip Carter & Ken Russell.
// 5 categories × 12 puzzles = 60 starter puzzles, all verifiable offline.

class SkillCategory {
  final String id;
  final String emoji;
  final String title;
  final String tagline;
  final List<SkillPuzzle> puzzles;

  const SkillCategory({
    required this.id,
    required this.emoji,
    required this.title,
    required this.tagline,
    required this.puzzles,
  });
}

class SkillPuzzle {
  final String question;
  final List<String> options; // exactly 4
  final int answerIndex;      // index into options
  final String explanation;

  const SkillPuzzle({
    required this.question,
    required this.options,
    required this.answerIndex,
    required this.explanation,
  });
}

// ── 1. Number Skills ─────────────────────────────────────────────────────────

const _numbers = SkillCategory(
  id: 'numbers',
  emoji: '🔢',
  title: 'Number Skills',
  tagline: 'Sequences, patterns and mental maths',
  puzzles: [
    SkillPuzzle(
      question: 'What comes next?\n2,  4,  8,  16,  ___',
      options: ['24', '30', '32', '64'],
      answerIndex: 2,
      explanation: 'Each number is doubled: 2×2=4, 4×2=8, 8×2=16, 16×2=32.',
    ),
    SkillPuzzle(
      question: 'What comes next?\n1,  4,  9,  16,  ___',
      options: ['20', '25', '36', '24'],
      answerIndex: 1,
      explanation: 'These are perfect squares: 1², 2², 3², 4², 5² = 25.',
    ),
    SkillPuzzle(
      question: 'What comes next?\n1,  1,  2,  3,  5,  8,  ___',
      options: ['11', '12', '13', '15'],
      answerIndex: 2,
      explanation: 'Fibonacci: each number is the sum of the two before it. 5+8=13.',
    ),
    SkillPuzzle(
      question: 'What comes next?\n45,  36,  27,  18,  ___',
      options: ['12', '9', '8', '10'],
      answerIndex: 1,
      explanation: 'Subtract 9 each time: 45−9=36, 36−9=27, 27−9=18, 18−9=9.',
    ),
    SkillPuzzle(
      question: 'What comes next?\n1000,  100,  10,  ___',
      options: ['5', '0', '1', '0.1'],
      answerIndex: 2,
      explanation: 'Divide by 10 each time: 1000÷10=100, 100÷10=10, 10÷10=1.',
    ),
    SkillPuzzle(
      question: 'What comes next?\n3,  6,  11,  18,  27,  ___',
      options: ['36', '38', '40', '35'],
      answerIndex: 1,
      explanation: 'Differences increase by 2: +3, +5, +7, +9, +11. So 27+11=38.',
    ),
    SkillPuzzle(
      question: 'What comes next?\n1,  8,  27,  64,  ___',
      options: ['100', '125', '216', '81'],
      answerIndex: 1,
      explanation: 'Perfect cubes: 1³=1, 2³=8, 3³=27, 4³=64, 5³=125.',
    ),
    SkillPuzzle(
      question: 'Which number is missing?\n2,  6,  12,  20,  ___,  42',
      options: ['28', '30', '32', '36'],
      answerIndex: 1,
      explanation: 'Pattern: n×(n+1). So: 1×2=2, 2×3=6, 3×4=12, 4×5=20, 5×6=30.',
    ),
    SkillPuzzle(
      question: 'What is  17 × 8?',
      options: ['126', '134', '136', '148'],
      answerIndex: 2,
      explanation: '17×8 = (20−3)×8 = 160−24 = 136.',
    ),
    SkillPuzzle(
      question: 'What comes next?\nA1,  B2,  C4,  D8,  ___',
      options: ['E10', 'E12', 'E16', 'F16'],
      answerIndex: 2,
      explanation: 'Letters go A→B→C→D→E. Numbers double: 1,2,4,8,16. So E16.',
    ),
    SkillPuzzle(
      question: 'What is the sum of all single-digit odd numbers?',
      options: ['20', '25', '24', '21'],
      answerIndex: 1,
      explanation: '1+3+5+7+9 = 25.',
    ),
    SkillPuzzle(
      question: 'What comes next?\nJ,  F,  M,  A,  M,  J,  J,  A,  S,  O,  N,  ___',
      options: ['J', 'D', 'A', 'M'],
      answerIndex: 1,
      explanation: 'First letters of the 12 months. November (N) → December (D).',
    ),
  ],
);

// ── 2. Verbal Skills ─────────────────────────────────────────────────────────

const _verbal = SkillCategory(
  id: 'verbal',
  emoji: '🔡',
  title: 'Verbal Skills',
  tagline: 'Analogies, relationships and word logic',
  puzzles: [
    SkillPuzzle(
      question: 'Book is to Library as Painting is to ___?',
      options: ['Canvas', 'Artist', 'Gallery', 'Museum'],
      answerIndex: 2,
      explanation: 'A book is stored in a library; a painting is displayed in a gallery.',
    ),
    SkillPuzzle(
      question: 'Doctor is to Hospital as Teacher is to ___?',
      options: ['Book', 'School', 'Student', 'Class'],
      answerIndex: 1,
      explanation: 'A doctor works in a hospital; a teacher works in a school.',
    ),
    SkillPuzzle(
      question: 'Fish is to Water as Bird is to ___?',
      options: ['Tree', 'Feather', 'Sky', 'Wing'],
      answerIndex: 2,
      explanation: 'Fish live in water; birds live in the sky — their natural habitat.',
    ),
    SkillPuzzle(
      question: 'Kitten is to Cat as Cub is to ___?',
      options: ['Dog', 'Bear', 'Horse', 'Fox'],
      answerIndex: 1,
      explanation: 'A kitten is a baby cat; a cub is a baby bear (or lion/tiger).',
    ),
    SkillPuzzle(
      question: 'Author is to Book as Composer is to ___?',
      options: ['Orchestra', 'Concert', 'Music', 'Song'],
      answerIndex: 2,
      explanation: 'An author creates a book; a composer creates music.',
    ),
    SkillPuzzle(
      question: 'Hot is to Cold as Dark is to ___?',
      options: ['Black', 'Night', 'Light', 'Shadow'],
      answerIndex: 2,
      explanation: 'Hot and cold are opposites; dark and light are opposites.',
    ),
    SkillPuzzle(
      question: 'Moon is to Earth as Earth is to ___?',
      options: ['Mars', 'Galaxy', 'Sun', 'Milky Way'],
      answerIndex: 2,
      explanation: 'The Moon orbits the Earth; the Earth orbits the Sun.',
    ),
    SkillPuzzle(
      question: 'Pen is to Ink as Pencil is to ___?',
      options: ['Wood', 'Lead', 'Graphite', 'Carbon'],
      answerIndex: 2,
      explanation: 'A pen writes with ink; a pencil writes with graphite.',
    ),
    SkillPuzzle(
      question: 'Run is to Running as Swim is to ___?',
      options: ['Swam', 'Swims', 'Swimming', 'Swimmer'],
      answerIndex: 2,
      explanation: 'Run → Running (add -ing). Swim → Swimming.',
    ),
    SkillPuzzle(
      question: 'Which word means the OPPOSITE of "Ancient"?',
      options: ['Old', 'Historic', 'Modern', 'Classic'],
      answerIndex: 2,
      explanation: '"Ancient" means very old. Its opposite is "modern" — of the present time.',
    ),
    SkillPuzzle(
      question: 'Clock is to Time as Thermometer is to ___?',
      options: ['Heat', 'Temperature', 'Weather', 'Mercury'],
      answerIndex: 1,
      explanation: 'A clock measures time; a thermometer measures temperature.',
    ),
    SkillPuzzle(
      question: 'India is to Rupee as Japan is to ___?',
      options: ['Yuan', 'Won', 'Yen', 'Dollar'],
      answerIndex: 2,
      explanation: 'India uses the Rupee; Japan uses the Yen as currency.',
    ),
  ],
);

// ── 3. Logic ─────────────────────────────────────────────────────────────────

const _logic = SkillCategory(
  id: 'logic',
  emoji: '🧩',
  title: 'Logic',
  tagline: 'Deduction, reasoning and puzzles',
  puzzles: [
    SkillPuzzle(
      question: 'All roses are flowers. Some flowers are red.\nAre all roses red?',
      options: ['Yes', 'No', 'Maybe', 'Cannot say'],
      answerIndex: 3,
      explanation: 'We only know some flowers are red — not which ones. We cannot conclude roses are red.',
    ),
    SkillPuzzle(
      question: 'Anita is taller than Priya. Priya is taller than Meena.\nWho is the shortest?',
      options: ['Anita', 'Priya', 'Meena', 'Cannot say'],
      answerIndex: 2,
      explanation: 'Anita > Priya > Meena. So Meena is the shortest.',
    ),
    SkillPuzzle(
      question: 'You have 5 apples. You take away 3.\nHow many do YOU have?',
      options: ['2', '3', '5', '0'],
      answerIndex: 1,
      explanation: 'You took 3 away, so you personally have 3. (The basket has 2 left.)',
    ),
    SkillPuzzle(
      question: 'A rooster is standing on a roof. It lays an egg.\nWhich side does the egg roll to?',
      options: ['Left side', 'Right side', 'Straight down', 'Neither — roosters cannot lay eggs'],
      answerIndex: 3,
      explanation: 'Roosters are male. Only hens (female) lay eggs!',
    ),
    SkillPuzzle(
      question: 'Two fathers and two sons each catch one fish.\nOnly 3 fish are caught in total. How?',
      options: ['One fish escaped', 'One person caught two', 'There are only 3 people — grandfather, father, son', 'The puzzle is wrong'],
      answerIndex: 2,
      explanation: 'Grandfather + Father + Son = 3 people. The father is both a "father" and a "son".',
    ),
    SkillPuzzle(
      question: 'Which is heavier — 1 kg of iron or 1 kg of cotton?',
      options: ['Iron', 'Cotton', 'Both the same', 'Cannot compare'],
      answerIndex: 2,
      explanation: 'Both weigh exactly 1 kg. Iron is denser but the question specifies the same weight.',
    ),
    SkillPuzzle(
      question: 'If the day after tomorrow is Sunday, what day is today?',
      options: ['Thursday', 'Friday', 'Saturday', 'Wednesday'],
      answerIndex: 1,
      explanation: 'Day after tomorrow = Sunday. Tomorrow = Saturday. Today = Friday.',
    ),
    SkillPuzzle(
      question: 'A is the mother of B. B is the father of C.\nWhat is A to C?',
      options: ['Mother', 'Aunt', 'Grandmother', 'Great-grandmother'],
      answerIndex: 2,
      explanation: 'A is B\'s mother. B is C\'s father. So A is C\'s grandmother (paternal).',
    ),
    SkillPuzzle(
      question: 'A man builds a house with all four walls facing south.\nA bear walks by. What colour is the bear?',
      options: ['Brown', 'Black', 'White', 'Cannot say'],
      answerIndex: 2,
      explanation: 'This is only possible at the North Pole, where polar bears live. The bear is white.',
    ),
    SkillPuzzle(
      question: 'If you have a match and enter a room with a candle, an oil lamp, and a fireplace, what do you light first?',
      options: ['The candle', 'The oil lamp', 'The fireplace', 'The match'],
      answerIndex: 3,
      explanation: 'You must light the match first before you can light anything else!',
    ),
    SkillPuzzle(
      question: 'There are 3 boxes: one has apples, one has oranges, one has both.\nAll labels are WRONG. You pick one fruit from "Apples+Oranges". It is an apple. What is in "Apples"?',
      options: ['Apples', 'Oranges', 'Apples + Oranges', 'Cannot say'],
      answerIndex: 1,
      explanation: 'Since all labels are wrong: "Apples+Oranges" box → only apples (you saw one). "Apples" must be wrong → it\'s oranges. "Oranges" → mixed.',
    ),
    SkillPuzzle(
      question: 'In a race, you overtake the person in 3rd place.\nWhat position are you now in?',
      options: ['1st', '2nd', '3rd', '4th'],
      answerIndex: 2,
      explanation: 'You overtook 3rd place, so you are now in 3rd and they are in 4th.',
    ),
  ],
);

// ── 4. Odd One Out ───────────────────────────────────────────────────────────

const _patterns = SkillCategory(
  id: 'odd_one_out',
  emoji: '🔍',
  title: 'Odd One Out',
  tagline: 'Find what doesn\'t belong and why',
  puzzles: [
    SkillPuzzle(
      question: 'Which is the odd one out?\nApple,  Banana,  Carrot,  Mango',
      options: ['Apple', 'Banana', 'Carrot', 'Mango'],
      answerIndex: 2,
      explanation: 'Carrot is a vegetable. Apple, Banana, and Mango are all fruits.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nCircle,  Square,  Triangle,  Cone',
      options: ['Circle', 'Square', 'Triangle', 'Cone'],
      answerIndex: 3,
      explanation: 'Cone is a 3D shape. Circle, Square, and Triangle are all 2D shapes.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\n4,  9,  16,  20,  25',
      options: ['4', '9', '16', '20'],
      answerIndex: 3,
      explanation: '4, 9, 16, and 25 are perfect squares (2², 3², 4², 5²). 20 is not.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nJupiter,  Mars,  Moon,  Saturn',
      options: ['Jupiter', 'Mars', 'Moon', 'Saturn'],
      answerIndex: 2,
      explanation: 'The Moon is a natural satellite. Jupiter, Mars, and Saturn are planets.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nHindi,  Bengali,  Tamil,  English',
      options: ['Hindi', 'Bengali', 'Tamil', 'English'],
      answerIndex: 3,
      explanation: 'Hindi, Bengali, and Tamil are Indian languages. English originated in England.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nCricket,  Tennis,  Chess,  Football',
      options: ['Cricket', 'Tennis', 'Chess', 'Football'],
      answerIndex: 2,
      explanation: 'Cricket, Tennis, and Football are physical sports. Chess is a board game.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nCow,  Hen,  Goat,  Tiger',
      options: ['Cow', 'Hen', 'Goat', 'Tiger'],
      answerIndex: 3,
      explanation: 'Cow, Hen, and Goat are domestic animals. Tiger is a wild animal.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nJanuary,  March,  June,  August',
      options: ['January', 'March', 'June', 'August'],
      answerIndex: 2,
      explanation: 'January, March, and August have 31 days. June has only 30 days.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nOxygen,  Nitrogen,  Carbon dioxide,  Helium',
      options: ['Oxygen', 'Nitrogen', 'Carbon dioxide', 'Helium'],
      answerIndex: 2,
      explanation: 'Oxygen, Nitrogen, and Helium are elements. Carbon dioxide is a compound (CO₂).',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nShakespeare,  Tagore,  Einstein,  Dickens',
      options: ['Shakespeare', 'Tagore', 'Einstein', 'Dickens'],
      answerIndex: 2,
      explanation: 'Shakespeare, Tagore, and Dickens are writers/poets. Einstein was a physicist.',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\n2,  3,  6,  7,  11',
      options: ['2', '3', '6', '7'],
      answerIndex: 2,
      explanation: '2, 3, 7, and 11 are prime numbers. 6 is not prime (6 = 2×3).',
    ),
    SkillPuzzle(
      question: 'Which is the odd one out?\nRiver,  Lake,  Pond,  Cloud',
      options: ['River', 'Lake', 'Pond', 'Cloud'],
      answerIndex: 3,
      explanation: 'River, Lake, and Pond are bodies of standing or flowing water. A cloud is water vapour in the atmosphere.',
    ),
  ],
);

// ── 5. Brain Teasers ─────────────────────────────────────────────────────────

const _teasers = SkillCategory(
  id: 'teasers',
  emoji: '🧠',
  title: 'Brain Teasers',
  tagline: 'Lateral thinking and clever traps',
  puzzles: [
    SkillPuzzle(
      question: 'What has hands but cannot clap?',
      options: ['A puppet', 'A clock', 'A statue', 'A tree'],
      answerIndex: 1,
      explanation: 'A clock has hour and minute "hands" but they cannot clap.',
    ),
    SkillPuzzle(
      question: 'What can run but never walks,\nhas a mouth but never talks,\nhas a head but never weeps?',
      options: ['A shadow', 'A river', 'A wheel', 'Wind'],
      answerIndex: 1,
      explanation: 'A river: it runs, has a "mouth" (where it meets the sea), and a "head" (its source).',
    ),
    SkillPuzzle(
      question: 'I speak without a mouth and hear without ears. I have no body but come alive with wind. What am I?',
      options: ['A ghost', 'An echo', 'A radio', 'A storm'],
      answerIndex: 1,
      explanation: 'An echo — it speaks back your words (no mouth), and you hear it (no ears).',
    ),
    SkillPuzzle(
      question: 'The more you take, the more you leave behind. What am I?',
      options: ['Money', 'Time', 'Footsteps', 'Memories'],
      answerIndex: 2,
      explanation: 'Footsteps — every step you take, you leave one more footstep behind you.',
    ),
    SkillPuzzle(
      question: 'What gets wetter the more it dries?',
      options: ['A sponge', 'A towel', 'Rain', 'Sand'],
      answerIndex: 1,
      explanation: 'A towel — it dries things by absorbing water, so it gets wetter as it does its job.',
    ),
    SkillPuzzle(
      question: 'A train leaves Mumbai at 7 AM at 60 km/h and a train leaves Delhi at 9 AM at 80 km/h. When they meet, which is closer to Mumbai?',
      options: ['The Mumbai train', 'The Delhi train', 'Both equally close', 'Neither'],
      answerIndex: 2,
      explanation: 'When they meet, they are at the same point — so both are equally close to Mumbai!',
    ),
    SkillPuzzle(
      question: 'How many months have 28 days?',
      options: ['1', '2', '6', '12'],
      answerIndex: 3,
      explanation: 'All 12 months have at least 28 days! (February has exactly 28 in a non-leap year.)',
    ),
    SkillPuzzle(
      question: 'A farmer has 17 sheep. All but 9 die. How many sheep are left?',
      options: ['8', '9', '17', '0'],
      answerIndex: 1,
      explanation: '"All but 9" means 9 survive. 9 sheep are left.',
    ),
    SkillPuzzle(
      question: 'What is always in front of you but cannot be seen?',
      options: ['The future', 'Air', 'Space', 'Your nose'],
      answerIndex: 0,
      explanation: 'The future is always ahead of you, but you cannot see it.',
    ),
    SkillPuzzle(
      question: 'I have cities but no houses, mountains but no trees, water but no fish. What am I?',
      options: ['A painting', 'A map', 'A dream', 'A desert'],
      answerIndex: 1,
      explanation: 'A map — it has symbols for cities, mountains, and water, but none of the real things.',
    ),
    SkillPuzzle(
      question: 'What comes once in a minute, twice in a moment, but never in a thousand years?',
      options: ['A second', 'The letter M', 'A blink', 'A full moon'],
      answerIndex: 1,
      explanation: 'The letter "M" — once in "minute", twice in "moment", zero in "a thousand years".',
    ),
    SkillPuzzle(
      question: 'Before Mount Everest was discovered, what was the highest mountain on Earth?',
      options: ['K2', 'Kangchenjunga', 'Mount Everest', 'Makalu'],
      answerIndex: 2,
      explanation: 'Mount Everest was always the highest — it just hadn\'t been discovered yet!',
    ),
  ],
);

// ── All categories ────────────────────────────────────────────────────────────

const allSkillCategories = [_numbers, _verbal, _logic, _patterns, _teasers];
