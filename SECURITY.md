# Security policy

This is a research experiment, not a product. There are no releases and no supported versions; only `main` is maintained.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/robkeim/tech-debt-miner/security/advisories/new). Please don't open a public issue for a security problem.

## Secrets

The LLM key and GitHub token are read only from the environment (or a gitignored `.env`) and never reach CI. See [ADR 0002](docs/adr/0002-single-llm-client-choke-point.md). If you find a committed secret, report it as above.
