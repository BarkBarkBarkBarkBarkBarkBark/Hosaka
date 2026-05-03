// Browser-side OpenAI Realtime client over WebRTC.
//
// We ask Hosaka's backend for an ephemeral session token, open an
// RTCPeerConnection with one outbound audio track (the mic) and one
// inbound audio track (the assistant), plus a data channel that carries
// Realtime events. Tool calls that come over the data channel are
// forwarded to /api/v1/voice/tools/{name} so the browser and the
// Python daemon share exactly one dispatcher.
//
// This file is deliberately tiny and framework-free — the VoicePanel
// does all the React plumbing.

export type VoiceState = "idle" | "listening" | "thinking" | "speaking" | "error";

export type VoiceEvents = {
  onState?: (state: VoiceState) => void;
  onUserTranscript?: (text: string) => void;
  onAssistantTranscript?: (delta: string) => void;
  onAssistantTranscriptDone?: (text: string) => void;
  onTool?: (name: string, args: Record<string, unknown>, result: string) => void;
  onError?: (err: unknown) => void;
};

type EphemeralToken = {
  client_secret: { value: string; expires_at?: number };
  session: Record<string, unknown>;
  tools: Array<Record<string, unknown>>;
  instructions: string;
  voice: string;
  model: string;
  api_shape?: "ga" | "beta" | string;
  sdp_url?: string;
};

const REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls";

export class VoiceSession {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private micStream: MediaStream | null = null;
  private audioEl: HTMLAudioElement | null = null;
  private assistantBuf = "";
  private handledCallIds = new Set<string>();

  constructor(private readonly events: VoiceEvents = {}) {}

  // ── public API ───────────────────────────────────────────────────

