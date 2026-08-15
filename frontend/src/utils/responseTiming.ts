const CURRENT_RESPONSE_TOTAL = 'total_after_final_audio';
const SYNTHESIS_RESPONSE_TOTAL = 'total_synthesis';

export function getResponseLatencyMs(
  timings: Record<string, number> | null | undefined,
): number | null {
  const value = timings?.[CURRENT_RESPONSE_TOTAL];
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

export function formatResponseLatency(milliseconds: number): string {
  if (milliseconds < 1_000) return `${Math.round(milliseconds)} ms`;
  const seconds = milliseconds / 1_000;
  return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
}

export function getSynthesisLatencyMs(
  timings: Record<string, number> | null | undefined,
): number | null {
  const value = timings?.[SYNTHESIS_RESPONSE_TOTAL];
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}
