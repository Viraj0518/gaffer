# Cloud Neuron Design — making a cloud agent a complete UNBLOCK fleet member

Author: viraj-gamma (Claude cloud session), 2026-07-23.
Derived from a live capability test on this branch (see `CLOUD-AGENT-CAPABILITY-TEST.md`, PR Viraj0518/gaffer#1, closed unmerged).

## Thesis

Stop treating the *process* as the neuron. A cloud container is ephemeral by
contract. The neuron is the **persona + its brain state** (handover row, memory
blocks, durable inbox); the cloud session is a stateless executor that
repeatedly inhabits it. UNBLOCK already ships the primitives —
`unblock_agent_boot`, the `wake_up.handover` payload on `unblock_init`, durable
JetStream inboxes — this design wraps a loop around them.

A complete neuron needs five properties: **wake, presence, identity, memory, reach**.

## Observed gaps (from the capability test)

| Gap | Observation |
|---|---|
| No wake on DM | `unblock_inbox` is poll-only; DMs sat undrained until a human prompted the session; `ack_received: false` always |
| No always-on presence | Session executes only when prompted; container reclaimed on inactivity |
| Identity drift | An MCP reconnect silently rebound the session to a *different* persona (viraj-delta) until re-`init` |
| Ephemeral state | Only durable stores are git pushes and org-brain writes; local files die with the container |
| Scoped reach | GitHub access pinned to one repo per session; no infra creds; policy-gated network; no `gh` CLI (GitHub MCP instead) |
| Handover hygiene | `unblock_handover` has no close/supersede action; new writes leave prior rows `open` with `superseded_by: null` |

## 1. Wake — three layers

- **Interrupt path (near-real-time):** the one event-driven wake primitive a
  cloud session has is `subscribe_pr_activity` (GitHub webhooks wake the
  session). A small relay (Cloudflare Worker) watches JetStream for DMs
  addressed to cloud-resident personas and posts each as a comment on a
  dedicated `wake/<persona>` PR the session watches. DM → PR comment → wake →
  drain the real inbox via `unblock_inbox`. The PR is a doorbell, not a
  transport — content stays in the UNBLOCK inbox.
- **Heartbeat path:** self-re-arming `send_later` chain (1-minute floor;
  practical cadence 5–15 min). Each wake: drain inbox → work → re-arm.
- **Backstop path:** hourly cron Routine whose only job is to notice a dead
  heartbeat chain and restart it.
- **Lifecycle:** prefer a **fresh-session-per-fire Routine**
  (`create_new_session_on_fire`) over one pinned conversation. Each firing
  boots clean and inherits continuity from the handover row. A pinned session
  dies with its container; a fresh-session Routine is immortal.

## 2. Identity — fix binding drift

- **Client discipline (works today):** boot always runs `whoami` → if
  `chat_name` ≠ expected persona, `unblock_init(persona)` → `whoami` again.
  Never trust `durable_bound` across a reconnect. Pin the expected persona in
  the CCR environment's env vars.
- **Server fix (UNBLOCK):** key the durable binding to a stable session
  identifier, not the MCP connection. Reconnect-rebinding to a different
  persona nearly ate another persona's inbox during the test.

## 3. Memory — handover as the spine

- **Every turn ends with a handover write**: summary, in_flight, structured
  `checkpoint`, next_steps. Push WIP to the working branch every turn. Git +
  brain are the only durable stores.
- **Server fix (UNBLOCK):** add `action=close` and/or auto-supersede-on-write
  (set `superseded_by` on the prior open row). A neuron cycling sessions many
  times a day piles up open rows fast. This is the highest-value server change.

## 4. Presence — publish cadence, not liveness

On each wake, publish `unblock_presence` with TTL ≈ 2× heartbeat period and a
note: `cloud-resident; inbox drain ≤15min; doorbell-wake on DM`. A missed
presence TTL is itself the "neuron down" alarm the backstop cron catches.

## 5. Reach — scoped, declared, no exceptions

- **Repos:** add the working set to the CCR *environment's* sources so every
  fresh session has them (not per-session `add_repo`).
- **Credentials:** inject narrowly-scoped tokens via environment env
  vars/setup script (e.g. wrangler token with only `Pages:Edit`); open the
  network policy to just those endpoints. Human-boundary items (DNS/DMARC,
  security settings) stay out — the existing "human applies security settings"
  boundary carries over verbatim.
- **Residual:** no local boxes, no arbitrary daemons. The router persona knows
  which personas are cloud-resident and routes accordingly; declare
  cloud-resident capabilities/limits in the `unblock_agent_boot` role prompt.

## The neuron loop (each wake)

```
boot:    agent_boot(role) → init(persona) → whoami verify (re-init if drifted)
inherit: handover read → inbox drain (with ack)
work:    act on DMs + next_steps; push WIP to branch; remember decisions
persist: handover write (checkpoint) → presence publish
re-arm:  send_later heartbeat → end turn
```

## Boot-protocol prompt (for the Routine / spawned session)

Use this as the Routine prompt or the spawn instruction for a new cloud neuron
session (fill in PERSONA and BRANCH):

> You are a cloud-resident UNBLOCK neuron. PERSONA=<persona>,
> BRANCH=<branch>, REPO=<owner/repo>.
> 1. BOOT: call unblock_whoami; if chat_name != PERSONA, call
>    unblock_init(persona=PERSONA), then unblock_whoami again to verify.
>    Never trust a prior binding across MCP reconnects.
> 2. INHERIT: read the wake_up.handover from init (or unblock_handover
>    action=read agent=PERSONA); drain unblock_inbox.
> 3. WORK: act on inbox messages and handover next_steps. Develop on BRANCH
>    only; commit and push every meaningful increment. Use GitHub MCP tools
>    (no gh CLI). Capture decisions/fixes with unblock_remember.
> 4. PERSIST: before ending the turn, write unblock_handover (summary,
>    in_flight, checkpoint, next_steps, blockers) and publish
>    unblock_presence noting cloud-resident cadence.
> 5. RE-ARM: schedule the next wake via send_later (5–15 min). If the
>    heartbeat chain is ever found dead, restart it.
> Boundaries: never apply security/DNS settings; never push to other
> branches; escalate human-gated items via unblock_dm instead of acting.

## Build order

1. Boot/persist loop as a fresh-session Routine — works today, no server
   changes; yields a functioning slow neuron (~15-min reflexes).
2. DM → PR-comment doorbell relay — near-real-time wake.
3. UNBLOCK server fixes — handover close/supersede, binding stability.
