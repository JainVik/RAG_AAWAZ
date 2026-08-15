import React, { useEffect, useState } from 'react';
import {
  ArrowClockwise,
  CaretDown,
  Check,
  CircleNotch,
  Copy,
  DownloadSimple,
  ShieldCheck,
  WarningOctagon,
} from '@phosphor-icons/react';
import type {
  EvidenceStatus,
  EvidenceSummary,
  OperationalMetrics,
  VerifiedPromptCatalog,
} from '../types/api';
import { getEvidenceSummary, getOperationalMetrics, getVerifiedPrompts } from '../services/api';
import { useShell } from '../components/layout/Shell';
import { RetrievalEvaluationCard } from '../components/evidence/RetrievalEvaluationCard';
import { CorpusIndexCard } from '../components/evidence/CorpusIndexCard';
import { ChunkRepresentationsCard } from '../components/evidence/ChunkRepresentationsCard';
import { DatasetAuditCard } from '../components/evidence/DatasetAuditCard';
import { CorpusScalingCard } from '../components/evidence/CorpusScalingCard';
import { GuardrailEvidenceCard } from '../components/evidence/GuardrailEvidenceCard';
import { VoiceLatencyCard } from '../components/evidence/VoiceLatencyCard';
import { MethodologySection } from '../components/evidence/MethodologySection';
import { OperationalLatencyCard } from '../components/evidence/OperationalLatencyCard';
import { VerifiedPromptCoverageCard } from '../components/evidence/VerifiedPromptCoverageCard';
import GlassSurface from '../components/ui/GlassSurface';

const statusTone: Record<EvidenceStatus, string> = {
  qualifying: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  smoke_audit: 'text-cyan-300 border-cyan-500/30 bg-cyan-500/10',
  partial: 'text-amber-300 border-amber-500/30 bg-amber-500/10',
  non_qualifying: 'text-amber-300 border-amber-500/30 bg-amber-500/10',
  not_measured: 'text-slate-300 border-white/15 bg-white/5',
  invalid: 'text-rose-300 border-rose-500/30 bg-rose-500/10',
};

function displayTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export const EvidencePage: React.FC = () => {
  const [evidence, setEvidence] = useState<EvidenceSummary | null>(null);
  const [operational, setOperational] = useState<OperationalMetrics | null>(null);
  const [verifiedPrompts, setVerifiedPrompts] = useState<VerifiedPromptCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [verifiedPromptsError, setVerifiedPromptsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const { ready } = useShell();

  const fetchEvidence = async () => {
    setLoading(true);
    setError(null);
    setMetricsError(null);
    setVerifiedPromptsError(null);
    const [evidenceResult, metricsResult, verifiedPromptsResult] = await Promise.allSettled([
      getEvidenceSummary(),
      getOperationalMetrics(),
      getVerifiedPrompts(),
    ]);
    if (evidenceResult.status === 'fulfilled') {
      setEvidence(evidenceResult.value);
    } else {
      setEvidence(null);
      setError(
        evidenceResult.reason instanceof Error
          ? evidenceResult.reason.message
          : 'Evidence request failed.',
      );
    }
    if (metricsResult.status === 'fulfilled') {
      setOperational(metricsResult.value);
    } else {
      setOperational(null);
      setMetricsError(
        metricsResult.reason instanceof Error
          ? metricsResult.reason.message
          : 'Operational metrics request failed.',
      );
    }
    if (verifiedPromptsResult.status === 'fulfilled') {
      setVerifiedPrompts(verifiedPromptsResult.value);
    } else {
      setVerifiedPrompts(null);
      setVerifiedPromptsError(
        verifiedPromptsResult.reason instanceof Error
          ? verifiedPromptsResult.reason.message
          : 'Verified questions request failed.',
      );
    }
    setLoading(false);
  };

  useEffect(() => {
    void fetchEvidence();
  }, []);

  const copySummary = async () => {
    if (!evidence) return;
    await navigator.clipboard.writeText(
      JSON.stringify(
        {
          generated_at: evidence.generated_at,
          runtime_ready: ready?.status === 'ready',
          retrieval: evidence.retrieval,
          corpus: evidence.corpus,
          dataset_audit: evidence.dataset_audit,
          guardrails: evidence.guardrails,
          voice_latency: evidence.voice_latency,
          limitations: evidence.provenance.limitations,
        },
        null,
        2,
      ),
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const download = () => {
    if (!evidence) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(evidence, null, 2)], { type: 'application/json' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `vani-rag-evidence-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-8 py-6">
      <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-4 sm:flex-row sm:items-center">
        <div>
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-300">
            <ShieldCheck size={14} /> Measured system evidence
          </div>
          <h1 className="text-3xl font-extrabold text-white">Evaluation &amp; system evidence</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Qualifying results come from checked artifacts. Live process telemetry is measured and clearly labeled separately.
          </p>
          {evidence && (
            <p className="mt-2 text-[10px] font-mono text-slate-500">
              Evidence summary refreshed {displayTimestamp(evidence.generated_at)}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button type="button" disabled={loading} onClick={() => void fetchEvidence()} className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-xs text-white disabled:opacity-40">
            <ArrowClockwise className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button type="button" disabled={!evidence} onClick={() => void copySummary()} className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-xs text-white disabled:opacity-40">
            {copied ? <Check /> : <Copy />} {copied ? 'Copied' : 'Copy summary'}
          </button>
          <button type="button" disabled={!evidence} onClick={download} className="flex items-center gap-1.5 rounded-xl bg-cyan-600 px-3.5 py-2 text-xs font-bold text-white disabled:opacity-40">
            <DownloadSimple /> JSON
          </button>
        </div>
      </header>

      {error && (
        <GlassSurface borderRadius={20} brightness={35} opacity={0.9} className="border-red-500/40 bg-red-950/20 p-6">
          <div className="flex gap-3">
            <WarningOctagon size={24} className="shrink-0 text-red-400" />
            <div><h2 className="font-bold text-white">Evidence endpoint unavailable</h2><p className="text-xs text-red-300">{error}</p></div>
          </div>
        </GlassSurface>
      )}

      {loading && (
        <div className="py-20 text-center">
          <CircleNotch size={36} className="mx-auto animate-spin text-cyan-400" />
          <p className="mt-3 text-sm text-slate-300">Loading measured evidence…</p>
        </div>
      )}

      {evidence && !loading && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <SummaryCard title="Backend operational readiness" status={ready?.status === 'ready' ? 'READY' : 'NOT READY'} tone={ready?.status === 'ready' ? statusTone.qualifying : statusTone.non_qualifying} detail="Live /ready state; independent of benchmark qualification." />
            <SummaryCard title="Retrieval evaluation" status={evidence.retrieval.status.replaceAll('_', ' ').toUpperCase()} tone={statusTone[evidence.retrieval.status]} detail={`${evidence.retrieval.sample_count} retained rows · ${evidence.retrieval.failure_count} failures`} />
            <SummaryCard title="Guardrail evaluation" status={evidence.guardrails.status.replaceAll('_', ' ').toUpperCase()} tone={statusTone[evidence.guardrails.status]} detail={`${evidence.guardrails.observed_correct_count}/${evidence.guardrails.sample_count} correct`} />
            <SummaryCard title="Voice latency evaluation" status={evidence.voice_latency.status.replaceAll('_', ' ').toUpperCase()} tone={statusTone[evidence.voice_latency.status]} detail={`${evidence.voice_latency.sample_count} measured rows`} />
          </div>
          <OperationalLatencyCard metrics={operational} error={metricsError} />
          <RetrievalEvaluationCard metrics={evidence.retrieval} />
          <CorpusIndexCard corpus={evidence.corpus} />
          <ChunkRepresentationsCard representations={evidence.chunk_representations} />
          <VerifiedPromptCoverageCard
            catalog={verifiedPrompts}
            error={verifiedPromptsError}
          />
          <GuardrailEvidenceCard guardrails={evidence.guardrails} />
          <VoiceLatencyCard latency={evidence.voice_latency} />

          <details className="overflow-hidden rounded-2xl border border-white/10 bg-[#0e1424] shadow-sm">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-6 text-left sm:p-8">
              <div>
                <h2 className="font-bold text-white">Supporting dataset &amp; capacity diagnostics</h2>
                <p className="mt-1 text-xs text-slate-400">Audit detail retained for evaluators without crowding the primary evidence story.</p>
              </div>
              <CaretDown size={18} className="shrink-0 text-slate-400" />
            </summary>
            <div className="space-y-6 border-t border-white/10 p-4 sm:p-6">
              <DatasetAuditCard audit={evidence.dataset_audit} />
              {evidence.corpus_scaling.status !== 'not_measured' && (
                <CorpusScalingCard scaling={evidence.corpus_scaling} />
              )}
            </div>
          </details>
          <MethodologySection provenance={evidence.provenance} />
        </>
      )}
    </div>
  );
};

const SummaryCard = ({ title, status, tone, detail }: { title: string; status: string; tone: string; detail: string }) => (
  <GlassSurface borderRadius={20} brightness={35} opacity={0.85} className="p-5">
    <div className="flex items-start justify-between gap-3">
      <div><h2 className="text-sm font-bold text-white">{title}</h2><p className="mt-1 text-xs text-slate-400">{detail}</p></div>
      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-bold ${tone}`}>{status}</span>
    </div>
  </GlassSurface>
);
