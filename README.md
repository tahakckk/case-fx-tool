# Case study — Junior Software Engineer at mangolab

Two small tasks, **about two and a half hours in total.** Please do not spend
your weekend on this. If you run out of time, stop and write down what you would
have done next — that answer counts too.

Use Claude Code, Cursor, Copilot — whatever you normally use. That is how we work
every day, and we would rather see you use it well than watch you avoid it. The
only thing we ask is that you know your own code.

**Start by clicking "Use this template"** to create your own repository, then
work there.

---

## Part A — build (about 90 minutes)

A small HTTP service — Python + FastAPI preferred, TypeScript is fine — with one
endpoint an AI agent could call as a tool:

```
GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28
```

It answers using the public [Frankfurter API](https://frankfurter.dev) —
European Central Bank rates, no API key, no signup.

### Three things are fixed, so that we can run every submission the same way

| | |
|---|---|
| Upstream URL | from the `FX_UPSTREAM_BASE` environment variable, defaulting to `https://api.frankfurter.dev`. **Nothing may hardcode the real host** — we point this at a fake upstream when reviewing. |
| Port | from the `PORT` environment variable, default `8080` |
| Scripts | `./run.sh` starts the service, `./test.sh` runs the tests. Both are in this template, unimplemented. |

### The response

On success, 200 with:

```json
{
  "amount": 250,
  "from": "EUR",
  "to": "TRY",
  "rate": 47.1234,
  "result": 11780.85,
  "rate_date": "2026-08-28",
  "asked_date": "2026-08-28",
  "source": "ECB via frankfurter.dev"
}
```

`rate_date` is **the date the rate you used actually belongs to.** `asked_date`
is what the caller asked for. They are not always the same, and that difference
is the point of this task.

On failure, a non-2xx status and:

```json
{ "error": "<short_machine_code>", "message": "<a sentence a person could read>" }
```

List your error codes in your README.

### The part that matters

The caller is a language model talking to a paying customer, so **a wrong number
is worse than no number.** Decide — and implement — what happens when:

- the ECB published no rate for the date asked (weekends, holidays);
- the date is in the future, or before the series starts;
- the currency code does not exist, or `from` and `to` are the same;
- the upstream is slow, returns 500, or returns something that is not JSON;
- `amount` is missing, zero, negative, or has ten decimal places.

Your endpoint must never invent a rate, and must never present a rate as
belonging to a date it does not belong to. Note that the upstream itself tells
you which date its rates are from — read it. If you choose to answer with an
earlier published rate, the response has to make that visible, because the model
has to be able to tell the customer which day the number is from.

### Also required

- **Tests that pass with no network at all** — fake the upstream. We run
  `./test.sh` with `FX_UPSTREAM_BASE` pointing at a closed port.
- A README of your own we can follow in under a minute: how to run it, how to
  run the tests, your error codes, and what your endpoint does in each of the
  cases above.
- A repeat of the same question should not re-ask the upstream.
- `NOTES.md`, one page. The skeleton is in this repo.

### Not required, not scored

Auth, a database, a UI, a Dockerfile, CI, deployment, more endpoints. Adding them
will not help you; a smaller thing done carefully will.

---

## Part B — review (about 45 minutes)

`tool.py` in this repository is a working version of the same service, written
quickly with an AI assistant. It runs. **Review it as if it were going live
tomorrow for a customer who pays us.**

Fill in `REVIEW.md`, one page:

- what is wrong, and what it does to a **customer** — not to a linter;
- how you would verify each finding;
- your findings **ranked**, and which single one you would fix before shipping
  tonight.

Fewer findings, ranked and explained, beat a long list. If something looks
suspicious but is actually fine, saying so is worth as much as finding a real
defect.

---

## Submitting

Reply to our email with a link to your repository. Commit in small steps — the
history is part of what we read. Five days is plenty; if you need more, just say
so.

Any question about this brief, ask. An unclear requirement is our fault, not a
test.

---

<sub>mangolab — Mango Yazılım Teknolojileri Ltd. Şti. · [mangolab.ai/careers](https://mangolab.ai/careers)</sub>
