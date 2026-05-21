-- curriculum_seed.sql — Idempotent NCERT curriculum graph seed
-- Run via: psql -U parth -d parth -f data/curriculum_seed.sql
-- or via foundation/db.py apply_schema()

-- ─────────────────────────────────────────────────────────────
-- 1. CONCEPTS  (40 total)
-- ─────────────────────────────────────────────────────────────
INSERT INTO curriculum_graph.concepts (id, label, subject, grade_min, grade_max, description) VALUES
-- === MATHEMATICS ===
('arithmetic',         'Arithmetic Operations',         'mathematics', 1, 6,  'Addition, subtraction, multiplication and division of whole numbers.'),
('fractions',          'Fractions',                     'mathematics', 3, 7,  'Parts of a whole; numerator and denominator; equivalent fractions.'),
('decimals',           'Decimals',                      'mathematics', 4, 7,  'Decimal notation; tenths, hundredths; converting fractions to decimals.'),
('bodmas',             'BODMAS / Order of Operations',  'mathematics', 5, 8,  'Brackets, Orders, Division, Multiplication, Addition, Subtraction precedence.'),
('ratios',             'Ratios and Proportions',        'mathematics', 6, 8,  'Comparing quantities; direct and inverse proportion.'),
('percentage',         'Percentages',                   'mathematics', 6, 8,  'Per-cent meaning; converting between fractions, decimals and percent.'),
('integers',           'Integers',                      'mathematics', 6, 7,  'Positive and negative whole numbers; number line; operations on integers.'),
('geometry',           'Basic Geometry',                'mathematics', 4, 8,  'Shapes, angles, perimeter and area of basic 2-D figures.'),
('algebra_basics',     'Algebra Basics',                'mathematics', 7, 9,  'Variables, expressions and simple equations; transposition.'),
('linear_equations',   'Linear Equations',              'mathematics', 7, 9,  'One-variable and two-variable linear equations; graphical solution.'),
('triangles',          'Triangles',                     'mathematics', 7, 9,  'Types of triangles; congruence and similarity; Pythagoras theorem.'),
('quadrilaterals',     'Quadrilaterals',                'mathematics', 7, 9,  'Properties of parallelograms, rectangles, squares, rhombus and trapezium.'),
('profit_loss',        'Profit and Loss',               'mathematics', 7, 9,  'Cost price, selling price, profit percentage and loss percentage.'),
('simple_interest',    'Simple Interest',               'mathematics', 7, 9,  'Principal, rate and time; SI = PRT/100.'),
('data_handling',      'Data Handling and Statistics',  'mathematics', 6, 9,  'Mean, median, mode; bar charts; pie charts; histograms.'),
('probability_basics', 'Basic Probability',             'mathematics', 8, 10, 'Sample space; equally likely outcomes; P(E) = favourable/total.'),

-- === SCIENCE — PHYSICS ===
('newton_laws',        'Newtons Laws of Motion',        'science',     8, 10, 'Three laws; inertia, F=ma, action-reaction.'),
('force_pressure',     'Force and Pressure',            'science',     8, 9,  'Contact and non-contact forces; pressure = force/area.'),
('electricity',        'Electricity and Circuits',      'science',     6, 10, 'Electric current, voltage, resistance; Ohms law; series and parallel circuits.'),
('magnetism',          'Magnetism',                     'science',     6, 9,  'Magnetic field; poles; electromagnets; Earths magnetism.'),
('light_optics',       'Light and Optics',              'science',     6, 10, 'Reflection, refraction; mirrors and lenses; dispersion of light.'),
('sound',              'Sound',                         'science',     8, 9,  'Vibrations; longitudinal waves; frequency, amplitude; echo.'),

-- === SCIENCE — CHEMISTRY ===
('periodic_table',     'Periodic Table and Atoms',      'science',     8, 10, 'Elements; atomic number; periods and groups; Mendeleevs table.'),
('chemical_reactions', 'Chemical Reactions',            'science',     9, 10, 'Reactants and products; types of reactions; balancing equations.'),
('acids_bases',        'Acids, Bases and Salts',        'science',     9, 10, 'pH scale; indicators; neutralisation; common acids and bases.'),
('carbon_compounds',   'Carbon and Its Compounds',      'science',     9, 10, 'Covalent bonds; hydrocarbons; functional groups; soaps and detergents.'),

