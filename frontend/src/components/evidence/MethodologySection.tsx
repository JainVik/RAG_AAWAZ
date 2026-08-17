import { useState } from 'react';
import { CaretDown, BookOpen, ShieldCheck, LockKey } from '@phosphor-icons/react';
import type { ProvenanceInfo } from '../../types/api';

interface MethodologySectionProps {
  provenance: ProvenanceInfo;
}

export const MethodologySection: React.FC<MethodologySectionProps> = ({ provenance }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="refractive-glass-card refractive-glass-card-primary overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-6 sm:p-8 flex items-center justify-between text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.04] transition-colors cursor-pointer"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-blue-500/10 dark:bg-blue-500/15 border border-blue-400/30 text-blue-600 dark:text-blue-300">
            <BookOpen size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-black dark:text-white tracking-tight">
              Methodology &amp; Cryptographic Provenance
            </h2>
            <p className="text-xs text-black dark:text-slate-400">
              Evaluation constraints, frozen threshold contracts, and artifact cryptographic verification
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs font-semibold text-black dark:text-slate-400">
          <span>{isOpen ? 'Collapse' : 'Expand details'}</span>
          <CaretDown
            size={18}
            className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          />
        </div>
      </button>

      {isOpen && (
        <div className="p-6 sm:p-8 pt-0 border-t border-black/10 dark:border-white/10 space-y-6 text-xs text-black dark:text-slate-300 leading-relaxed font-sans">
          {/* Methodological Statements */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-black/[0.03] dark:bg-white/[0.04] border border-black/10 dark:border-white/10 rounded-xl space-y-1.5 transition-all hover:bg-black/[0.06] dark:hover:bg-white/[0.07]">
              <span className="font-bold text-black dark:text-white flex items-center gap-1.5 text-xs">
                <ShieldCheck size={16} className="text-blue-600 dark:text-blue-400" />
                <span>Deterministic Evaluation Scope</span>
              </span>
              <p className="text-black dark:text-slate-400">
                The 100-query benchmark is an audited evaluation measured across 100 test queries. Results depend strictly on this corpus, index version, dense embedding model, and router contract. Retrieval quality measures passage presence and does not guarantee generation correctness.
              </p>
            </div>

            <div className="p-4 bg-black/[0.03] dark:bg-white/[0.04] border border-black/10 dark:border-white/10 rounded-xl space-y-1.5 transition-all hover:bg-black/[0.06] dark:hover:bg-white/[0.07]">
              <span className="font-bold text-black dark:text-white flex items-center gap-1.5 text-xs">
                <LockKey size={16} className="text-blue-600 dark:text-blue-400" />
                <span>Confidence &amp; Speech Standards</span>
              </span>
              <p className="text-black dark:text-slate-400">
                Sarvam realtime speech events do not provide recognition confidence scores. In adherence to Section 3.5, confidence is reported as unavailable and never fabricated. Raw audio and evaluation records are never persisted in the browser.
              </p>
            </div>
          </div>

          {/* Provenance Hashes */}
          <div className="space-y-2">
            <span className="font-bold text-black dark:text-white uppercase tracking-wider text-[11px] block">
              Cryptographic Artifact Hashes (SHA256)
            </span>
            <div className="p-4 bg-black/[0.03] dark:bg-black/40 border border-black/10 dark:border-white/10 rounded-xl space-y-2 font-mono text-[11px] backdrop-blur-sm">
              {Object.entries(provenance.artifact_hashes).map(([file, hash]) => (
                <div key={file} className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 py-1 border-b border-black/5 dark:border-white/5 last:border-0">
                  <span className="text-blue-600 dark:text-blue-300 font-semibold">{file}</span>
                  <span className="text-black dark:text-slate-400 truncate max-w-md" title={String(hash)}>
                    {String(hash)}
                  </span>
                </div>
              ))}
              {Object.keys(provenance.artifact_hashes).length === 0 && (
                <span className="text-slate-500">No verified artifact hashes were returned.</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
