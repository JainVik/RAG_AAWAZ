import { describe, expect, it } from 'vitest';
import { formatResponseLatency, getResponseLatencyMs } from './responseTiming';

describe('response timing', () => {
  it('uses the backend measured final-audio/text-query response total', () => {
    expect(
      getResponseLatencyMs({
        total_after_final_audio: 128.42,
        total_duration_ms: 999,
      }),
    ).toBe(128.42);
  });

  it('omits legacy, missing, or invalid measurements', () => {
    expect(getResponseLatencyMs({ total_duration_ms: 75 })).toBeNull();
    expect(getResponseLatencyMs({ total_after_final_audio: Number.NaN })).toBeNull();
    expect(getResponseLatencyMs({ total_after_final_audio: -1 })).toBeNull();
    expect(getResponseLatencyMs(undefined)).toBeNull();
  });

  it('formats milliseconds and slower responses compactly', () => {
    expect(formatResponseLatency(128.42)).toBe('128 ms');
    expect(formatResponseLatency(1_245)).toBe('1.25 s');
  });
});
