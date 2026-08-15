import React from 'react';
import { CheckCircle, MicrophoneStage, Warning } from '@phosphor-icons/react';
import type { VerifiedPromptCatalog } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface VerifiedPromptCoverageCardProps {
  catalog: VerifiedPromptCatalog | null;
  error: string | null;
}

export const VerifiedPromptCoverageCard: React.FC<VerifiedPromptCoverageCardProps> = ({
  catalog,
  error,
}) => {
  const clean = catalog
    ? catalog.coverage.conditions['clean-short'] + catalog.coverage.conditions['clean-long']
    : 0;
  const noisy = catalog
    ? catalog.coverage.conditions['noisy-short'] + catalog.coverage.conditions['noisy-long']
    : 0;

  return (
    <GlassSurface borderRadius={20} brightness={35} opacity={0.85} className="space-y-5 p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-violet-400/20 bg-violet-500/10 p-2.5 text-violet-300">
            <MicrophoneStage size={22} weight="bold" />
          </div>
          <div>
            <h2 className="font-bold text-white">Verified voice-question palette</h2>
            <p className="text-xs text-slate-400">
              Corpus-backed prompts prepared for the human voice benchmark
            </p>
          </div>
        </div>
        <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs font-semibold text-violet-200">
          Recording plan · not a benchmark
        </span>
      </div>

      {catalog ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Questions" value={catalog.total} />
            <Stat label="Text-validated" value={catalog.live_text_validated_count} />
            <Stat label="Clean / noisy" value={`${clean} / ${noisy}`} />
            <Stat
              label="Short / long"
              value={`${catalog.coverage.lengths.short} / ${catalog.coverage.lengths.long}`}
            />
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <Coverage label="Hindi" count={catalog.coverage.languages.hi} />
            <Coverage label="English" count={catalog.coverage.languages.en} />
            <Coverage label="Hindi + English" count={catalog.coverage.languages['hi-en']} />
          </div>
          <p className="flex items-start gap-2 rounded-xl border border-cyan-500/15 bg-cyan-500/5 px-4 py-3 text-xs text-slate-300">
            <CheckCircle size={16} weight="fill" className="mt-0.5 shrink-0 text-cyan-400" />
            Every prompt already completed against the live text retrieval path with cited evidence.
            Audio recording and voice-latency qualification are still measured separately.
          </p>
        </>
      ) : (
        <p className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/8 px-4 py-3 text-xs text-amber-200">
          <Warning size={16} className="mt-0.5 shrink-0" />
          {error ?? 'Verified question palette is unavailable.'}
        </p>
      )}
    </GlassSurface>
  );
};

const Stat = ({ label, value }: { label: string; value: string | number }) => (
  <div className="rounded-xl border border-white/8 bg-white/5 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
    <p className="mt-1 font-mono text-xl font-bold text-white">{value}</p>
  </div>
);

const Coverage = ({ label, count }: { label: string; count: number }) => (
  <div className="flex items-center justify-between rounded-xl border border-white/8 bg-white/5 px-4 py-3 text-xs">
    <span className="text-slate-300">{label}</span>
    <span className="font-mono font-bold text-cyan-300">{count}</span>
  </div>
);