-- === SCIENCE — BIOLOGY ===
('cell_biology',       'Cell Structure and Function',   'science',     6, 9,  'Cell theory; prokaryote vs eukaryote; organelles and their roles.'),
('photosynthesis',     'Photosynthesis',                'science',     7, 9,  'Light + CO2 + water to glucose + O2; role of chlorophyll.'),
('human_body',         'Human Body Systems',            'science',     6, 9,  'Digestive, circulatory, respiratory, nervous and skeletal systems.'),
('ecosystem',          'Ecosystem and Ecology',         'science',     7, 9,  'Biotic and abiotic factors; food chains and webs; energy flow.'),
('heredity',           'Heredity and Evolution',        'science',     9, 10, 'Mendels laws; genes; chromosomes; natural selection.'),
('natural_resources',  'Natural Resources',             'science',     8, 10, 'Renewable and non-renewable; conservation; water, soil, air.'),
('water_cycle',        'Water Cycle',                   'science',     6, 8,  'Evaporation, condensation, precipitation; groundwater.'),

-- === SOCIAL SCIENCE — HISTORY ===
('mughal_empire',      'Mughal Empire',                 'social_science', 6, 8, 'Babur to Aurangzeb; administration; culture; decline.'),
('indian_independence','Indian Independence Movement',  'social_science', 8, 10,'Freedom struggle; Gandhi; Non-Cooperation; Quit India; 1947.'),
('french_revolution',  'French Revolution',             'social_science', 9, 10,'Causes; events of 1789; Enlightenment ideas; impact on world.'),
('nationalism_india',  'Rise of Nationalism in India',  'social_science', 9, 10,'Swadeshi; INC; role of press; mass movements.'),

-- === SOCIAL SCIENCE — GEOGRAPHY ===
('geography_india',    'Geography of India',            'social_science', 6, 9, 'Physical features; climate zones; rivers; vegetation.'),
('resources_development','Resources and Development',   'social_science', 8, 10,'Types of resources; sustainable development; land use.'),

-- === SOCIAL SCIENCE — CIVICS ===
('democracy_politics', 'Democracy and Political Science','social_science',8, 10,'Constitution; fundamental rights; Parliament; federalism.')

ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- 1b. PATTERN TAGS — update each concept with its structural patterns
-- ─────────────────────────────────────────────────────────────

UPDATE curriculum_graph.concepts SET patterns = ARRAY['scaling','nested_hierarchy']        WHERE id = 'arithmetic';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['scaling','nested_hierarchy']        WHERE id = 'fractions';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['scaling','nested_hierarchy']        WHERE id = 'decimals';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy']                  WHERE id = 'bodmas';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['scaling']                           WHERE id = 'ratios';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['scaling']                           WHERE id = 'percentage';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','symmetry']                  WHERE id = 'integers';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['symmetry','crystalline']            WHERE id = 'geometry';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy']                  WHERE id = 'algebra_basics';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['wave','scaling']                    WHERE id = 'linear_equations';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['symmetry','branching']              WHERE id = 'triangles';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['symmetry','crystalline']            WHERE id = 'quadrilaterals';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle']                             WHERE id = 'profit_loss';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['scaling','cycle']                   WHERE id = 'simple_interest';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['emergence']                         WHERE id = 'data_handling';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['emergence','scaling']               WHERE id = 'probability_basics';

UPDATE curriculum_graph.concepts SET patterns = ARRAY['wave','cycle']                      WHERE id = 'newton_laws';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['flow','scaling']                    WHERE id = 'force_pressure';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['flow','wave','nested_hierarchy']    WHERE id = 'electricity';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['wave','spiral']                     WHERE id = 'magnetism';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['wave','spiral']                     WHERE id = 'light_optics';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['wave']                              WHERE id = 'sound';

UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy','crystalline','symmetry'] WHERE id = 'periodic_table';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','emergence']                 WHERE id = 'chemical_reactions';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','scaling']                   WHERE id = 'acids_bases';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['branching','crystalline']           WHERE id = 'carbon_compounds';

UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy','branching']      WHERE id = 'cell_biology';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','flow']                      WHERE id = 'photosynthesis';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['branching','flow','nested_hierarchy'] WHERE id = 'human_body';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy','cycle','emergence'] WHERE id = 'ecosystem';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['branching','nested_hierarchy']      WHERE id = 'heredity';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','flow']                      WHERE id = 'natural_resources';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','flow','branching']          WHERE id = 'water_cycle';

UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy','cycle']          WHERE id = 'mughal_empire';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['emergence']                         WHERE id = 'indian_independence';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['emergence','cycle']                 WHERE id = 'french_revolution';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['emergence']                         WHERE id = 'nationalism_india';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy','branching','flow'] WHERE id = 'geography_india';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['cycle','nested_hierarchy']          WHERE id = 'resources_development';
UPDATE curriculum_graph.concepts SET patterns = ARRAY['nested_hierarchy','emergence']      WHERE id = 'democracy_politics';


-- ─────────────────────────────────────────────────────────────
-- 1c. PATTERN LIBRARY
-- ─────────────────────────────────────────────────────────────

INSERT INTO curriculum_graph.pattern_library (id, label, description, examples, scales) VALUES

('spiral',
 'The Spiral',
 'A curve that winds outward from a centre, maintaining proportion at every scale. Nature uses it everywhere — from the smallest shell to the largest galaxy.',
 ARRAY['nautilus shell','spiral galaxy','DNA double helix','cyclone from above','sunflower seeds','chameleon tail','fiddlehead fern','whirlpool','cochlea in your ear'],
 ARRAY['cosmic','planetary','biological','atomic']),

('branching',
 'Branching',
 'A structure that splits into smaller copies of itself, again and again. Every branch looks like the whole. More surface, less material — the most efficient shape in nature.',
 ARRAY['tree trunk to branches to twigs to veins','river delta from satellite','lungs and bronchial tubes','blood vessels','lightning bolt','river network','neural dendrites','coral reef','family tree'],
 ARRAY['cosmic','planetary','biological','mathematical']),

('wave',
 'The Wave',
 'A disturbance that travels through space carrying energy but not matter. Everything that moves without moving its medium is a wave.',
 ARRAY['ocean wave','sound in air','light from the sun','seismic wave through Earth','stadium wave','ripple in a pond','radio signal','quantum probability wave'],
 ARRAY['cosmic','planetary','biological','atomic','mathematical']),

('cycle',
 'The Cycle',
 'A process that returns to its starting point and begins again. Energy and matter are conserved — nothing is created or destroyed, only transformed.',
 ARRAY['water cycle','carbon cycle','seasons','day and night','cell division','life and death','profit and loss','breathing','rock cycle','food chain loop'],
 ARRAY['cosmic','planetary','biological','mathematical']),

('nested_hierarchy',
 'Nested Hierarchy',
 'Structures within structures — each level contains the one below and is contained by the one above. The universe organises itself this way at every scale.',
 ARRAY['quarks inside protons inside atoms inside molecules inside cells inside organs inside organisms','planets inside solar systems inside galaxies inside galaxy clusters','words inside sentences inside paragraphs','army ranks','folders inside folders'],
 ARRAY['cosmic','planetary','biological','atomic','mathematical']),

('symmetry',
 'Symmetry',
 'A transformation that leaves something unchanged. The deepest laws of physics are symmetries — conservation of energy is a symmetry in time.',
 ARRAY['snowflake (6-fold)','human face','butterfly wings','crystal lattice','flower petals','honeycomb','Taj Mahal','the periodic table groups','mirror reflection'],
 ARRAY['cosmic','planetary','biological','atomic','mathematical']),

('crystalline',
 'Crystalline Order',
 'Atoms or units arranging themselves into the same repeating pattern, following simple rules, creating large-scale order from local interactions.',
 ARRAY['salt crystal','snowflake','diamond','quartz','ice formation','graphite layers','honeycomb','brick wall','amino acid folding'],
 ARRAY['planetary','biological','atomic']),

