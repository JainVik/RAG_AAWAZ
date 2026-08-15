import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { VerifiedPromptCatalog } from '../../types/api';
import { VerifiedPromptCoverageCard } from './VerifiedPromptCoverageCard';

const catalog: VerifiedPromptCatalog = {
  schema_version: '1.0.0',
  catalog_id: 'msmarco-xi-human-voice-v1',
  status: 'recording_plan',
  total: 60,
  live_text_validated_count: 60,
  coverage: {
    languages: { hi: 20, en: 20, 'hi-en': 20 },
    conditions: {
      'clean-short': 15,
      'clean-long': 15,
      'noisy-short': 15,
      'noisy-long': 15,
    },
    lengths: { short: 30, long: 30 },
    source_types: { human: 60 },
  },
  prompts: [],
};

describe('VerifiedPromptCoverageCard', () => {
  it('presents the balanced prompt plan without calling it measured voice evidence', () => {
    const markup = renderToStaticMarkup(
      <VerifiedPromptCoverageCard catalog={catalog} error={null} />,
    );

    expect(markup).toContain('Verified voice-question palette');
    expect(markup).toContain('Recording plan · not a benchmark');
    expect(markup).toContain('Hindi');
    expect(markup).toContain('English');
    expect(markup).toContain('Hindi + English');
    expect(markup).toContain('Audio recording and voice-latency qualification are still measured separately');
  });

  it('shows a bounded unavailable state when the catalog cannot be loaded', () => {
    const markup = renderToStaticMarkup(
      <VerifiedPromptCoverageCard catalog={null} error="Catalog unavailable." />,
    );

    expect(markup).toContain('Catalog unavailable.');
    expect(markup).not.toContain('Text-validated');
  });
});
