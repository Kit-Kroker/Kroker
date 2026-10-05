# Security

This project is **alpha** software for a single operator. Read this page
before pointing it at any repository.

## The short version

- **Run it only on repositories you own or fully trust.** The pipeline
  executes the target repository's code — build scripts, tests, dependency
  installs — as the user the worker runs as.
- **Run it only on localhost.** No surface is authenticated. Anyone who can
  reach the ports can start runs and approve gates.
- **There is one tenant: you.** Nothing separates one user's data from
  another's.

Nothing below weakens those three statements. The mechanisms that exist are
fences that keep an honest agent on the path; none of them is a boundary
against hostile input.

## What the pipeline does with a repository

A run clones the target repository into git worktrees and then:

- starts a coding harness (`claude -p`, `opencode run`) in the worktree with
  shell and file tools;
- installs the repository's declared dependencies and runs its test, lint
  and build commands;
- with deploy enabled (off by default), runs the project's deploy, smoke
  and rollback commands.

Every one of those steps runs code or instructions the repository controls.
PRD NFR-9 states the consequence: a connected repository is
attacker-controlled input, and executing its build scripts, tests,
configuration or dependency manifests is executing untrusted code.

## What is not there

| Missing | What follows from it | Tracked as |
|---|---|---|
| Per-run container, restricted OS user | Repository code runs as the worker user, with that user's files, toolchain and credentials in reach | FR-1002, E-21 |
| Network-level egress control | Any process started by a build, a test or an allowed shell call can open any connection | FR-1002, E-21 |
| A curated environment for build and test runs | Test, lint and dependency-install subprocesses inherit the worker's whole environment, provider API keys included (`src/sdlc/stages/qa/activities.py`) | NFR-5 |
| Repository-scoped, short-lived credentials | The harness is handed the worker's SSH agent socket (`SSH_AUTH_SOCK` is on the allowlist) and the operator's own provider credentials | FR-1003, E-20 |
| Authentication on the HTTP surfaces | `POST /api/runs` starts a run; `POST /api/runs/{id}/decide` answers a gate, the merge gate included; `POST /api/graphs` writes files; the board routes change task state | OQ-11 |
| A verified caller identity | `X-Actor` is whatever the client sends. It is recorded as the reviewer of a decision and proves nothing | OQ-11 |
| Authentication on Temporal | Reaching the Temporal port is enough to start workflows and signal approvals directly | — |
| Tenant isolation | No tenant concept exists; the artifact store, the board and memory are shared by everything the worker runs | FR-1001, NFR-8 |

OQ-11 is recorded in
[`docs/roadmap/pipeline-as-data.md`](docs/roadmap/pipeline-as-data.md); the
other identifiers are rows in [`PRD.md`](PRD.md) and
[`ROADMAP.md`](ROADMAP.md). FR-1002 is the gating item for running anyone
else's repository, not a hardening task.

## What is there, and how far it goes

- **Harness environment allowlist** (`src/sdlc/harness/base.py`). The coding
  harness receives a fixed list of variables plus the provider credentials
  it needs, not the worker's environment. This covers the harness process
  only — see the build-and-test row above.
- **Tool-level containment** (`policy/containment.yaml`, ADR-17). A
  `PreToolUse` hook and each harness's native deny rules refuse writes
  outside the worktree, recursive force-deletes, rewrites of the agent's own
  permission config, and tool calls to hosts off an allowlist. A harness
  with no enforcement layer is refused rather than run unfenced. The
  policy's own header says what this is: a fence, not a sandbox. A socket
  opened inside an allowed `Bash` call is invisible to it.
- **Secret scrubbing** (`src/sdlc/memory/scrub.py`) redacts a handful of
  secret-shaped patterns from harness sessions and memory before they are
  retained. Its own docstring calls it best-effort and not a security
  boundary.
- **The merge gate's security floor** scans the *change the pipeline
  produced* for critical findings. It protects the code being delivered. It
  does not protect the machine the pipeline runs on.

## Threats to plan around

1. **A hostile or compromised repository.** A `conftest.py`, a `setup.py`, a
   `postinstall` script or a Makefile target runs with your user's rights
   and network access and can read the provider keys in the worker's
   environment. A malicious dependency pulled in by an honest repository
   lands in the same place.
2. **Instructions hidden in content.** Repository files and — with research
   enabled — fetched web pages are model input. Text in them
   can steer an agent that holds shell and file tools. The tool-level fence
   narrows what a steered agent can do; it does not stop a network call made
   from inside an allowed command.
3. **Anyone on the network.** A dashboard or board API bound to anything
   other than loopback hands run control and gate approval to whoever can
   connect. The Markdown artifact URLs are meant to be pasted into chats and
   tickets, which makes the bind address easy to forget.
4. **Published ports.** `docker-compose.yml` publishes Temporal (7233, 8233)
   and Hindsight (8888, 9999) on `127.0.0.1` only. Keep it that way: neither
   service authenticates its callers, and a mapping without the loopback
   prefix publishes on every host interface.

## Running the alpha safely

- Use repositories you wrote, or have read closely enough to run their test
  suite on your own machine without the pipeline.
- Bind the API to `127.0.0.1`, as the README command does. Do not put it
  behind a tunnel or a reverse proxy.
- Run the worker on a machine or in a VM that holds nothing you could not
  afford to leak, with provider keys that carry a spend limit.
- Leave the deploy stage off unless you have read the commands it will run.

## Reporting a vulnerability

Report privately through GitHub: **Security → Report a vulnerability** on
[Kit-Kroker/Kroker](https://github.com/Kit-Kroker/Kroker/security/advisories/new).
Please do not open a public issue for something exploitable.

Include what you ran, what you expected and what happened. A minimal
repository or request that reproduces it helps most.

This is a small alpha project with no response-time commitment and no
bounty. Fixes land on `main`; no other version is supported.

The gaps listed under [What is not there](#what-is-not-there) are known and
documented, so a report that restates one of them is not a vulnerability.
A way around a mechanism listed under
[What is there](#what-is-there-and-how-far-it-goes) is.
