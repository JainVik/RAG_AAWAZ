import React, { useEffect, useState } from 'react';
import {
  CircleNotch,
  ShieldCheck,
  WarningOctagon,
} from '@phosphor-icons/react';
import type {
  EvidenceSummary,
} from '../types/api';
import { getEvidenceSummary } from '../services/api';
import { CorpusIndexCard } from '../components/evidence/CorpusIndexCard';
import { ChunkRepresentationsCard } from '../components/evidence/ChunkRepresentationsCard';
import { LatencyAnalyticsCard } from '../components/evidence/LatencyAnalyticsCard';
import { GuardrailEvidenceCard } from '../components/evidence/GuardrailEvidenceCard';
import { MethodologySection } from '../components/evidence/MethodologySection';

export const EvidencePage: React.FC = () => {
  const [evidence, setEvidence] = useState<EvidenceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchEvidence = async () => {
    setLoading(true);
    setError(null);
    try {
      const summary = await getEvidenceSummary();
      setEvidence(summary);
    } catch (err) {
      setEvidence(null);
      setError(err instanceof Error ? err.message : 'Evidence request failed.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchEvidence();
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-8 py-6">
      {/* Header */}
      <header className="border-b border-black/10 dark:border-white/10 pb-4">
        <div>
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-700 dark:text-blue-300">
            <ShieldCheck size={14} /> System Evidence &amp; Verification
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-black dark:text-white">System Evidence</h1>
          <p className="mt-1 max-w-2xl text-sm text-black dark:text-slate-400">
            Measured evaluation metrics, chunking strategies, vector index footprint, 100-query latency percentiles (P50/P70/P100), and guardrail verification.
          </p>
        </div>
      </header>

      {error && (
        <div className="glass-inner-box text-rose-800 dark:text-rose-300 p-6">
          <div className="flex gap-3">
            <WarningOctagon size={24} className="shrink-0 text-rose-500 dark:text-rose-400" />
            <div>
              <h2 className="font-bold text-black dark:text-white">Evidence endpoint unavailable</h2>
              <p className="text-xs text-rose-700 dark:text-rose-300">{error}</p>
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="py-20 text-center">
          <CircleNotch size={36} className="mx-auto animate-spin text-blue-600 dark:text-blue-400" />
          <p className="mt-3 text-sm text-black dark:text-slate-300">Loading system evidence…</p>
        </div>
      )}

      {evidence && !loading && (
        <div className="space-y-8">
          {/* Section 1: Corpus Vector Index */}
          <section aria-labelledby="section-corpus-index">
            <CorpusIndexCard corpus={evidence.corpus} />
          </section>

          {/* Section 2: Chunking Strategies & Five Retrieval Representations */}
          <section aria-labelledby="section-representations">
            <ChunkRepresentationsCard representations={evidence.chunk_representations} />
          </section>

          {/* Section 3: Latency Analytics (100 Test Queries with P50 / P70 / P100 Numbers & Full/Short Breakdown) */}
          <section aria-labelledby="section-latency">
            <LatencyAnalyticsCard />
          </section>

          {/* Section 4: Guardrail Setup */}
          <section aria-labelledby="section-guardrails">
            <GuardrailEvidenceCard guardrails={evidence.guardrails} />
          </section>

          {/* Section 5: Methodology, Provenance & System Limitations */}
          <section aria-labelledby="section-methodology">
            <MethodologySection provenance={evidence.provenance} />
          </section>
        </div>
      )}
    </div>
  );
};
