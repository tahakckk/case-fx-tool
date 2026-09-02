# Notes

## Decisions

- Prefer an explicit error to an invented or incorrectly dated rate: an agent may present the result directly to a customer. Validate upstream status, schema, base, rate and date before caching or returning a rate.
- Accept an earlier publication date returned for weekends or holidays, preserving it in `rate_date` and keeping the request in `asked_date`. Do not call `/latest` as a fallback. Reject future requests and upstream dates later than requested.
- Use `Decimal` throughout calculation and round only the result to two places with `ROUND_HALF_UP`, avoiding early rate rounding.
- Cache only successful, validated rates and their actual dates in the process, keyed by currency pair and asked date. This reuses rates across amounts while allowing retries after errors.
- Keep HTTP handling, configuration, response models and conversion in small modules. A repository abstraction, database, Docker and CI were unnecessary for this brief.
- Use `httpx.MockTransport` and a fixed clock for offline tests. Unexpected HTTP calls fail; tests check error bodies, dates and upstream call counts.

## With another day

- Bound cache size and lifetime, and coalesce concurrent requests for the same rate.
- Define an amount limit using total digits or an explicit upper bound.
- Add operational metrics and structured logging.
- Add a separate, optional live integration test for the Frankfurter contract; keep the default suite offline.

## AI tools

I used OpenAI Codex to turn the brief into an acceptance checklist, create the modular foundation, generate test matrices and assist with diff reviews. Each step stayed small; tests ran without network access, and changes were reviewed as diffs before committing. The output was checked through tests and review rather than accepted without verification.

## One thing the AI got wrong

The initially generated `run.sh` and `test.sh` had Windows CRLF on their shebang lines. This could cause a Linux execution error such as `/usr/bin/env: 'bash\r'`. A byte/line-ending check before the first commit caught it. Both scripts were normalized to LF, and `*.sh text eol=lf` was added to `.gitattributes`.
