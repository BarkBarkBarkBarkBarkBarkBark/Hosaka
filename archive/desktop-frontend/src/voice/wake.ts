// Browser-side voice activity detection.
//
// We keep this intentionally small: inside the kiosk the operator is
// right next to the device, so a real wake-word ("hey hosaka") is
// overkill. A mic-level VAD ("start listening when the user speaks")
// gives the ChatGPT-voice-mode feel without a model download.
//
// For users who *do* want a wake word in-browser: swap MicVAD for an
// openwakeword-js / porcupine-web instance with the same start/stop
// shape. The headless Python daemon is where the real wake-word lives.

import { MicVAD } from "@ricky0123/vad-web";

export type WakeEvents = {
  onSpeechStart?: () => void;
  onSpeechEnd?: () => void;
  onError?: (err: unknown) => void;
};

export class BrowserWake {
  private vad: MicVAD | null = null;

  constructor(private readonly events: WakeEvents = {}) {}

  async start(): Promise<void> {
    try {
      this.vad = await MicVAD.new({
        onSpeechStart: () => this.events.onSpeechStart?.(),
        onSpeechEnd: () => this.events.onSpeechEnd?.(),
        // Sensible defaults; surface more props only if the UI grows a knob.
        positiveSpeechThreshold: 0.6,
        negativeSpeechThreshold: 0.4,
      });
      this.vad.start();
    } catch (exc) {
      this.events.onError?.(exc);
      throw exc;
    }
  }

  pause(): void {
    try {
      this.vad?.pause();
    } catch {
      /* noop */
    }
  }

  resume(): void {
    try {
      this.vad?.start();
    } catch {
      /* noop */
    }
  }

  async stop(): Promise<void> {
    try {
      this.vad?.pause();
      this.vad?.destroy?.();
    } catch {
      /* noop */
    }
    this.vad = null;
  }
}
