"""
Generate WAV files for the three demo call scenarios.

Each scenario is a list of caller turn texts that are synthesised
to WAV files.  During a video walkthrough you can play them back
with  `python main.py --file demo_audio/<file>.wav`  instead of
speaking into the mic — making the recording reliable and repeatable.

Run once from the project root:
    python demo_audio/generate_demo.py
"""

import os
import sys

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.tts import speak

OUTPUT_DIR = os.path.dirname(__file__)


SCENARIOS = {
    # Scenario A — full happy path: employment law, booking confirmed
    "scenario_a_employment_booking": [
        "Hello, I was dismissed from my job last month and I want to know my rights.",
        "Yes I was employed there for three years and then they let me go without any warning.",
        "It happened about six weeks ago.",
        "Yes I would like to book a consultation please.",
        "My name is Sarah Johnson.",
        "My email is sarah dot johnson at gmail dot com.",
        "My phone number is zero seven seven one two three four five six seven.",
        "Tuesday at ten would be great.",
        "Yes all of those details are correct.",
    ],

    # Scenario B — low-confidence STT path: name/email uncertain, agent confirms
    "scenario_b_stt_confidence": [
        "Hi I need help with a tenancy dispute.",
        "I am the tenant and my landlord has refused to return my deposit.",
        "It is a private rental and it has been two months now.",
        "Yes I would like to book an appointment.",
        "My name is Aleksei Novak.",
        "My email is a dot novak at outlook dot com.",
        "My phone is zero seven eight nine nine eight seven six five four.",
        "Friday afternoon would work well for me.",
        "Yes those details are correct.",
    ],

    # Scenario C — human handoff: emergency custody hearing today
    "scenario_c_emergency_transfer": [
        "I desperately need legal help right now.",
        "I have a child custody hearing in court today at two pm and I have no representation.",
        "Is there anyone who can help me urgently?",
    ],
}


def generate_all() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for scenario_name, turns in SCENARIOS.items():
        print(f"\n--- Generating: {scenario_name} ---")
        for i, text in enumerate(turns, start=1):
            filename = f"{scenario_name}_turn{i:02d}.wav"
            path = os.path.join(OUTPUT_DIR, filename)
            print(f"  Turn {i}: \"{text[:60]}{'...' if len(text) > 60 else ''}\"")
            speak(text, save_path=path)
            print(f"          → {filename}")

    print("\nAll demo audio files generated.")
    print(f"Location: {OUTPUT_DIR}")
    print("\nPlay a single turn with:")
    print("  python main.py --file demo_audio/<filename>.wav")


if __name__ == "__main__":
    generate_all()