  async start(audioSink: HTMLAudioElement): Promise<void> {
    this.audioEl = audioSink;
    this.setState("thinking");

    const token = await fetchEphemeralToken();

    const pc = new RTCPeerConnection();
    this.pc = pc;

    pc.ontrack = (evt) => {
      if (this.audioEl) {
        this.audioEl.srcObject = evt.streams[0];
        void this.audioEl.play().catch(() => {/* user-gesture fallback */});
      }
    };

    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    for (const track of this.micStream.getTracks()) {
      pc.addTrack(track, this.micStream);
    }

    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.onmessage = (e) => this.handleServerEvent(e.data);
    dc.onopen = () => this.configureSession(token);
    dc.onerror = (e) => this.events.onError?.(e);

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpUrl = token.sdp_url || REALTIME_CALLS_URL;
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token.client_secret.value}`,
      "Content-Type": "application/sdp",
    };
    if (token.api_shape === "beta" || !sdpUrl.includes("/realtime/calls")) {
      headers["OpenAI-Beta"] = "realtime=v1";
    }
    const answerResp = await fetch(sdpUrl, {
      method: "POST",
      headers,
      body: offer.sdp ?? "",
    });
    if (!answerResp.ok) {
      throw new Error(`realtime SDP exchange failed: ${answerResp.status}`);
    }
    const answer: RTCSessionDescriptionInit = {
      type: "answer",
      sdp: await answerResp.text(),
    };
    await pc.setRemoteDescription(answer);
    this.setState("listening");
  }

  async stop(): Promise<void> {
    this.setState("idle");
    try {
      this.dc?.close();
    } catch {/* noop */}
    this.dc = null;
    try {
      this.pc?.close();
    } catch {/* noop */}
    this.pc = null;
    if (this.micStream) {
      for (const track of this.micStream.getTracks()) track.stop();
      this.micStream = null;
    }
    if (this.audioEl) {
      this.audioEl.srcObject = null;
    }
  }

  muteMic(mute: boolean): void {
    this.micStream?.getAudioTracks().forEach((t) => (t.enabled = !mute));
  }

  isOpen(): boolean {
    return this.dc?.readyState === "open";
  }

  sendUserText(text: string): void {
    if (!this.dc || this.dc.readyState !== "open") return;
    const msg = {
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    };
    this.dc.send(JSON.stringify(msg));
    this.dc.send(JSON.stringify({ type: "response.create" }));
  }

  // ── internals ────────────────────────────────────────────────────

  private setState(state: VoiceState): void {
    this.events.onState?.(state);
  }

  private configureSession(token: EphemeralToken): void {
    if (!this.dc) return;
    // Echo the tool schema + instructions we already injected when we
    // minted the ephemeral token. Doing it again via session.update
    // guarantees the settings apply once the data channel is live even
    // if the token creation path ever drops them upstream.
    const session = token.api_shape === "beta" ? {
      type: "session.update",
      session: {
        modalities: ["audio"],
        voice: token.voice,
        instructions: token.instructions,
        input_audio_format: "pcm16",
        output_audio_format: "pcm16",
        input_audio_transcription: { model: "gpt-4o-mini-transcribe" },
        turn_detection: {
          type: "server_vad",
          threshold: 0.5,
          prefix_padding_ms: 300,
          silence_duration_ms: 600,
        },
        tools: token.tools,
        tool_choice: "auto",
      },
    } : {
      type: "session.update",
      session: {
        type: "realtime",
        model: token.model,
        output_modalities: ["audio"],
        instructions: token.instructions,
        audio: {
          input: {
            transcription: { model: "gpt-4o-mini-transcribe" },
            turn_detection: {
              type: "server_vad",
              threshold: 0.5,
              prefix_padding_ms: 300,
              silence_duration_ms: 600,
            },
          },
          output: {
            voice: token.voice,
          },
        },
        tools: token.tools,
        tool_choice: "auto",
      },
    };
    this.dc.send(JSON.stringify(session));
  }

  private handleServerEvent(raw: unknown): void {
    if (typeof raw !== "string") return;
    let evt: Record<string, unknown>;
    try {
      evt = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    const type = String(evt.type ?? "");
    switch (type) {
      case "input_audio_buffer.speech_started":
        this.setState("listening");
        break;
      case "input_audio_buffer.speech_stopped":
        this.setState("thinking");
        break;
      case "response.audio.delta":
      case "response.output_audio.delta":
        this.setState("speaking");
        break;
      case "response.audio.done":
      case "response.output_audio.done":
        this.setState("listening");
        break;
      case "response.audio_transcript.delta": {
        const delta = String(evt.delta ?? "");
        this.assistantBuf += delta;
        this.events.onAssistantTranscript?.(delta);
        break;
      }
      case "response.output_audio_transcript.delta": {
        const delta = String(evt.delta ?? "");
        this.assistantBuf += delta;
        this.events.onAssistantTranscript?.(delta);
        break;
      }
      case "response.audio_transcript.done":
      case "response.output_audio_transcript.done":
        if (this.assistantBuf.trim()) {
          this.events.onAssistantTranscriptDone?.(this.assistantBuf);
        }
        this.assistantBuf = "";
        break;
      case "conversation.item.input_audio_transcription.completed": {
        const text = String(evt.transcript ?? "");
        if (text.trim()) this.events.onUserTranscript?.(text);
        break;
      }
      case "response.function_call_arguments.done":
        void this.handleFunctionCall(evt);
        break;
      case "response.done":
        void this.handleResponseDone(evt);
        this.setState("listening");
        break;
      case "error":
        this.events.onError?.(evt.error ?? evt);
        this.setState("error");
        break;
    }
  }

  private async handleFunctionCall(evt: Record<string, unknown>): Promise<void> {
    const callId = String(evt.call_id ?? "");
    if (callId && this.handledCallIds.has(callId)) return;
    if (callId) this.handledCallIds.add(callId);
    const name = String(evt.name ?? "");
    let args: Record<string, unknown> = {};
    const raw = evt.arguments;
    if (typeof raw === "string") {
      try {
        args = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        args = {};
      }
    } else if (raw && typeof raw === "object") {
      args = raw as Record<string, unknown>;
    }
    let output = `tool ${name}: dispatch failed`;
    try {
      const resp = await fetch(`/api/v1/voice/tools/${encodeURIComponent(name)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args }),
      });
      if (resp.ok) {
        const data = (await resp.json()) as { output?: string };
        output = data.output ?? output;
      } else {
        output = `tool ${name}: http ${resp.status}`;
      }
    } catch (exc) {
      output = `tool ${name}: ${String(exc)}`;
    }
    this.events.onTool?.(name, args, output);
    if (!this.dc || this.dc.readyState !== "open") return;
    this.dc.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: {
          type: "function_call_output",
          call_id: callId,
          output,
        },
      }),
    );
    this.dc.send(JSON.stringify({ type: "response.create" }));
  }

  private async handleResponseDone(evt: Record<string, unknown>): Promise<void> {
    const response = evt.response;
    if (!response || typeof response !== "object") return;
    const output = (response as { output?: unknown }).output;
    if (!Array.isArray(output)) return;
    for (const item of output) {
      if (!item || typeof item !== "object") continue;
      const call = item as Record<string, unknown>;
      if (call.type !== "function_call") continue;
      await this.handleFunctionCall({
        call_id: call.call_id,
        name: call.name,
        arguments: call.arguments,
      });
    }
  }
}

async function fetchEphemeralToken(): Promise<EphemeralToken> {
  const resp = await fetch("/api/v1/voice/ephemeral-token", { method: "POST" });
  if (!resp.ok) {
    let detail = "";
    try {
      const data = (await resp.json()) as { detail?: string };
      detail = typeof data.detail === "string" ? data.detail : "";
    } catch {
      try {
        detail = await resp.text();
      } catch {
        detail = "";
      }
    }
    if (resp.status === 405) {
      detail = detail.trim() || "backend may be out of date — run: hosaka update && hosaka build";
    }
    const suffix = detail.trim() ? `: ${detail.trim()}` : "";
    throw new Error(`ephemeral-token ${resp.status}${suffix}`);
  }
  return (await resp.json()) as EphemeralToken;
}
