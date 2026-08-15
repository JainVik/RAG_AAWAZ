export interface CoreLatencyStage {
  key: 'input_guarded' | 'retrieved' | 'evidence_selected' | 'answered' | 'verified';
  label: string;
  shortLabel: string;
  durationMs: number | null;
}

export interface CoreLatencySummary {
  stages: CoreLatencyStage[];
  subtotalMs: number | null;
  totalAfterFinalInputMs: number | null;
}

const CORE_STAGE_DEFINITIONS: ReadonlyArray<
  Pick<CoreLatencyStage, 'key' | 'label' | 'shortLabel'>
> = [
  { key: 'input_guarded', label: 'Input safety', shortLabel: 'Safety' },
  { key: 'retrieved', label: 'Embedding, hybrid search & fusion', shortLabel: 'Hybrid search' },
  { key: 'evidence_selected', label: 'Evidence window selection', shortLabel: 'Evidence' },
  { key: 'answered', label: 'Extractive answer assembly', shortLabel: 'Answer' },
  { key: 'verified', label: 'Grounding verification', shortLabel: 'Grounding' },
];

function finiteDuration(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

export function formatStageLatency(milliseconds: number): string {
  if (milliseconds < 1) return `${milliseconds.toFixed(2)} ms`;
  if (milliseconds < 10) return `${milliseconds.toFixed(1)} ms`;
  if (milliseconds < 1_000) return `${milliseconds.toFixed(1)} ms`;
  return `${(milliseconds / 1_000).toFixed(2)} s`;
}

export function getCoreLatencySummary(
  timings: Record<string, number> | null | undefined,
): CoreLatencySummary | null {
  if (!timings) return null;

  const stages = CORE_STAGE_DEFINITIONS.map((stage) => ({
    ...stage,
    durationMs: finiteDuration(timings[stage.key]),
  }));
  const measured = stages.filter(
    (stage): stage is CoreLatencyStage & { durationMs: number } => stage.durationMs !== null,
  );
  const totalAfterFinalInputMs = finiteDuration(timings.total_after_final_audio);

  if (measured.length === 0 && totalAfterFinalInputMs === null) return null;

  return {
    stages,
    // These five backend stages are sequential. A subtotal is only truthful when
    // every stage completed; partial/abstained paths must not treat missing values as zero.
    subtotalMs:
      measured.length === CORE_STAGE_DEFINITIONS.length
        ? measured.reduce((total, stage) => total + stage.durationMs, 0)
        : null,
    totalAfterFinalInputMs,
  };
}
