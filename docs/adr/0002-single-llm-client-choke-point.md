# All LLM calls go through one client

One client module is the only code that imports the provider SDK. It enforces the per-run USD cap (required, low default, raised only via `--max-usd`), the Response cache, Dry-run (an injected client that raises on send, not scattered flags), secret redaction and per-call logging. A test fails if the SDK is imported elsewhere. New experiments default to Dry-run until `--run` is passed. The LLM key is only ever read from the environment (optionally a gitignored `.env`) and never reaches CI, which uses recorded responses.
