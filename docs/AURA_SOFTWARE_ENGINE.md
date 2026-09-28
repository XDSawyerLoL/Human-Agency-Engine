# AURA Software Engine v1

AURA Software Engine is a guarded software-engineering capability backed by an
OpenHands Agent Server configured with `conversation_runtime=docker`. It exists
to let AURA inspect, modify and test code in a containerized runtime plus a
dedicated git worktree, without giving the reasoning layer direct production
write access.

## Boundary

The engine is deliberately **not** a deployment system.

It may:

- open an OpenHands conversation against an allow-listed repository workspace;
- create a dedicated git worktree for the conversation;
- edit files and run repository checks inside that workspace;
- retry after failed checks;
- expose the agent final response to AURA;
- interrupt a runaway or stuck conversation.

It may not:

- push to a remote repository;
- merge a pull request;
- deploy or publish;
- write directly to main/master;
- rotate or expose secrets;
- bypass the Human Agency Engine authorization stack.

Promotion remains:

`branch -> tests -> review/canary -> promote`

## Existing controls reused

Software Engine does not create a second authorization architecture. A mission
must reference an existing AURA adapter preflight for:

- adapter: `aura-software-engine`
- version: `1.0.0`
- audience: `aura-software-sandbox`
- action type: `software_patch`

The preflight itself is downstream of the existing policy receipt, delegation,
human commit and dual-key dry-run. Production configuration additionally
requires an effective signed sandbox attestation.

## Privacy

The raw mission goal is sent to the configured OpenHands Agent Server but is not
stored in the Human Agency Engine database. The database stores only a SHA-256
goal digest, repository, quality commands, execution status and OpenHands
conversation identifier.

The final agent response is returned to the caller during refresh but is also
not stored; only its digest is retained.

## Configuration

The capability is disabled by default.

```env
SOFTWARE_AGENT_ENABLED=false
SOFTWARE_AGENT_BASE_URL=http://127.0.0.1:3000
SOFTWARE_AGENT_SESSION_API_KEY=
SOFTWARE_AGENT_AGENT_PROFILE_ID=
SOFTWARE_AGENT_WORKSPACE_ROOT=/workspace/repos
SOFTWARE_AGENT_ALLOWED_REPOSITORIES=XDSawyerLoL/Human-Agency-Engine
SOFTWARE_AGENT_MAX_ITERATIONS=80
SOFTWARE_AGENT_TIMEOUT_SECONDS=20
SOFTWARE_AGENT_REQUIRE_ATTESTATION=true
```

In production, use an authenticated Agent Server with
`conversation_runtime=docker` and keep `SOFTWARE_AGENT_REQUIRE_ATTESTATION=true`.
A local OpenHands runtime is rejected even if the service is reachable. A
loopback HTTP URL is accepted for the outer Docker-runtime controller on the
same host; a non-loopback production URL must use HTTPS.

The outer OpenHands Docker-runtime controller must already have each allow-listed
repository available under:

`<SOFTWARE_AGENT_WORKSPACE_ROOT>/<owner>/<repository>`

The server-side Agent Profile referenced by
`SOFTWARE_AGENT_AGENT_PROFILE_ID` owns model configuration. That keeps model
credentials out of Human Agency Engine requests and allows the profile to point
at a local/free model endpoint when appropriate.

## API

All routes inherit the existing Human Agency Engine API-key protection.

- `GET /v1/execution/software-agent/capabilities`
- `POST /v1/execution/software-agent/bootstrap`
- `POST /v1/execution/software-agent/runs`
- `GET /v1/execution/software-agent/runs/{run_id}`
- `POST /v1/execution/software-agent/runs/{run_id}/refresh`
- `POST /v1/execution/software-agent/runs/{run_id}/interrupt`

Bootstrap requires the exact confirmation:

`REGISTER AURA SOFTWARE ENGINE`

## Quality loop

A mission can provide explicit quality commands. If none are supplied, the agent
is instructed to discover and run the repository's native compile/lint/test
checks, start narrow, then expand when practical. AURA should treat a final
response as evidence about the sandbox run, not as permission to promote it.
