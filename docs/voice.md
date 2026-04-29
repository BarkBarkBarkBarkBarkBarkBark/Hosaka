# voice stack status — 2026-04-29

this document tracks what the hosaka voice surface is today, what was fixed in this pass, what is still inconsistent, and what future-self should do next.

## intent

hosaka should not just be a flashy voice demo.

the target behavior is:

1. operator speaks naturally.
2. speech becomes text reliably.
3. hosaka routes real work to the real local agent when machine context matters.
4. operator sees transcript + progress, not just vibes.
5. spoken output stays concise and separate from hidden machine reasoning.

there are now two lanes:

- **demo lane** — browser ↔ openai realtime. fast, smooth, good for public/shared deployments.
- **agent lane** — browser record → upload → whisper transcription → picoclaw work → concise reply. slower, but this is the lane that can actually inspect files, run commands, and operate on the local environment.

## what was wrong

### 1) frontend voice changes were not showing up

root cause: the appliance serves built static assets from `hosaka/web/ui`, not `frontend/src` directly. source edits were landing, but the served bundle was stale.

### 2) the voice pane was camera-dominant

the older built UI still favored the video surface. that made the transcript feel secondary, which is the wrong trust model for a coding/control assistant.

### 3) browser voice tool calls could fail even in local dev

docker bridge networking meant same-origin browser requests did not always look like loopback, so write-gated routes could reject the browser with auth errors.

### 4) `ask_agent` could quietly degrade into a non-agent answer

that made hosaka sound capable while not actually using the local execution path. for environment-aware voice interaction, that is misleading.

### 5) transcript usability was weak

the transcript could auto-snap too aggressively, making it hard to scroll back and inspect what happened.

### 6) local agent voice was too synchronous

the initial whisper → picoclaw turn path waited for the full result before the UI could meaningfully reflect progress. that works, but it does not feel like an assistant that heard the operator and then went to work.

## what is fixed now

### rebuild pipeline

- docker dev now runs a frontend watcher.
- `frontend/package.json` includes `build:watch`.
- `docker/dev.sh` and `docker/compose.yml` were patched so frontend edits rebuild into the served UI immediately.

### transcript-first voice panel

- transcript is now the primary surface.
- camera is parked by default and only expanded when needed.
- the orb/status card is compact and ambient instead of dominating the screen.
- transcript history keeps more items and no longer forcibly steals scroll position while the operator is reviewing older lines.

### clearer local-agent behavior

- voice instructions now push environment-aware tasks toward the real agent path.
- `ask_agent` no longer silently falls back when picoclaw is unavailable.
- same-origin local browser requests are trusted for voice write actions.

### backend-first local voice lane

- `POST /api/v1/voice/agent-turn` exists for one-shot whisper → picoclaw turns.
- local voice transcription uses the openai transcription api (`whisper-1` by default).
- picoclaw is prompted to return structured json with:
  - `spoken`
  - `thought`
  - `did_work`

### queued local voice jobs

this pass adds a better shape for the agent lane:

- `POST /api/v1/voice/agent-jobs`
  - accepts recorded audio
  - queues the turn
  - immediately returns a job id plus a short acknowledgement
- `GET /api/v1/voice/agent-jobs/{job_id}`
  - reports `queued`, `transcribing`, `thinking`, `completed`, or `error`
  - returns operator transcript, quiet status note, and final spoken reply when ready

the current frontend uses this queue so the operator gets an immediate “heard you / working on it” response while picoclaw continues in the background.

### public vs local separation

- public mode should stay on the safer demo lane.
- local builds can expose the stronger whisper → picoclaw lane.
- local-agent endpoints are now hard-disabled when `HOSAKA_PUBLIC_MODE=1`.

## current interaction model

### demo lane

- openai realtime over webrtc
- low-latency audio in/out
- useful for public showcase and lightweight conversational feel
- not the right place for trusted machine work

### agent lane

- press and hold the orb/button
- record one local turn
- release to send
- hosaka acknowledges quickly in the transcript
- whisper transcribes
- picoclaw works on the real machine state
- transcript shows quiet progress notes
- final reply lands with a short completion ding

this is not full duplex voice yet. it is a deliberate, operator-friendly push-to-talk control surface.

## important inconsistencies still present

### 1) no live tts handoff yet

