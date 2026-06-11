"""
15 real Indian school children — scripted for simulation.

Each persona is designed to trigger specific agent signals:
  - breakthrough, belief, struggle, connection, awe episodes
  - curiosity threads (why-questions, pushback, speculation)
  - misconceptions the evaluator will catch
  - emotion arcs (starts neutral, moves to engaged/frustrated/amazed)
  - linguistic register (Hindi, English, Hinglish)

Used by simulate_students.py and demo.html.
"""

PERSONAS = [
    {
        "id": "arjun_s8",
        "name": "Arjun",
        "grade": 8,
        "subject": "Science",
        "avatar": "🏏",
        "desc": "Cricket-obsessed, fast connector, overconfident",
        "messages": [
            "why does a cricket ball swing in the air?",
            "oh! so it's the same as an airplane wing — pressure difference on both sides",
            "wait but then how does a googly spin backwards? the seam is pointing the wrong way",
            "that's insane. the wrist flick creates a different pressure zone entirely. I never thought physics was IN cricket",
            "so heavier balls would swing more right? because more momentum",
        ],
    },
    {
        "id": "priya_s6",
        "name": "Priya",
        "grade": 6,
        "subject": "Science",
        "avatar": "🌱",
        "desc": "Deep why-questions, makes surprising connections",
        "messages": [
            "why do plants need sunlight? can't they just eat the soil?",
            "ohh they make their own food! that's so cool, but how do they KNOW how to do that",
            "wait that's like a factory inside the leaf? same as how our stomach digests?",
            "yaar that's crazy — both plants and us are just running chemical reactions",
            "so if I put a plant in space with artificial light it would still work?",
        ],
    },
    {
        "id": "rohan_s9",
        "name": "Rohan",
        "grade": 9,
        "subject": "Mathematics",
        "avatar": "😰",
        "desc": "Exam anxiety, overconfident on basics, freezes on applications",
        "messages": [
            "I know trigonometry already, we did it last year",
            "wait what is this sin(A+B) formula, I've never seen this",
            "I can't do this, it makes no sense, why are there so many formulas",
            "okay wait — so it comes from drawing the triangle inside a unit circle?",
            "oh I get it now. The formula is just geometry hidden as algebra",
        ],
    },
    {
        "id": "ananya_s7",
        "name": "Ananya",
        "grade": 7,
        "subject": "Science",
        "avatar": "🔬",
        "desc": "Bilingual Hinglish, unexpected cross-domain leaps",
        "messages": [
            "yeh osmosis kya hota hai exactly?",
            "toh matlab water apne aap move karta hai? without anyone pushing it?",
            "same as how smell spreads in a room na — diffusion waisa hi hai",
            "lekin agar dono sides pe equal concentration ho toh kuch nahi hoga?",
            "that's like equilibrium in economics! supply and demand balancing",
        ],
    },
    {
        "id": "dev_s10",
        "name": "Dev",
        "grade": 10,
        "subject": "Mathematics",
        "avatar": "🎮",
        "desc": "Fast learner, gets bored, uses gaming references",
        "messages": [
            "calculus seems easy just tell me the rules",
            "okay but why does differentiation give the slope — I want the actual reason not just the formula",
            "ohh it's like finding the instantaneous speed — same as lag compensation in gaming",
            "so integration is just differentiation in reverse? like respawning?",
            "what if the function has a sharp corner — is the derivative undefined there?",
        ],
    },
    {
        "id": "sneha_s6",
        "name": "Sneha",
        "grade": 6,
        "subject": "Science",
        "avatar": "🌸",
        "desc": "Shy, Hindi-dominant, sudden breakthroughs",
        "messages": [
            "mujhe light ke baare mein samajhna hai",
            "toh light ko reflect karne ke liye surface smooth hona chahiye?",
            "par mirror pe toh hum apna chehra dekhte hain aur paani mein bhi... same reason?",
            "acha samjha! dono mein surface flat hai isliye image banti hai",
            "toh agar paani mein lehren hon toh image distort ho jaati hai kyunki surface uneven ho jaata hai",
        ],
    },
    {
        "id": "kabir_s8",
        "name": "Kabir",
        "grade": 8,
        "subject": "Science",
        "avatar": "⚡",
        "desc": "Argumentative pushback style, enjoys being wrong",
        "messages": [
            "I thought electricity travels at the speed of light",
            "but that can't be right — electrons are heavy particles, they can't move that fast",
            "wait so the ELECTRONS are slow but the SIGNAL is fast? how is that possible",
            "ohh like a pipe full of water — push one end and the other end moves immediately even though the water molecules didn't travel",
            "are you sure? that seems too weird. the electrons never actually reach the light bulb?",
        ],
    },
    {
        "id": "meera_s7",
        "name": "Meera",
        "grade": 7,
        "subject": "Mathematics",
        "avatar": "📐",
        "desc": "Struggles with fractions, needs encouragement, gives up easily",
        "messages": [
            "I can't do fractions, I give up",
            "what's the point of dividing fractions, when do you even use this",
            "bahut mushkil hai, I never get it right in tests",
            "okay if I think of it as sharing pizza... 1/2 divided by 1/4 means how many quarter slices fit in half a pizza?",
            "that's 2! oh my god I actually got it. So I just flip the second fraction?",
        ],
    },
    {
        "id": "rishi_s9",
        "name": "Rishi",
        "grade": 9,
        "subject": "Science",
        "avatar": "🌌",
        "desc": "Science enthusiast, makes awe moments, cross-domain connections",
        "messages": [
            "how does DNA actually store information?",
            "so it's literally a 4-letter code? like binary but with 4 symbols instead of 2?",
            "NO WAY. DNA is the same concept as a computer hard drive but made of chemistry",
            "so the same information theory that Shannon invented for computers works for biology?",
            "what's the error correction mechanism? computers have checksums — does DNA have something like that?",
        ],
    },
    {
        "id": "aisha_s6",
        "name": "Aisha",
        "grade": 6,
        "subject": "Science",
        "avatar": "🌾",
        "desc": "Rural background, farming family, strong intuitive physics",
        "messages": [
            "why does my dadi say crops grow better in black soil?",
            "toh black soil mein zyada nutrients hote hain? like fertilizer already inside?",
            "hamare khet mein bhi black soil hai aur actually better crops aate hain wahan",
            "and in science class we learned about minerals — toh yeh wahi minerals hain jo plants eat?",
            "so when it rains the water carries minerals from the top down to the roots?",
        ],
    },
    {
        "id": "vikram_s10",
        "name": "Vikram",
        "grade": 10,
        "subject": "Mathematics",
        "avatar": "💪",
        "desc": "Overconfident, attributes failure to bad teaching not effort",
        "messages": [
            "probability is easy, I always thought it was just common sense",
            "the Monty Hall problem is obviously 50-50, any answer other than that is wrong",
            "that makes no sense, you can't convince me switching matters",
            "okay fine I worked it out with all the cases... switching wins 2 out of 3 times",
            "I always thought probability was about intuition but actually it's about listing all cases systematically",
        ],
    },
    {
        "id": "tara_s7",
        "name": "Tara",
        "grade": 7,
        "subject": "Science",
        "avatar": "🦋",
        "desc": "Likes teaching back, needs to explain to understand",
        "messages": [
            "can you explain gravity to me like I'm going to teach it to someone else",
            "okay so I would say: gravity is a force between any two masses, bigger mass pulls harder",
            "and if someone asks me why the moon doesn't fall — I would say it IS falling, just sideways fast enough to keep missing Earth",
            "is that right? the moon is basically in permanent free fall?",
            "that's the same as the ISS! the astronauts feel weightless because they're also falling alongside the station",
        ],
    },
    {
        "id": "aryan_s8",
        "name": "Aryan",
        "grade": 8,
        "subject": "Science",
        "avatar": "🔥",
        "desc": "Overconfident on new topics, surprised by complexity",
        "messages": [
            "magnetism is easy, opposite poles attract same poles repel, I already know this",
            "wait what is this — magnetic field lines and flux and permeability, I thought it was simple",
            "I can't do this, too many new terms at once",
            "okay slow down — so a moving charge creates a magnetic field? electricity and magnetism are the SAME thing?",
            "that's wild. I always thought they were completely separate. Maxwell unified them?",
        ],
    },
    {
        "id": "lakshmi_s9",
        "name": "Lakshmi",
        "grade": 9,
        "subject": "Mathematics",
        "avatar": "📊",
        "desc": "Methodical, needs every step shown, high conscientiousness",
        "messages": [
            "please show me how to solve quadratic equations step by step",
            "okay I understand the factoring method, can you show me one more example before I try",
            "for the discriminant formula — if b squared minus 4ac is negative what does that mean exactly",
            "so no real solutions means the parabola never touches the x-axis? can you show me the graph?",
            "now I want to solve one myself — please tell me if each step is correct as I go",
        ],
    },
    {
        "id": "siddharth_s6",
        "name": "Siddharth",
        "grade": 6,
        "subject": "Science",
        "avatar": "✨",
        "desc": "Easily amazed, generates awe moments, high curiosity",
        "messages": [
            "how big is the universe?",
            "that can't be right — the observable universe is 93 BILLION light years across but it's only 13 billion years old?",
            "no way. light from some places will NEVER reach us because space is expanding faster than light?",
            "that means there are stars we can never ever see. ever. that is the most insane thing I have ever heard",
            "so the universe could be infinite and we'd never know? we're just stuck in our little bubble forever?",
        ],
    },
]


def get_persona(persona_id: str) -> dict | None:
    return next((p for p in PERSONAS if p["id"] == persona_id), None)
