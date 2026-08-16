import React from 'react';
import { Microphone, TextT, User } from '@phosphor-icons/react';

interface ChatUserMessageProps {
  query?: string;
  timestamp?: string;
  source?: 'voice' | 'text' | 'sample';
}

export const ChatUserMessage: React.FC<ChatUserMessageProps> = ({
  query,
  timestamp,
  source = 'voice',
}) => {
  return (
    <div className="flex w-full justify-end select-none animate-fade-in my-3">
      <div className="group relative flex items-start gap-3 max-w-2xl rounded-2xl border border-blue-500/25 bg-blue-950/25 hover:bg-blue-950/35 p-3.5 sm:p-4 shadow-xl backdrop-blur-xl transition-all hover:border-cyan-400/40">
        {/* Content Body */}
        <div className="flex flex-col space-y-1.5 min-w-0 text-right items-end">
          {/* Question text */}
          {query && (
            <p className="text-sm sm:text-[15px] leading-relaxed text-white font-medium break-words whitespace-pre-wrap text-right">
              {query}
            </p>
          )}

          {/* Header row: Timestamp · Source */}
          <div className="flex items-center gap-2 text-[10px] text-slate-400">
            {timestamp && (
              <span className="text-[9px] text-slate-500">
                {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            )}

            {timestamp && <span>·</span>}

            {source === 'voice' ? (
              <span className="flex items-center gap-1 text-cyan-400 font-semibold">
                <Microphone size={12} weight="bold" />
                <span>Voice</span>
              </span>
            ) : (
              <span className="flex items-center gap-1 text-slate-300 font-semibold">
                <TextT size={12} weight="bold" />
                <span>Text</span>
              </span>
            )}
          </div>
        </div>

        {/* User Avatar Icon on Right */}
        <div className="pt-0.5 shrink-0">
          <div className="w-8 h-8 rounded-full bg-blue-600/30 border border-blue-400/30 flex items-center justify-center text-cyan-300 shadow-md">
            <User size={15} weight="bold" />
          </div>
        </div>
      </div>
    </div>
  );
};
