# API Smoke Test Script Plan

> **For future implementation only:** This document describes a local development smoke script. It is not a statement that the script already exists, and it is not intended to be a stable CI-quality test suite.

**Goal:** Define a lightweight `scripts/smoke_api.sh` plan that verifies the local FastAPI MVP with `curl` after the service has already been started by the developer.

**Architecture:** Keep the script small and explicit. It should not own process startup, dependency installation, or database seeding beyond simple API calls. Its purpose is local developer confidence: verify a few key endpoints, print actionable results, and document the manual `/upload_pdf` step without pretending external-search behavior is deterministic.

**Tech Stack:** Bash, curl, optional jq, existing FastAPI endpoints, local developer shell environment.

---

## Current State

What is already true today:

- The API exists in [backend/src/main.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/main.py).
- The README documents how to start the service manually.
- `/search` may depend on external sources and is not guaranteed to be stable offline.
- `/upload_pdf` exists and currently allows upload for any existing paper, not only `accepted` papers.
- There is currently no `scripts/smoke_api.sh` in this plan.

This document defines a future helper script for local smoke verification only.

## Script Purpose

The future script should answer one question:

- "Did my locally running service respond correctly on its main MVP endpoints?"

It should not try to answer:

- "Is the system stable enough for CI?"
- "Are third-party search providers healthy?"
- "Is the search ranking semantically correct?"

## Intended Usage

Recommended usage model:

1. Developer starts the backend manually.
2. Developer runs `scripts/smoke_api.sh`.
3. Script checks a few endpoints and prints pass/fail summaries.
4. Script prints a manual `/upload_pdf` verification command for the developer to run if desired.

Recommended non-goal:

- The script should not launch `uvicorn` itself in v1.

## Script Inputs

Recommended environment variables or flags:

- `BASE_URL`
  - default: `http://127.0.0.1:8000`
- `SEARCH_MODE`
  - default: `basic`
  - optional: `advanced`
- `SEARCH_QUERY`
  - default: `graph reconstruction`
- `UPLOAD_PAPER_ID`
  - optional
  - used only to print or run a manual upload command
- `UPLOAD_FILE`
  - optional
  - local PDF path for manual upload instruction output
- `CURL_BIN`
  - optional override for curl path
- `JQ_BIN`
  - optional override for jq path

Recommended v1 rule:

- Keep all inputs optional with sensible defaults.

## Dependencies

Required:

- Bash
- curl
- a running local FastAPI server

Optional:

- jq for nicer JSON formatting and simple field checks

Explicitly not required:

- new Python dependencies
- Chroma
- FAISS
- a test-only fake graph mode
- CI secrets or network credentials

## Planned Checks

### 1. Health Check

Call:

- `GET /health`

Expectation:

- HTTP `200`
- response contains `"status": "ok"`

This should be the strongest and simplest assertion in the script.

### 2. Logs Write Check

Call:

- `POST /logs`

Expectation:

- HTTP `200`
- response contains an `id`

Purpose:

- confirm write path works against local SQLite

### 3. Logs Read Check

Call:

- `GET /logs`

Expectation:

- HTTP `200`
- JSON list response

Purpose:

- confirm read path works and the service can return persisted log data

### 4. Search Check

Call:

- `POST /search`

Recommended default:

- use `{"mode":"basic","query":"graph reconstruction"}`

Expectation:

- HTTP `200`
- JSON array response

Important limitation:

- Because `/search` depends on external sources in the real runtime path, this check should not be the only strong assertion in the script.
- A `200` with an empty list may still be operationally informative.
- A network-related failure should be reported clearly as an external dependency issue, not silently treated as proof the whole backend is broken.

### 5. Candidates Check

Call:

- `GET /papers/candidates`

Expectation:

- HTTP `200`
- JSON list response

Purpose:

- confirm the candidate persistence/readback endpoint is reachable
- if `/search` returned results, attempt to surface one `paper_id` for the developer

### 6. Upload PDF Manual Verification

This should be printed as a manual step, not a required automated assertion in v1.

Reason:

- it needs a real local file
- it depends on picking an existing `paper_id`
- automating it increases script complexity and makes local usage more brittle

Recommended output:

- print a ready-to-copy `curl -F` example
- explain that the current code only requires the paper to exist
- remind the developer that `candidate -> upload_pdf -> uploaded` is currently allowed

## Output Design

Recommended output sections:

- environment summary
- passed checks
- soft warnings
- manual next steps

Recommended reporting style:

- clear single-line status per endpoint
- final summary at the end

Example categories:

- `PASS`: endpoint behaved as expected
- `WARN`: endpoint responded, but result depends on external network state
- `FAIL`: endpoint unreachable or returned unexpected structure

## Failure Policy

Recommended rule:

- hard-fail on `/health`, `/logs`, and `/papers/candidates` contract failures
- soft-warn on `/search` instability caused by external providers

Reason:

- `/search` currently depends on outside systems
- local smoke value comes from distinguishing app breakage from provider/network breakage

## Manual Upload Step Design

Recommended printed instructions:

1. Choose a `paper_id` from `/papers/candidates`.
2. Run a sample `curl` upload command with a local PDF.
3. Confirm the response contains:
   - `paper_id`
   - `status = "uploaded"`
   - `pdf_path`
4. Optionally re-run `/papers/candidates` or `/memory/summary` to inspect the updated state.

Important note the script should print:

- `/upload_pdf` is currently a local workflow smoke step, not a strong automated CI assertion.

## Non-Goals

This future script should not:

- start or stop the backend process
- seed a fake runtime search mode in production code
- claim CI stability
- require external provider success to count the whole script as useful
- verify `/embed` unless the script is later expanded into a fuller lifecycle smoke tool

## Risks

### Over-Trusting Search

Biggest script design risk:

- treating `/search` as a deterministic assertion when it depends on external sources

Mitigation:

- document `/search` as a soft operational check
- avoid making it the only pass/fail signal

### Scope Creep

Trying to automate upload, accept, embed, and network fallbacks all at once can turn a smoke script into a second test framework.

Mitigation:

- keep v1 narrow
- automate only the safest endpoints
- leave `/upload_pdf` as a documented manual step

### Hidden Environment Assumptions

Local scripts often fail because they assume `jq`, specific ports, or seeded data.

Mitigation:

- make `jq` optional
- make `BASE_URL` configurable
- print clear guidance when data-dependent steps cannot proceed

## Definition Of Done For The Future Script

This plan should only be considered implemented when all of the following become true:

- a `scripts/smoke_api.sh` file exists
- it assumes the local service is already running
- it verifies `/health`
- it writes and reads `/logs`
- it calls `/search` with documented caveats about external dependency
- it calls `/papers/candidates`
- it prints a manual `/upload_pdf` verification command
- its documentation states clearly that it is a local developer smoke script, not a stable CI test