('emergence',
 'Emergence',
 'When simple parts following simple rules produce behaviour that none of the parts could produce alone. The whole is genuinely more than the sum of its parts.',
 ARRAY['consciousness from neurons','life from chemistry','traffic jams from individual cars','ant colony intelligence','democracy from individual votes','market price from buyers and sellers','weather from air molecules','music from notes'],
 ARRAY['cosmic','planetary','biological','mathematical']),

('flow',
 'Flow',
 'Movement from high concentration to low — of energy, matter, information, or force. Everything flows downhill in some sense.',
 ARRAY['river flowing to sea','electricity from high to low potential','heat from hot to cold','blood from heart outward','diffusion of perfume','nutrients through food chain','water through roots to leaves','information through a network'],
 ARRAY['cosmic','planetary','biological','atomic']),

('scaling',
 'Scaling',
 'When the same relationship holds at every size — zoom in or zoom out and the structure looks the same. Coastlines, mountains, and economic inequality all share this.',
 ARRAY['Mandelbrot set','coastline paradox','mountain range silhouette at different scales','population of cities (Zipf law)','earthquake sizes','income distribution','heartbeat intervals','internet traffic'],
 ARRAY['cosmic','planetary','biological','mathematical'])

ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────────────────────
-- 2. CONCEPT EDGES  (50+ edges)
-- ─────────────────────────────────────────────────────────────
INSERT INTO curriculum_graph.concept_edges (from_id, to_id, type) VALUES

-- arithmetic is the root for all maths
('arithmetic',       'fractions',          'prerequisite'),
('arithmetic',       'decimals',           'prerequisite'),
('arithmetic',       'integers',           'prerequisite'),
('arithmetic',       'bodmas',             'prerequisite'),
('arithmetic',       'geometry',           'prerequisite'),
('arithmetic',       'data_handling',      'prerequisite'),

-- fractions tree
('fractions',        'ratios',             'prerequisite'),
('fractions',        'algebra_basics',     'prerequisite'),
('fractions',        'profit_loss',        'prerequisite'),
('fractions',        'decimals',           'co-requisite'),

-- decimals tree
('decimals',         'percentage',         'prerequisite'),
('decimals',         'simple_interest',    'prerequisite'),

-- bodmas and algebra
('bodmas',           'algebra_basics',     'prerequisite'),

-- integers and algebra
('integers',         'algebra_basics',     'prerequisite'),
('integers',         'linear_equations',   'prerequisite'),

-- percentage tree
('percentage',       'profit_loss',        'prerequisite'),
('percentage',       'simple_interest',    'prerequisite'),
('percentage',       'probability_basics', 'prerequisite'),

-- ratios
('ratios',           'percentage',         'prerequisite'),
('ratios',           'profit_loss',        'prerequisite'),

-- algebra to linear equations
('algebra_basics',   'linear_equations',   'prerequisite'),

-- geometry to shapes
('geometry',         'triangles',          'prerequisite'),
('geometry',         'quadrilaterals',     'prerequisite'),

-- data handling to probability
('data_handling',    'probability_basics', 'prerequisite'),

-- leads-to chains (maths)
('linear_equations', 'algebra_basics',     'leads-to'),
('triangles',        'quadrilaterals',     'co-requisite'),

-- cell biology is biology root
('cell_biology',     'photosynthesis',     'prerequisite'),
('cell_biology',     'human_body',         'prerequisite'),
('cell_biology',     'heredity',           'prerequisite'),

-- ecosystem
('ecosystem',        'natural_resources',  'prerequisite'),
('ecosystem',        'heredity',           'prerequisite'),
('water_cycle',      'natural_resources',  'prerequisite'),

-- physics
('newton_laws',      'force_pressure',     'prerequisite'),
('newton_laws',      'electricity',        'leads-to'),
('electricity',      'magnetism',          'co-requisite'),
('magnetism',        'electricity',        'co-requisite'),

-- light and sound (leads-to from newton)
('newton_laws',      'light_optics',       'leads-to'),
('newton_laws',      'sound',              'leads-to'),