the long-term plan mentioned livekit. that is not implemented. current local-agent mode is transcript-first with a completion chime, not synthesized spoken playback.

### 2) demo lane and agent lane are still separate implementations

conceptually they form a dual-lane system, but they are not yet unified under one orchestrator that decides:

- when to do a fast acknowledgement only
- when to keep talking in realtime
- when to spin off a long-running machine job

### 3) job state is in-memory only

the current queued job store is process-local and ephemeral.

- server restart loses jobs.
- there is no durable history.
- there is no multi-worker coordination.

that is acceptable for local appliance iteration, but not a final design.

### 4) progress is polling, not push

the frontend currently polls job status. this is simple and robust, but websocket or sse progress would be cleaner if voice jobs become more frequent.

### 5) transcript semantics still need tightening

we currently separate:

- `you`
- `hosaka`
- `status`
- `tool`

that is already better than before, but future iterations should more explicitly distinguish:

- operator speech
- acknowledgement/presence speech
- background work updates
- final answer
- tool traces meant only for debugging

### 6) backend policy is implicit in prompting

the structured json prompt helps, but the real policy boundary between “say something quickly” and “do real work quietly” should eventually live in explicit code, not just model instructions.

## recommendations

### near-term

1. **keep the dual-lane model**
	- demo lane for public / low-friction interaction
	- agent lane for local execution and trusted environment-aware work

2. **treat the fast acknowledgement as presence, not authority**
	- the immediate reply should confirm receipt and intent
	- the later completion should carry the authoritative outcome

3. **keep transcript first**
	- operators need auditability more than theatrics
	- camera should stay secondary

4. **continue using push-to-talk for the real agent lane**
	- simpler mental model
	- cheaper on constrained machines
	- easier to debug than full duplex barge-in logic

### medium-term

1. add push progress updates over websocket or sse.
2. add durable job history.
3. attach final-result speech synthesis to the local-agent lane.
4. introduce explicit routing rules for small-talk vs machine-work requests.
5. let long-running jobs surface follow-up cards, diffs, or artifacts in the transcript.

### long-term

1. unify both lanes behind a single voice orchestrator.
2. decide if livekit is still the right tts/output transport once the local-agent path is stable.
3. support interruption, cancellation, and resumable task summaries.
4. give the operator explicit controls for what can be spoken aloud vs shown only in text.

## concrete tasks for future self

- [ ] validate the latest press-to-hold + async job UI on device hardware.
- [ ] add a visible cancel action for a running local voice job.
- [ ] persist voice jobs beyond process memory.
- [ ] move job progress from polling to push.
- [ ] add optional final spoken playback for completed local-agent turns.
- [ ] add tests around `voice_api.py` job lifecycle and public-mode restrictions.
- [ ] tighten the transcript role model and operator-facing copy.
- [ ] audit whether the demo lane should expose fewer tools in public mode.

## implementation notes

the key files for this system are:

- [frontend/src/panels/VoicePanel.tsx](../frontend/src/panels/VoicePanel.tsx)
- [frontend/src/styles/app.css](../frontend/src/styles/app.css)
- [hosaka/web/voice_api.py](../hosaka/web/voice_api.py)
- [hosaka/voice/tools.py](../hosaka/voice/tools.py)
- [hosaka/llm/openai_adapter.py](../hosaka/llm/openai_adapter.py)
- [hosaka/identity.py](../hosaka/identity.py)

signal steady.

## future ideas

### orb silhouette — person-presence outline

when the camera is active, run a lightweight background-subtraction or
person-segmentation pass (e.g. mediapipe selfie segmentation, which runs
in-browser via wasm at ~15 fps on a pi 4) and project the person's crude
silhouette **onto the orb surface** — rendered as a soft, dimly-lit shape
inside the orb circle. the effect: the device literally "sees" the person
standing in front of it and reflects their outline back as part of its own
representational state. keep it abstract (4–8 px blur, ~15% opacity amber
fill) so it reads as presence rather than surveillance.

implementation sketch:
1. `<canvas>` overlay, same bounding box as `.voice-orb--full`.
2. every animation frame: draw the segmentation mask, clip to the orb
   circle, composite with `globalCompositeOperation = "lighter"`.
3. gate behind `VITE_ORB_SILHOUETTE=1` env var — off by default.
4. on pi 3b use a lower-res capture (160×120) and run every 3rd frame.
