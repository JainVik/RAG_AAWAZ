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
      <div className="group relative flex items-start gap-3 max-w-2xl refractive-glass-card refractive-glass-card-primary p-3.5 sm:p-4 transition-all hover:border-blue-400/40">
        {/* Content Body */}
        <div className="flex flex-col space-y-1.5 min-w-0 text-right items-end">
          {/* Question text */}
          {query && (
            <p className="text-sm sm:text-[15px] leading-relaxed text-black dark:text-white font-medium break-words whitespace-pre-wrap text-right">
              {query}
            </p>
          )}

          {/* Header row: Timestamp · Source */}
          <div className="flex items-center gap-2 text-[10px] text-black dark:text-slate-400">
            {timestamp && (
              <span className="text-[9px] text-slate-600 dark:text-slate-500">
                {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            )}

            {timestamp && <span>·</span>}

            {source === 'voice' ? (
              <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400 font-semibold">
                <Microphone size={12} weight="bold" />
                <span>Voice</span>
              </span>
            ) : (
              <span className="flex items-center gap-1 text-black dark:text-slate-300 font-semibold">
                <TextT size={12} weight="bold" />
                <span>Text</span>
              </span>
            )}
          </div>
        </div>

        {/* User Avatar Icon on Right */}
        <div className="pt-0.5 shrink-0">
          <div className="w-8 h-8 rounded-full bg-blue-500/10 dark:bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-blue-600 dark:text-blue-300 shadow-md">
            <User size={15} weight="bold" />
          </div>
        </div>
      </div>
    </div>
  );
};
