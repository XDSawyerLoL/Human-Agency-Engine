# Providence Analyst + Superposition Engine

Providence V15.1 adds a conversational layer without giving a language model authority over the predictive engine.

## Architecture

```text
User
  -> Providence Analyst (Qwen / OpenAI-compatible, optional)
     -> read-only snapshot + track record + causal context
     -> Superposition Engine
        -> Observer A: strong evidence
        -> Observer B: weak signals
        -> Observer C: adversarial / falsification
```

The canonical public probability always comes from Providence Forecast Engine. The LLM cannot write or recalculate it.

`relative_world_weight_percent` is **not** an event probability. It is a normalized relative support/attention weight across the selected active hypotheses.

The Superposition name is a multi-hypothesis metaphor. Providence does not claim quantum computation.

## Hostinger environment variables

The Analyst supports any OpenAI-compatible chat-completions endpoint, including a Qwen deployment served by vLLM/SGLang or a compatible provider.

```text
PROVIDENCE_QWEN_BASE_URL=https://your-provider.example/v1
PROVIDENCE_QWEN_API_KEY=server-side-secret
PROVIDENCE_QWEN_MODEL=your-qwen-model-id
PROVIDENCE_REDTEAM_MODEL=your-optional-red-team-model-id
PROVIDENCE_ANALYST_TIMEOUT_MS=25000
PROVIDENCE_ANALYST_MAX_TOKENS=900
```

Do not expose the API key in frontend JavaScript.

If no model endpoint is configured, `/api/analyst/chat` remains functional in `engine_only` mode and produces a deterministic grounded summary from Providence data.

## Red Team isolation

The Red Team model is advisory only:

- no tools;
- no wallets;
- no MHS/hardware adapter;
- no Intent Engine execution;
- no probability writes;
- no access to server secrets;
- only a sanitized read-only Providence context is supplied.

An uncensored or abliterated model, if used, should only be assigned this read-only adversarial role.

## API

- `GET /api/analyst/status`
- `GET /api/superposition?q=...&scenario_key=...&limit=4`
- `POST /api/analyst/chat`

Example:

```json
{
  "message": "Quelles trajectoires européennes sont les plus fragiles ?",
  "mode": "red_team",
  "history": []
}
```

## Separation from The Intent Engine

Providence answers **what may happen and why**.

The Intent Engine remains a separate execution/policy system. A future bridge may consume Providence forecasts before planning or irreversible physical actions, but the Providence Analyst itself never executes those actions.
