# Agent Notes

- Modify only active sources; anything under `legacy/` is historical context and should stay untouched unless the user explicitly says otherwise.
- The running bot lives in `bot.py`. Review that file before making behavioral changes.
- Dependencies were trimmed to match actual imports. Current requirements are
  - `nio-bot[cli,e2ee]==1.3.0a2` (latest release on PyPI as of 2025-08-15; pip install needs the `--pre` flag)
  - `requests~=2.32.5`
  Re-check versions when updating; avoid reintroducing unused packages.
- Environment variables documented in `env.example` configure homeserver access, invitation flow, and SMTP. Keep them consistent when adding new settings.
- If you need to add new Matrix or cryptography features, confirm whether additional libs (e.g., `python-olm`) are required before modifying `requirements.txt`.
- Repository currently tracks user-made deletions (`gpt.py`, `newbot.py`, `perplexity_ai_llm.py`). Do not restore or purge them without confirmation.