-- chemistry
('periodic_table',   'chemical_reactions', 'prerequisite'),
('periodic_table',   'acids_bases',        'prerequisite'),
('periodic_table',   'carbon_compounds',   'prerequisite'),
('chemical_reactions','acids_bases',       'co-requisite'),
('chemical_reactions','carbon_compounds',  'leads-to'),

-- history connections
('mughal_empire',    'indian_independence','leads-to'),
('french_revolution','nationalism_india',  'leads-to'),
('nationalism_india','indian_independence','leads-to'),

-- geography connections
('geography_india',  'resources_development','leads-to'),
('resources_development','democracy_politics','leads-to')

ON CONFLICT (from_id, to_id, type) DO NOTHING;


-- ─────────────────────────────────────────────────────────────
-- 3. MISCONCEPTION REMEDIATIONS TABLE + DATA
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS curriculum_graph.misconception_remediations (
    id                    BIGSERIAL PRIMARY KEY,
    concept_id            TEXT NOT NULL REFERENCES curriculum_graph.concepts(id),
    misconception_pattern TEXT NOT NULL,
    remediation_text      TEXT NOT NULL,
    worked_example        TEXT DEFAULT '',
    analogy_hint          TEXT DEFAULT '',
    created_at            TIMESTAMPTZ DEFAULT now()
);

-- Idempotent: only insert if pattern not already there for that concept
INSERT INTO curriculum_graph.misconception_remediations
    (concept_id, misconception_pattern, remediation_text, worked_example, analogy_hint)
