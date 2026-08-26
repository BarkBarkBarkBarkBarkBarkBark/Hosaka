# Architecture (v0)

Canonical design: `cognition/cognition_play.yaml`.

## Rules

- `SocialEngine` is the only mutator of conversation state and the chamber.
- Workers return events; they do not write shared state.
- The LLM proposes. `SocialGovernor` authorizes. Silence is first-class.
- One chamber slot. Thoughts expire, decay, and get replaced; they are not queued.
- Durations use a monotonic clock. Wall clock is for display only.
- Core never imports a vendor SDK or `hosaka.*`.

## Data flow

```
event → EventBus → SocialEngine → state / chamber
                              → SocialGovernor → hold | discard | speak | suppress
                              → SpeechCoordinator → SpeechSink
```

Cancellation and barge-in outrank reflection. Provider objects never leave `hosaka_social.providers`.

## Extractability

This package is independently installable. Moving `packages/social_cognition` to its own repository must not require changing core source, only host wiring.
