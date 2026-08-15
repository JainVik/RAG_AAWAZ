import { describe, expect, it } from 'vitest';
import { formatStageLatency, getCoreLatencySummary } from './pipelineLatency';

describe('getCoreLatencySummary', () => {
  it('sums the five sequential core stages without relabeling the canonical total', () => {
    const summary = getCoreLatencySummary({
      input_guarded: 0.1,
      retrieved: 40,
      evidence_selected: 2,
      answered: 0.4,
      verified: 0.2,
      total_after_final_audio: 91,
      stt_finalize: 45,
      speculative_retrieval: 160,
    });

    expect(summary?.subtotalMs).toBeCloseTo(42.7);
    expect(summary?.totalAfterFinalInputMs).toBe(91);
    expect(summary?.stages).toHaveLength(5);
  });

  it('shows observed stages but withholds a subtotal for an early abstention', () => {
    const summary = getCoreLatencySummary({
      input_guarded: 0.1,
      retrieved: 30,
      total_after_final_audio: 35,
    });

    expect(summary?.subtotalMs).toBeNull();
    expect(summary?.stages.filter((stage) => stage.durationMs !== null)).toHaveLength(2);
  });

  it('rejects invalid timings instead of presenting them as zero', () => {
    const summary = getCoreLatencySummary({
      input_guarded: Number.NaN,
      retrieved: -1,
    });
    expect(summary).toBeNull();
  });

  it('keeps sub-millisecond stages visible', () => {
    expect(formatStageLatency(0.089)).toBe('0.09 ms');
    expect(formatStageLatency(2.53)).toBe('2.5 ms');
    expect(formatStageLatency(79.72)).toBe('79.7 ms');
  });
});