SELECT v.concept_id, v.misconception_pattern, v.remediation_text, v.worked_example, v.analogy_hint
FROM (VALUES
    -- FRACTIONS
    ('fractions',
     'reversed numerator denominator',
     'The denominator tells us how many equal parts the whole is split into; the numerator tells us how many of those parts we are talking about. Think of a pizza cut into 4 slices (denominator = 4). If you eat 3 slices, that is 3/4 — top number is what you have, bottom is the total.',
     'Write 3 out of 8 equal parts: numerator = 3, denominator = 8 → 3/8.',
     'Denominator = Down below = Divides the whole.'),

    ('fractions',
     'addition keeps denominator',
     'When adding fractions with different denominators you must first find a common denominator. You cannot just add numerators and denominators separately.',
     '1/3 + 1/4: find LCM(3,4)=12 → 4/12 + 3/12 = 7/12. NOT 2/7.',
     'You cannot add apples and oranges without first converting to a common unit.'),

    ('fractions',
     'bigger denominator means bigger fraction',
     'A larger denominator means each piece is SMALLER, so the fraction is actually smaller. 1/10 is less than 1/2 even though 10 is greater than 2.',
     'Cut a pizza into 2: each slice = 1/2. Cut into 10: each slice = 1/10. More cuts means smaller pieces.',
     'More people sharing the same pizza means less for each person.'),

    -- BODMAS
    ('bodmas',
     'left to right always',
     'In BODMAS, operations inside brackets come first, then exponents/orders, then multiplication and division (left to right), then addition and subtraction (left to right). Multiplication does NOT always come before division — they are the same priority, resolved left to right.',
     '6 / 2 x 3 = (6 / 2) x 3 = 3 x 3 = 9, not 6 / (2x3) = 1.',
     'BODMAS is a rank system, not a step-by-step queue.'),

    ('bodmas',
     'addition before multiplication',
     'Multiplication and division outrank addition and subtraction regardless of position.',
     '2 + 3 x 4 = 2 + 12 = 14, not 5 x 4 = 20.',
     'Multiplication is a fast lane — it jumps the queue over addition.'),

    -- NEWTON LAWS
    ('newton_laws',
     'heavier falls faster',
     'Galileo showed that in the absence of air resistance, all objects fall with the same acceleration due to gravity (approximately 9.8 m/s squared) regardless of mass. A feather and a hammer dropped on the Moon (no air) hit the ground together.',
     'Astronaut David Scott dropped a hammer and feather on the Moon in 1971 — they landed simultaneously.',
     'Gravity pulls harder on heavier things, but heavier things also resist acceleration more — the two effects exactly cancel.'),

    ('newton_laws',
     'objects need force to keep moving',
     'Newtons First Law: an object in motion stays in motion unless an unbalanced force acts on it. Friction and air drag are forces that slow things down — without them, no force is needed to keep moving.',
     'A ball rolling on a frictionless ice rink would roll forever.',
     'In space, the Voyager probe is still moving decades after its engines switched off.'),

    -- PHOTOSYNTHESIS
    ('photosynthesis',
     'plants get food from soil',
     'Plants make their own food using sunlight, carbon dioxide (from air) and water. The soil provides only minerals and water — not food. The food (glucose) is manufactured inside the leaf using light energy.',
     '6CO2 + 6H2O + light gives C6H12O6 + 6O2. CO2 comes from air, not soil.',
     'Plants are solar-powered kitchens — they cook their own glucose using sunlight.'),

    ('photosynthesis',
     'photosynthesis happens at night',
     'Photosynthesis requires light and stops (or slows greatly) in darkness. Respiration happens day and night, but photosynthesis only happens in the presence of light.',
     'A plant kept in a dark room for several days will consume its own starch reserves and wilt.',
     'Photosynthesis is like a solar panel — it only generates energy when the sun is shining.'),

    -- ELECTRICITY
    ('electricity',
     'current flows from negative to positive',
     'Conventional current is defined as flowing from the positive terminal to the negative terminal (outside the battery). Electrons actually flow the other way, but by convention current direction is opposite to electron flow.',
     'In circuit diagrams current arrows point from + to −. Electrons move from − to +.',
     'Conventional current is a historical convention — we use it because it was defined before electrons were discovered.'),

    -- PERIODIC TABLE / ATOMS
    ('periodic_table',
     'atom is smallest particle of matter',
     'Atoms are the smallest unit of an element that retains chemical properties, but atoms themselves are made of subatomic particles: protons, neutrons and electrons. The atom is NOT indivisible.',
     'Hydrogen atom: 1 proton + 0 neutrons + 1 electron.',
     'An atom is like a tiny solar system — the nucleus (sun) at the centre, electrons (planets) orbiting it.'),

    -- DECIMALS
    ('decimals',
     'more digits means bigger number',
     'The position of the decimal point determines the value. 0.9 is greater than 0.15 even though 0.15 has more digits.',
     '0.9 = 9/10; 0.15 = 15/100 = 3/20. Since 9/10 = 18/20 is greater than 3/20, 0.9 is larger.',
     'Think of tenths as larger coins and hundredths as smaller coins.'),

    -- CELL BIOLOGY
    ('cell_biology',
     'mitochondria makes food',
     'Mitochondria release energy FROM food (ATP synthesis via cellular respiration). The food-making happens in chloroplasts during photosynthesis, but only in plant cells.',
     'Mitochondria: C6H12O6 + O2 gives CO2 + H2O + ATP (energy released).',
     'Mitochondria are the power plant — they burn fuel to generate electricity, not produce the fuel.'),

    -- PERCENTAGE
    ('percentage',
     'percent means divide by 10',
     'Per-cent means per hundred. To convert a fraction to percent, multiply by 100. To find x% of a number, multiply by x/100.',
     '3/4 as percent = 3/4 x 100 = 75%. To find 20% of 50: 50 x 20/100 = 10.',
     'Per-cent = per hundred. Think of a 100-square grid: 75% means 75 squares are shaded.'),

    -- MAGNETISM
    ('magnetism',
     'same poles attract',
     'Like poles (N-N or S-S) REPEL each other. Only unlike poles (N-S) attract. This is a common reversal of the rule.',
     'Two north poles held close will push apart. A north pole and south pole will pull together.',
     'Just like in relationships — opposites attract, likes repel.')

) AS v(concept_id, misconception_pattern, remediation_text, worked_example, analogy_hint)
WHERE NOT EXISTS (
    SELECT 1 FROM curriculum_graph.misconception_remediations mr
    WHERE mr.concept_id = v.concept_id
      AND mr.misconception_pattern = v.misconception_pattern
);
