# AI and network routing

JarvisAi Unity keeps the user-facing AI control small:

- `Авто`
- `Быстро`
- `Качество`

The UI should not show a long provider/model list by default. The backend maps those modes to
provider plans and falls back when a provider hits rate limits, timeouts, or temporary server errors.
The current build does not expose a user-facing local AI mode.

## Provider plan

| Mode | Order |
| --- | --- |
| `auto` | Groq, Cerebras, Gemini, OpenRouter |
| `fast` | Groq, Cerebras |
| `quality` | Gemini, Groq, Cerebras, OpenRouter |

OpenRouter is a last-resort aggregator because free model availability and limits are dynamic.

## Keys

Cloud keys are read from protected registration settings first, then environment variables:

- `GROQ_API_KEY`
- `CEREBRAS_API_KEY`
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`

Windows builds must keep these values protected through DPAPI in `SettingsStore`. They must not be
written as plaintext to the settings JSON.

## Proxy and VPN

Default network mode is `system`, which lets `httpx` respect environment proxy variables such as
`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY`.

Advanced settings may switch to:

- `manual`: use a configured proxy URL and do not trust environment proxy values.
- `off`: disable environment proxy discovery.

Keep `NO_PROXY` defaults for local endpoints:

```text
localhost,127.0.0.1,::1
```

Local AI services such as Ollama should not be routed through cloud/VPN proxy paths.

## Source checks

The provider routing was checked against official documentation:

- Groq OpenAI compatibility and rate-limit documentation.
- Cerebras Inference OpenAI compatibility/model documentation.
- Google Gemini OpenAI-compatible endpoint and rate-limit documentation.
- OpenRouter API and free-model FAQ documentation.
- HTTPX environment variable proxy behavior.
