import micOnSfx from '../assets/sfx/mic-on.mp3';
import micOffSfx from '../assets/sfx/mic-off.mp3';
import lightSwitchOnSfx from '../assets/sfx/light-switch-on.mp3';
import lightSwitchOffSfx from '../assets/sfx/light-switch-off.mp3';

// Cache preloaded audio objects for instant playback
let micOnAudio: HTMLAudioElement | null = null;
let micOffAudio: HTMLAudioElement | null = null;
let lightSwitchOnAudio: HTMLAudioElement | null = null;
let lightSwitchOffAudio: HTMLAudioElement | null = null;

function getAudio(source: string, volume = 0.45): HTMLAudioElement | null {
  if (typeof window === 'undefined') return null;
  try {
    const audio = new Audio(source);
    audio.volume = volume;
    audio.preload = 'auto';
    return audio;
  } catch {
    return null;
  }
}

/**
 * Play sound effect asynchronously with zero impact on main thread / latency
 */
function playSfx(audioInstance: HTMLAudioElement | null, source: string, volume = 0.45) {
  if (typeof window === 'undefined') return;

  try {
    const audio = audioInstance || getAudio(source, volume);
    if (!audio) return;

    audio.currentTime = 0;
    audio.volume = volume;
    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch(() => {
        // Fail silently if browser autoplay policy blocks audio
      });
    }
  } catch {
    // Fail silently
  }
}

/**
 * Play microphone on sound effect
 */
export function playMicOnSound() {
  if (!micOnAudio) micOnAudio = getAudio(micOnSfx, 0.45);
  playSfx(micOnAudio, micOnSfx, 0.45);
}

/**
 * Play microphone off / completed sound effect
 */
export function playMicOffSound() {
  if (!micOffAudio) micOffAudio = getAudio(micOffSfx, 0.45);
  playSfx(micOffAudio, micOffSfx, 0.45);
}

/**
 * Play theme switch sound effect
 * @param toDark - true if switching to Dark Mode, false if switching to Light Mode
 */
export function playThemeSound(toDark: boolean) {
  if (toDark) {
    if (!lightSwitchOffAudio) lightSwitchOffAudio = getAudio(lightSwitchOffSfx, 0.5);
    playSfx(lightSwitchOffAudio, lightSwitchOffSfx, 0.5);
  } else {
    if (!lightSwitchOnAudio) lightSwitchOnAudio = getAudio(lightSwitchOnSfx, 0.5);
    playSfx(lightSwitchOnAudio, lightSwitchOnSfx, 0.5);
  }
}
