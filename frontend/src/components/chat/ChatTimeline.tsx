import React, { useEffect, useRef } from 'react';
import { ArrowCounterClockwise, Sparkle } from '@phosphor-icons/react';
import type { ChatTurn } from '../../utils/chatSessionHistory';
import type { ServerLanguageCode, VoiceState } from '../../types/api';
import { ChatUserMessage } from './ChatUserMessage';
import { ChatAssistantMessage } from './ChatAssistantMessage';

interface ChatTimelineProps {
  turns: ChatTurn[];
  liveQuery?: string;
  liveLanguage?: ServerLanguageCode;
  liveState?: VoiceState;
  isLive?: boolean;
  audioLevel?: number;
  onClearSession?: () => void;
  onSelectPrompt?: (query: string, language: ServerLanguageCode) => void;
}

export const ChatTimeline: React.FC<ChatTimelineProps> = ({
  turns,
  liveQuery = '',
  liveLanguage = 'en',
  liveState = 'idle',
  isLive = false,
  audioLevel = 0,
  onClearSession,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll smoothly to bottom on new turns, live updates, or completion
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns, isLive, liveQuery, liveState]);

  return (
    <div
      ref={containerRef}
      className="flex flex-col w-full max-w-6xl mx-auto px-2 sm:px-4 py-2 space-y-6 pb-36 min-h-[calc(100dvh-180px)]"
    >
      {/* Top Sticky Header of the Chat Timeline */}
      <div className="sticky top-16 z-30 flex items-center justify-between border border-white/10 bg-[#070b14]/85 backdrop-blur-2xl px-4 py-2.5 rounded-2xl shadow-xl -mx-1 sm:mx-0 mb-4 transition-all">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <Sparkle size={15} className="text-cyan-400" />
          <span>Active Conversation</span>
          <span className="rounded-full bg-white/5 border border-white/10 px-2 py-0.5 text-[10px] text-slate-400">
            {turns.length} {turns.length === 1 ? 'turn' : 'turns'} (Cached in browser)
          </span>
        </div>

        {onClearSession && (
          <button
            type="button"
            onClick={onClearSession}
            className="flex items-center gap-1.5 px-3.5 py-1 rounded-full text-xs font-semibold text-slate-300 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 shadow-sm transition-all cursor-pointer active:scale-95 hover:border-cyan-400/40"
            title="Start new conversation"
          >
            <ArrowCounterClockwise size={13} className="text-cyan-400" />
            <span>New Conversation</span>
          </button>
        )}
      </div>

      {/* Historical Message Stream */}
      <div className="flex flex-col space-y-8">
        {turns.map((turn) => (
          <div key={turn.id} className="flex flex-col space-y-4">
            {/* User Question (Right-Aligned) */}
            <ChatUserMessage
              query={turn.query}
              language={turn.language}
              timestamp={turn.timestamp}
              source={turn.source}
            />

            {/* Assistant Response (Left-Aligned with Mini Orb on Top-Left) */}
            <ChatAssistantMessage
              result={turn.result}
              synthesisLoading={turn.synthesisLoading}
              synthesisResult={turn.synthesisResult}
              synthesisError={turn.synthesisError}
            />
          </div>
        ))}

        {/* Active In-Flight Query State */}
        {isLive && (
          <div className="flex flex-col space-y-4">
            {liveQuery ? (
              <ChatUserMessage
                query={liveQuery}
                language={liveLanguage}
                source="voice"
              />
            ) : null}

            <ChatAssistantMessage
              isLive={true}
              liveState={liveState}
              audioLevel={audioLevel}
              liveTranscript={liveQuery}
            />
          </div>
        )}
      </div>

      {/* Anchor for auto-scrolling */}
      <div ref={bottomRef} className="h-4" />
    </div>
  );
};
