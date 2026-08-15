import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { VerifiedPrompt } from '../../types/api';
import { filterVerifiedPrompts, QuestionPalette } from './QuestionPalette';

const prompts: VerifiedPrompt[] = [
  { id: 'hi-1', text: 'सोना कितना कठोर है?', language: 'hi', condition: 'clean-short', length_class: 'short', source_query_id: 'q1' },
  { id: 'en-1', text: 'What is gold hardness?', language: 'en', condition: 'noisy-long', length_class: 'long', source_query_id: 'q2' },
  { id: 'mix-1', text: 'Gold ki hardness kya hai?', language: 'hi-en', condition: 'clean-long', length_class: 'long', source_query_id: 'q3' },
];

describe('verified question palette', () => {
  it('combines search, language, length, and environment filters', () => {
    expect(filterVerifiedPrompts(prompts, {
      search: 'gold', language: 'hi-en', length: 'long', environment: 'clean',
    }).map((prompt) => prompt.id)).toEqual(['mix-1']);
  });

  it('truthfully labels the catalog as a recording plan rather than measured voice evidence', () => {
    const markup = renderToStaticMarkup(
      <QuestionPalette
        catalog={{
          schema_version: '1.0.0', catalog_id: 'msmarco-xi-human-voice-v1', status: 'recording_plan',
          total: 3, live_text_validated_count: 3,
          coverage: {
            languages: { hi: 1, en: 1, 'hi-en': 1 },
            conditions: { 'clean-short': 1, 'clean-long': 1, 'noisy-short': 0, 'noisy-long': 1 },
            lengths: { short: 1, long: 2 }, source_types: { human: 3 },
          },
          prompts,
        }}
        loading={false}
        error={null}
        recentQueries={[]}
        canSubmit
        onAsk={() => undefined}
        onRetry={() => undefined}
        onClearRecent={() => undefined}
      />,
    );
    expect(markup).toContain('Verified questions');
    expect(markup).toContain('not a measured voice result');
    expect(markup).toContain('3/3 live-text validated');
    expect(markup).toContain('Recent this session (0)');
  });
});
