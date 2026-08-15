import { describe, expect, it } from 'vitest';
import {
  createSilenceDetectionState,
  markRecognizedSpeech,
  observeVolumeForAutoStop,
} from './audio';

describe('voice silence auto-stop', () => {
  it('does not submit a request when the user has not spoken', () => {
    const observation = observeVolumeForAutoStop(
      createSilenceDetectionState(0),
      0,
      10_000
    );
    expect(observation.state.speechDetected).toBe(false);
    expect(observation.shouldStop).toBe(false);
  });

  it('stops after confirmed speech followed by 1.5 seconds of silence', () => {
    let state = createSilenceDetectionState(0);
    state = observeVolumeForAutoStop(state, 0.1, 100).state;
    state = observeVolumeForAutoStop(state, 0.1, 200).state;
    expect(state.speechDetected).toBe(true);
    expect(observeVolumeForAutoStop(state, 0, 1_699).shouldStop).toBe(false);
    expect(observeVolumeForAutoStop(state, 0, 1_700).shouldStop).toBe(true);
  });

  it('uses recognized partial speech and resets the silence clock when speech resumes', () => {
    let state = markRecognizedSpeech(createSilenceDetectionState(0), 200);
    state = observeVolumeForAutoStop(state, 0, 1_300).state;
    state = observeVolumeForAutoStop(state, 0.1, 1_400).state;
    expect(observeVolumeForAutoStop(state, 0, 2_899).shouldStop).toBe(false);
    expect(observeVolumeForAutoStop(state, 0, 2_900).shouldStop).toBe(true);
  });
});
