import React, { useEffect, useRef } from 'react';
import type { ChatTurn } from '../../utils/chatSessionHistory';
import type { VoiceState } from '../../types/api';
import { ChatUserMessage } from './ChatUserMessage';
import { ChatAssistantMessage } from './ChatAssistantMessage';

interface ChatTimelineProps {
  turns: ChatTurn[];
  liveQuery?: string;
  liveState?: VoiceState;
  isLive?: boolean;
  audioLevel?: number;
}

export const ChatTimeline: React.FC<ChatTimelineProps> = ({
  turns,
  liveQuery = '',
  liveState = 'idle',
  isLive = false,
  audioLevel = 0,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll smoothly to bottom on new turns, live updates, or completion
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns, isLive, liveQuery, liveState]);

  return (
    <div className="flex flex-col w-full max-w-6xl mx-auto px-2 sm:px-4 py-2 space-y-6">
      {/* Historical Message Stream */}
      <div className="flex flex-col space-y-8">
        {turns.map((turn) => (
          <div key={turn.id} className="flex flex-col space-y-4">
            {/* User Question (Right-Aligned) */}
            <ChatUserMessage
              query={turn.query}
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
