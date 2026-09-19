# Model routing

Company Core talks to AI models through the OpenAI Chat Completions protocol. All agents use the
same base URL and API key, while role variables select the model used for each workload. For
step-by-step key acquisition and verification, see [API keys](keys.md).

## OmniRoute

OmniRoute is the recommended setup when you want multiple providers, route aliases, and fallback
behind one local endpoint. It needs Node 22.22.2+.

Full `.env` values and verify commands are canonical in [API keys](keys.md#ai-gateway-tier-1-required-for-ai-actions).
Summary:

```dotenv
OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1
OMNIROUTE_API_KEY=<endpoint-key-from-OmniRoute-dashboardEndpoints>
MODEL_FAST=auto/best-fast
```

Start OmniRoute before Company Core. If they run in separate Docker containers, `127.0.0.1` points
to the current container; use a shared Compose service name instead.

## Ollama and Llama

Ollama is the simplest fully local option. Set every `MODEL_*` to a real `ollama list` name;
`auto/*` aliases do not exist in Ollama. Full values in [API keys](keys.md#option-b-ollama-fully-local).

The `ollama` API key is a non-secret placeholder required by OpenAI-compatible clients. Choose a
vision-capable installed model for `MODEL_VISION` if you use image analysis. Small local models may
produce campaign packages that fail strict quality gates; review and regenerate those outputs.

## Other OpenAI-compatible endpoints

For LiteLLM or a hosted provider, use its `/v1` base URL, API key, and exact model identifiers.
Full values in [API keys](keys.md#option-c-litellm--hosted-openai-compatible-api).

Never expose the model API key in frontend code or commit it to Git. Run `make doctor` after editing
`.env`, then use the provider's models endpoint or a minimal chat-completions request to verify the
connection before launching long media workflows.
