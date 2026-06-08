"""
Per-call latency tracker.

Records STT, LLM, and TTS time for every turn and prints a
summary at the end of the call — used for the video walkthrough
and the written latency question in the assessment.
"""

from dataclasses import dataclass, field


@dataclass
class TurnRecord:
    turn: int
    stt_ms: float
    llm_ms: float
    tts_ms: float

    @property
    def total_ms(self) -> float:
        return self.stt_ms + self.llm_ms + self.tts_ms


@dataclass
class LatencyTracker:
    records: list[TurnRecord] = field(default_factory=list)

    def record(self, turn: int, stt_ms: float, llm_ms: float, tts_ms: float) -> None:
        self.records.append(TurnRecord(turn, stt_ms, llm_ms, tts_ms))

    def print_summary(self) -> None:
        if not self.records:
            return

        print("\n=== Latency Summary ===")
        print(f"  {'Turn':>4}  {'STT':>7}  {'LLM':>7}  {'TTS':>7}  {'Total':>8}")
        print("  " + "-" * 42)
        for r in self.records:
            print(f"  {r.turn:>4}  {r.stt_ms:>6.0f}ms  {r.llm_ms:>6.0f}ms  {r.tts_ms:>6.0f}ms  {r.total_ms:>7.0f}ms")

        stt_vals  = [r.stt_ms  for r in self.records if r.stt_ms  > 0]
        llm_vals  = [r.llm_ms  for r in self.records]
        tts_vals  = [r.tts_ms  for r in self.records]
        total_vals = [r.total_ms for r in self.records]

        def avg(vals): return sum(vals) / len(vals) if vals else 0

        print("  " + "-" * 42)
        print(f"  {'avg':>4}  {avg(stt_vals):>6.0f}ms  {avg(llm_vals):>6.0f}ms  {avg(tts_vals):>6.0f}ms  {avg(total_vals):>7.0f}ms")
        print(f"  {'max':>4}  {max(stt_vals or [0]):>6.0f}ms  {max(llm_vals):>6.0f}ms  {max(tts_vals):>6.0f}ms  {max(total_vals):>7.0f}ms")
        print(f"\n  Target budget: STT <800ms | LLM <1500ms | TTS <500ms | Total <2500ms")

        over_budget = [r for r in self.records if r.total_ms > 2500]
        if over_budget:
            print(f"  Turns over budget: {[r.turn for r in over_budget]}")
        else:
            print(f"  All turns within 2500ms budget ✓")
