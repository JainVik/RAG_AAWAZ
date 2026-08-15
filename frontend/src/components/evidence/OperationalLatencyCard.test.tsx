import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { OperationalMetrics } from '../../types/api';
import { OperationalLatencyCard } from './OperationalLatencyCard';

const metrics: OperationalMetrics = {
  requests_total: 12,
  latency_sample_count: 10,
  latency_ms: { p50: 80, p70: 100, p95: 150, p100: 190 },
  timings_ms: {
    input_guarded: { count: 10, p50: 0.1, p70: 0.2, p95: 0.3, p100: 0.4 },
    retrieved: { count: 10, p50: 42, p70: 55, p95: 90, p100: 120 },
  },
  groq_synthesis: {
    latency_sample_count: 2,
    latency_ms: { p50: 500, p70: 520, p95: 550, p100: 560 },
  },
};

describe('OperationalLatencyCard', () => {
  it('labels volatile process telemetry separately from qualifying evidence', () => {
    const markup = renderToStaticMarkup(<OperationalLatencyCard metrics={metrics} />);
    expect(markup).toContain('Live process performance');
    expect(markup).toContain('Operational · non-qualifying');
    expect(markup).toContain('10 timed responses from 12 process requests');
    expect(markup).toContain('P95');
    expect(markup).toContain('190.0 ms');
    expect(markup).toContain('Embedding + hybrid retrieval');
    expect(markup).toContain('Optional Groq synthesis');
  });

  it('does not invent aggregate timing before a process sample exists', () => {
    const markup = renderToStaticMarkup(<OperationalLatencyCard metrics={null} />);
    expect(markup).toContain('Live timing is not available yet');
    expect(markup).not.toContain('0.00 ms');
  });
});
