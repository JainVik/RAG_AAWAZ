import React from 'react';
import type { QueryResponse, SynthesisResponse, VoiceState } from '../../types/api';
import { VoiceOrb } from '../voice/VoiceOrb';
import { AnswerCards } from '../voice/AnswerCards';

interface ChatAssistantMessageProps {
  result?: QueryResponse | null;
  synthesisLoading?: boolean;
  synthesisResult?: SynthesisResponse | null;
  synthesisError?: string | null;
  isLive?: boolean;
  liveState?: VoiceState;
  audioLevel?: number;
  liveTranscript?: string;
  onDismiss?: () => void;
}

export const ChatAssistantMessage: React.FC<ChatAssistantMessageProps> = ({
  result,
  synthesisLoading = false,
  synthesisResult = null,
  synthesisError = null,
  isLive = false,
  liveState = 'idle',
  audioLevel = 0,
  liveTranscript = '',
  onDismiss = () => {},
}) => {
  const isListening = isLive && liveState === 'recording';
  const isProcessing = isLive && liveState === 'processing';

  return (
    <div className="flex w-full justify-start select-none animate-fade-in my-4">
      <div className="flex flex-col items-start w-full max-w-5xl space-y-3">
        {/* Header with Mini Orb on Top-Left above response */}
        <div className="flex items-center gap-2.5 px-1 text-xs">
          <VoiceOrb
            state={isLive ? liveState : 'idle'}
            audioLevel={audioLevel}
            size="sm"
            animated={false}
          />
          <div className="flex items-center gap-2">
            <span className="font-extrabold text-sm tracking-tight text-white">
              VANI <span className="text-cyan-400">RAG</span>
            </span>
            <span className="text-slate-600">·</span>
            {isListening ? (
              <span className="text-[11px] font-bold text-cyan-300 animate-pulse flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                Listening to speech…
              </span>
            ) : isProcessing ? (
              <span className="text-[11px] font-bold text-violet-300 animate-pulse flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                Searching verified index &amp; synthesizing…
              </span>
            ) : (
              <span className="text-[11px] font-medium text-slate-400">
                Grounded Multilingual Evidence
              </span>
            )}
          </div>
        </div>

        {/* Live in-flight speech preview if listening */}
        {isListening && liveTranscript && (
          <div className="w-full max-w-2xl rounded-2xl border border-cyan-500/20 bg-cyan-950/20 p-4 backdrop-blur-xl">
            <p className="text-sm font-medium text-cyan-200 italic leading-relaxed">
              "{liveTranscript}"
            </p>
          </div>
        )}

        {/* Completed Response Cards (Includes Extractive Answer, Groq Synthesis, and Latency Table) */}
        {result && (
          <div className="w-full text-left">
            <AnswerCards
              result={result}
              synthesisLoading={synthesisLoading}
              synthesisResult={synthesisResult}
              synthesisError={synthesisError}
              onDismiss={onDismiss}
            />
          </div>
        )}
      </div>
    </div>
  );
};
