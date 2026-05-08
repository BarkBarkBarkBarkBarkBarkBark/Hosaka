<!--
  AUTO-GENERATED HEADER, MANUAL BODY (for now).
  Phase 10 of docs/increased_observability.yaml will replace the body
  with output from scripts/gen_agent_context.py. Until then, this file
  is the hand-written seed every future agent session reads first.
-->

# AGENT_CONTEXT

read this before you touch anything.

## the rule

there is **one** source of truth for what hosaka does:

- catalog: [docs/hosaka.features.yaml](hosaka.features.yaml) *(phase 02)*
- plan:    [docs/increased_observability.yaml](increased_observability.yaml)
- events:  `runtime/observability/events.db` (sqlite, 24h ring) *(phase 08)*

everything else — `openapi.json`, the user `manual/`, this file — is generated
from the catalog. do not edit them by hand. if a fact is wrong, fix the catalog.

## what to do first

1. read [docs/increased_observability.yaml](increased_observability.yaml) end-to-end. it's the spec.
2. `GET /api/v1/events/summary` — what's actually been running on this box.
3. `GET /api/v1/events/silent` — what claims to exist but hasn't emitted.
4. only then, write code.

## the observability protocol (one paragraph)

every function that matters wears `@trace(feature_id)`. every package
`__init__.py` wears `@heartbeat(module_id)`. both come from `hosaka.obs` and
both are guaranteed never to raise. emits land in a bounded in-process queue,
get batched into `events.db` by one supervised writer thread, and age out
after 24h. nothing in this pipeline is allowed to crash hosaka. if the sink
dies, decorators degrade to no-ops and `obs.sink_restarts_total` goes up.

## red flags ship themselves

a crash builds a redacted bundle (last 30 min of events + stack + manifest
slice) and POSTs it over tailscale to the triage relay, which opens a private
github issue and tags copilot. **end users never compose the prompt.** the
relay's template is the only path to the model. fixes flow back through the
canary stages in phase 11: one device → one ring → fleet, with
`/canary rollback` always one keystroke away.

## hard nos

- no new long-running processes. reuse the web process; everything else is a thread or a stdlib library.
- no ORM, no migration framework, no network calls in `hosaka.obs`.
- no editing `docs/openapi.json` or `docs/manual/**` by hand — CI will fail you.
- no removing features. mark `status: deprecated` and let the dead-code report find them.
- no telemetry that can throw. if your emit can raise, you wrote it wrong.

## commands worth knowing

```
/manual                # the user manual (generated)
/features list         # everything registered, with status
/what-can-i-do         # ranked baller commands from the event sink
/health  /doctor       # are we ok?
/events recent         # last N events on this box
/crash last  /crash ship
/canary status  /canary rollback
/safe-mode             # boot with plugins off
```

## file map (the parts that matter to an agent)

| you want to…                 | go here                                         |
| ---------------------------- | ----------------------------------------------- |
| understand the plan          | [docs/increased_observability.yaml](increased_observability.yaml) |
| add a feature                | [docs/hosaka.features.yaml](hosaka.features.yaml) + write the code + `@trace` it |
| add an HTTP route            | declare it as an entrypoint in the catalog; openapi regenerates |
| ship a crash to triage       | `scripts/build_crash_bundle.py` (phase 11)      |
| query "what just happened"   | `runtime/observability/events.db` or `/api/v1/events` |
| see what's silently dead     | `/api/v1/events/silent`                         |

if any of these paths don't exist yet, that's the next ticket. don't invent a
parallel system — extend the catalog.
