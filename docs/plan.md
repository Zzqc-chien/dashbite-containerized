# Plan: Containerize DashBite

| | |
|---|---|

> Reviewed by Qianchun Zhang: I chose to include the atomic-write fix
> because the restart policy would otherwise hide these crashes.

| **Role** | Architect (design only — no code in this change) |
| **Baseline** | `2c75df2` "Import DashBite baseline from class demo" — 33 tests green via `make test` |
| **Goal** | Run the whole pipeline with Docker Compose, and make it container-ready beyond a basic Dockerfile |
| **Related** | [docker-k8s-guide.md](./docker-k8s-guide.md) (this plan implements its Part 1, with the deviations noted below), [lld-dashbite-ml-pipeline.md](./lld-dashbite-ml-pipeline.md) |

## TL;DR

- **One image, five services, one named volume.** Every stage runs from `dashbite:local` with a different `command`; all share a volume mounted at `/data`.
- **Five small code changes, no ML changes:** `DATA_ROOT` override in `pipeline/paths.py`; the dashboard stops pinning its data to the source tree; a shared run loop that stops cleanly on SIGTERM and writes a heartbeat; a stdlib-only health probe (`python -m pipeline.healthcheck <stage>`); and, as the last step, atomic writes for the files stages hand to each other.
- **Makefile stays the interface:** new `docker-*` targets; every existing target keeps its name and behaviour, and `make test` still needs no Docker.
- **Tests:** the 33 existing tests are untouched; 26 new tests (59 total). The same suite runs inside the image with `make docker-test`.
- **Feasibility-checked.** Before writing this, I tried the design in a throwaway copy of the repo (not committed or shared): stop time went from **10.1 s / exit 137 to 0.5 s / exit 0**, all five services reached `healthy`, host suite **58 passed, 1 skipped**, in-image suite **56 passed, 3 skipped**. See [Appendix A](#appendix-a--how-this-plan-was-checked) for what was and wasn't verified.

---

## 0. What the repository looks like today

Findings that shape the design (file references are to the baseline commit):

| # | Finding | Why it matters in a container |
|---|---|---|
| F1 | Every worker is `while True: work(); time.sleep(poll)` with no signal handling (`simulator.py:120`, `preprocess.py:162`, `train.py:145`, `infer.py:107`). | As PID 1 in a container, Python **ignores SIGTERM** (the kernel drops default-action signals for a namespace's init). `docker stop` waits the 10 s grace period, then SIGKILLs — possibly mid-write. Measured: 10.1 s, exit 137. |
| F2 | `paths.data_root(base)` returns `(base or PROJECT_ROOT) / "data"`; no override exists. Tests pass `base=tmp_path` and assert `tmp_path / "data"`. | Data location is welded to the code location. Any override must keep "explicit `base` wins" so existing tests stay valid. |
| F3 | `dashboard/app.py:46` sets `base = PROJECT_ROOT` and passes it to every loader. | Even with an env override in `paths.py`, the dashboard would **silently** read `/app/data` and show "No predictions yet" forever. |
| F4 | `Config` is frozen by `tests/regression/test_stage0_config.py` (exact dict match). | Adding a `data_root` field to `Config` would break a golden test. |
| F5 | Logging is `print()`. | When stdout is not a TTY, Python block-buffers it. Measured: **0 bytes** of simulator output after 4 s without `PYTHONUNBUFFERED=1`; `docker compose logs` would look dead. |
| F6 | Streamlit 1.64 (what `requirements.txt` resolves today) installs its own SIGTERM handler and serves `GET /_stcore/health → 200 "ok"`. | The dashboard already shuts down cleanly (measured 0.4 s as PID 1) and has a ready-made health endpoint. No dashboard code needed for these two. |
| F7 | `requirements.txt` has lower bounds only. Today: pandas 3.0.6, scikit-learn 1.9.1, streamlit 1.64.0; numpy resolves to **2.4.6 on Python 3.11 but 2.5.3 on 3.12**. | Host and image can already differ. The in-image test run is the guard (see R7). |
| F8 | `docs/docker-k8s-guide.md` already proposes one image, a `DATA_ROOT` env var and one Compose service per stage. | This plan follows it. Deviations: data at `/data` (not `/app/data`), file named `compose.yaml`, localhost-only port, read-only dashboard mount. |

---

## 1. Requirements and constraints

**Functional**

- **R1.** `make docker-up` builds one image and starts all five stages; data flows simulator → preprocess → train/infer → dashboard through one shared volume.
- **R2.** The dashboard is reachable at `http://localhost:8501` and shows live numbers.
- **R3.** `make docker-down` stops every container in about a second, with exit code 0 and no half-written files from being killed.
- **R4.** `docker compose ps` reports a meaningful health state for all five services.
- **R5.** `make docker-test` runs the full pytest suite inside the image.

**Constraints**

- **C1. The Makefile is the public interface.** New `docker-*` targets are added. Existing targets (`install`, `test*`, `simulator` … `dashboard`, `run`, `stop`, `clean*`) keep their names and behaviour. `make test` must not need Docker.
- **C2. No pipeline-logic changes.** File names, CSV schemas, checkpoint format and ML behaviour stay as they are. Train and infer still never import each other; the existing source-inspection tests keep passing.
- **C3. The 33 existing tests pass unmodified.** Test infrastructure (`conftest.py`, `pytest.ini`) may change.
- **C4. No new runtime dependencies.** New code is stdlib-only.
- **C5. One Dockerfile, one image** for every stage and for the test run.
- **C6. Portable.** Works on Docker Desktop (macOS, Apple Silicon and Intel) and Linux Docker Engine with Compose v2 (`docker compose`). All dependencies ship arm64 and amd64 wheels, so no compiler is needed in the image.
- **C7. The host workflow is unaffected.** `make run` / `make stop` still use `./data`; containers use the volume. The two never share files.

**Non-goals.** Kubernetes manifests, CI, multi-replica safety (claim or shard logic), and image publishing to a registry. Some are listed as follow-ups in §4.

---

## 2. Proposed files and changes

This section specifies *what* each file must do and the interfaces other parts depend on. How to write it is left to the Builder; snippets show only the contracts that must match exactly.

| File | New / changed | Responsibility |
|---|---|---|
| `Dockerfile` | new | One image for all stages and for the test run |
| `.dockerignore` | new | Keep host-only and generated files out of the build context |
| `compose.yaml` | new | Five pipeline services plus a `tests` service, one named volume |
| `pipeline/lifecycle.py` | new | Stop flag, signal handler installation, heartbeat, shared run loop |
| `pipeline/healthcheck.py` | new | Health probe CLI for all five services |
| `pipeline/paths.py` | changed | `DATA_ROOT` override inside `data_root()`; new `atomic_path()` helper (step 6) |
| `pipeline/{simulator,preprocess,train,infer}.py` | changed | `run_loop` uses the shared loop and accepts a stop flag; `main()` installs handlers; handoff files are written through `atomic_path()` (step 6) |
| `pipeline/dashboard/app.py` | changed | Stop pinning data to `PROJECT_ROOT` |
| `Makefile` | changed | `docker-*` targets; `clean-data` honours `DATA_ROOT` and removes leftover temp files; unbuffered output |
| `pytest.ini`, `tests/conftest.py` | changed | `container` marker; environment isolation fixture |
| `tests/…` (6 files) | new | See §5 |
| `README.md`, `docs/docker-k8s-guide.md` | changed | "Run with Docker" section, new env vars, updated checklist |

`docs/lld-dashbite-ml-pipeline.md` stays as it is. It describes lessons 0–7 ("no containers") and remains accurate for those stages.

### 2.1 `Dockerfile`

Requirements:

- **Base:** `python:3.12-slim` (multi-arch; every dependency ships arm64 and amd64 wheels, so no compiler and no multi-stage build).
- **Layer order:** install `requirements.txt` before copying source, so code edits don't reinstall dependencies.
- **Contents:** `pipeline/`, `tests/` and `pytest.ini`. Tests ship in the image (fixtures are a few KB and `pytest` is already a dependency), so the image that runs is the image that gets tested.
- **Environment:** `PYTHONUNBUFFERED=1` (F5), `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=/app`, `DATA_ROOT=/data`, `HEARTBEAT_DIR=/tmp/dashbite`, `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`, and pip's no-cache setting.
- **User:** an unprivileged user named `app` (uid 10001). **The image must contain `/data`, owned by `app`** (created and chowned while still root, before `USER app`). This is what makes the shared volume writable; see §3.5.
- **Default command:** the dashboard, in exec form, listening on `0.0.0.0:8501`, headless. `EXPOSE 8501`. Workers override the command in Compose.
- **Exec form everywhere** (`CMD` and every Compose `command`) so Python or Streamlit is PID 1 and receives SIGTERM directly, with no `sh -c` wrapper.
- **No `HEALTHCHECK` instruction** (probes differ per service; see §2.3).

Expected size is about 0.8 GB, dominated by pyarrow (via Streamlit), scipy (via scikit-learn) and pandas (R10).

### 2.2 `.dockerignore`

Must exclude at least `.venv/` (large, and contains macOS binaries that are wrong inside Linux), `data/` (grows without bound during `make run`), `.git`, `.logs/`, caches and bytecode, and `.streamlit/`. `docs/` may be excluded because nothing in the image reads it.

### 2.3 `compose.yaml`

Required shape:

| Service | Command | Volume | Health probe | Notes |
|---|---|---|---|---|
| `simulator` | `python -m pipeline.simulator` | `dashbite-data` at `/data` | `pipeline.healthcheck simulator` | |
| `preprocess` | `python -m pipeline.preprocess` | same | `… preprocess` | |
| `train` | `python -m pipeline.train` | same | `… train` | |
| `infer` | `python -m pipeline.infer` | same | `… infer` | |
| `dashboard` | image default | same, **read-only** | `… dashboard` | Port `127.0.0.1:8501:8501`; longer start period |
| `tests` | `pytest -q -p no:cacheprovider` | **none** | none | In profile `test`, so `up` skips it |

Cross-cutting requirements:

- **Project name `dashbite`,** so container and volume names are predictable (`dashbite-train-1`, `dashbite_dashbite-data`). The smoke test relies on them.
- **One image, `dashbite:local`,** built from `.` for every service. Share configuration with YAML anchors rather than repeating it five times.
- **Environment** for all pipeline services: `DATA_ROOT=/data` plus the tuning knobs interpolated from the shell with the Makefile's demo defaults as fallbacks, for example `${BATCH_SIZE:-20}`. Because the Makefile already exports these, `make docker-up BATCH_SIZE=50` works like `make run BATCH_SIZE=50`.
- **Health timing** for workers: about a 10 s interval, 5 s timeout, 3 retries and a 20 s start period.
- **`restart: on-failure`** on the pipeline services.
- **No `depends_on` and no `container_name`.**

Why:

- **No `depends_on`.** Each stage already tolerates missing upstream data (preprocess idles on an empty `raw/`, train returns `None`, infer logs "waiting"). Startup ordering would couple services that are decoupled on purpose, which is one of the lesson's teaching points.
- **`on-failure` rather than `unless-stopped`.** A crash (for example, a half-written file; see R1) restarts the stage. A clean stop (exit 0, now that SIGTERM is handled) does not. After a laptop or Docker Desktop restart, the demo doesn't silently resume filling the volume.
- **Read-only dashboard mount.** `app.py` never writes, and the mount makes the read/write boundary between stages visible.
- **Localhost port.** Docker publishes on all interfaces by default. To show the dashboard to a room, change it to `"8501:8501"` deliberately.
- **No `container_name`,** so `docker compose up --scale infer=2` stays possible for the guide's experiment (R8).
- **Probes in Compose, not the Dockerfile.** The probe differs per service, the one-off `tests` container shouldn't carry one, and each entry maps one-to-one onto a Kubernetes `livenessProbe` later.
- **`tests` in a profile.** `docker compose run --rm tests` works without `--profile`, and the service mounts no volume, so tests can never touch pipeline data.

### 2.4 Makefile

New targets (the public interface):

| Target | Behaviour |
|---|---|
| `docker-build` | Build the image |
| `docker-up` | Build if needed, start all five services detached, print the dashboard URL |
| `docker-ps` | Show status and health |
| `docker-logs` | Follow logs; `SERVICE=<name>` narrows to one service |
| `docker-down` | Stop and remove containers; **keep** the volume |
| `docker-clean` | Also delete the volume |
| `docker-test` | Build, then run the `tests` service once and remove it |

Also:

- A `COMPOSE ?= docker compose` variable so another runtime can be substituted.
- None of the new targets depend on `install`, so a machine with only Docker can use them. The `docker-` prefix keeps them distinct from the host `run` and `stop`.
- Add them to `.PHONY` and `make help`.
- `clean-data` also removes leftover hidden temp files (`.*.tmp`) under each data subfolder (step 6).
- `clean-data` uses a `DATA_ROOT ?= $(CURDIR)/data` variable instead of the hard-coded `data/` prefix. Don't export it; the host default must stay the repo's `data/`.
- Export `PYTHONUNBUFFERED=1` so `.logs/*.log` update live during `make run`.
- Pitfall: keep comments on their own lines. Make keeps the spaces before a trailing `#` as part of the value, so `DATA_ROOT ?= …/data   # note` would expand with trailing spaces and break `clean-data`'s `rm` paths.

### 2.5 Code changes (interfaces)

**`pipeline/paths.py`.** `data_root(base=None)` resolves in this order:

1. explicit `base` → `base / "data"` (unchanged; existing tests depend on it);
2. otherwise `$DATA_ROOT`, used as-is (it names the data directory itself), read at call time; a blank value counts as unset;
3. otherwise `PROJECT_ROOT / "data"`.

Everything else in `paths.py` keeps its signature. Document the precedence in the docstring (R3).

**`pipeline/lifecycle.py`** (new, stdlib only, so the health probe can import it cheaply). Public interface:

```python
class StopFlag:
    requested: bool
    def request(self, *_) -> None: ...          # usable directly as a signal handler
    def sleep(self, seconds: float) -> None: ... # returns early once a stop is requested

def install_stop_handlers(flag: StopFlag | None = None) -> StopFlag: ...  # SIGTERM + SIGINT
def heartbeat_path(stage: str) -> Path | None: ...  # $HEARTBEAT_DIR/<stage>.heartbeat, None if unset
def beat(stage: str) -> None: ...                   # touch the heartbeat; no-op if unset
def run_forever(stage: str, step: Callable[[], object],
                poll_interval: float, stop: StopFlag | None = None) -> None: ...
```

Behaviour:

- `run_forever` repeats *step → beat → sleep* until the flag is set, then prints `<stage> stopped` and returns (process exit code 0).
- The signal handler must only set a flag. It must not take locks (see §3.2 for why `threading.Event` is not used).
- `sleep` polls in short slices (about 0.2 s) so a stop is noticed quickly.
- Handlers are installed only from each stage's `main()`, never inside `run_loop`, so tests don't alter pytest's signal handling.
- Exceptions raised by `step` are **not** caught (§3.8).

**Workers.** Each `run_loop` gains an optional `stop: StopFlag | None = None` parameter (existing callers are unaffected) and hands its existing per-iteration work to `run_forever` under its stage name: `simulator`, `preprocess`, `train` or `infer`. The work itself doesn't change; for example, infer's "using checkpoint …" bookkeeping moves into its step unchanged. `main()` becomes `run_loop(stop=install_stop_handlers())`. Remove any `import time` left unused.

**`pipeline/healthcheck.py`** (new, stdlib only; no pandas import, so each probe is cheap). CLI contract:

```
python -m pipeline.healthcheck {simulator|preprocess|train|infer|dashboard}
exit 0 = healthy, 1 = unhealthy, 2 = usage error; prints one explanatory line
```

- **Workers:** healthy when the stage's heartbeat file exists and is younger than `HEARTBEAT_MAX_AGE_SECONDS`, which defaults to `max(30, 3 × POLL_INTERVAL_SECONDS)`.
- **Dashboard:** healthy when `GET http://127.0.0.1:8501/_stcore/health` returns 200 (URL overridable via `DASHBOARD_HEALTH_URL`). Bypass any proxy environment variables for this request, so a proxy injected into the container (for example by Docker Desktop's proxy setting) can't hijack a localhost probe.
- The printed line appears in `docker inspect … .State.Health.Log`, so make it diagnostic, for example stating the heartbeat's age and the limit.

**`pipeline/dashboard/app.py`.** Stop passing `PROJECT_ROOT` to the loaders; call them without `base`, so they resolve through `data_root()`. The module must no longer reference `PROJECT_ROOT` (a test checks this).

**Atomic handoff writes (step 6), in `pipeline/paths.py`.** Interface:

```python
@contextmanager
def atomic_path(final: Path) -> Iterator[Path]: ...
# yields a temp path in the same folder; on normal exit, publishes it as `final`
# in one rename; on an exception, leaves `final` untouched and removes the temp file
```

Rules:

- **Temp name:** hidden (starting with `.`) and in the *same directory* as the final file, for example `.orders_…csv.tmp`. Same directory is what makes `os.replace` a single atomic rename. The leading dot keeps it out of every reader's glob (`orders_*.csv`, `features_*.csv`, `checkpoint_*.joblib`, `predictions_*.csv`), so a reader either sees nothing or the complete file.
- **Call sites, one change each:** the raw batch in `simulator.write_batch`; the features CSV in `preprocess.process_new_raw_files`; the checkpoint and its metrics JSON in `train.write_checkpoint` (write the metrics first, so a visible checkpoint always has its metrics); `train.save_state`; the predictions CSV in `infer.run_once`.
- **Deliberately not changed:**
  - The quality log. It gets one short line appended per batch, and only the dashboard reads it, so the worst case is one odd refresh.
  - The `.done_*` markers, which are only checked for existence.
- **No change to file names, contents or order of work,** so every existing test holds.

**New environment variables** (document all of them in the README config table):

| Variable | Default | Meaning |
|---|---|---|
| `DATA_ROOT` | `<project>/data` (image: `/data`) | Shared pipeline data directory |
| `HEARTBEAT_DIR` | unset, so no heartbeat (image: `/tmp/dashbite`) | Where workers touch `<stage>.heartbeat` |
| `HEARTBEAT_MAX_AGE_SECONDS` | `max(30, 3 × POLL_INTERVAL_SECONDS)` | Staleness limit for worker probes |
| `DASHBOARD_HEALTH_URL` | `http://127.0.0.1:8501/_stcore/health` | Dashboard probe target |

---

## 3. Container-readiness improvements (evaluated)

### 3.1 Configurable data directory via environment variable — **adopt**

| Option | Verdict |
|---|---|
| (a) No env var; mount the volume at `/app/data` (= `PROJECT_ROOT/data`) | Zero code, but it keeps data welded to the code path, hides bug F3 (the dashboard would "work" by accident), and needs `/app` to be writable by the non-root user. I checked this: the current code in a non-root image crashes with `PermissionError: '/app/data'`. |
| **(b) `DATA_ROOT` read inside `paths.data_root()` at call time** | **Chosen.** One function, so every stage and the dashboard follow it. Reading at call time (not import time) means tests can `monkeypatch.setenv` with no import-order traps. |
| (c) A `data_root` field on `Config` | Breaks the frozen-config regression test (F4). It would also mix *where data lives* with *model tuning knobs*, and need `cfg` threaded into every path call. |
| (d) A `--data-root` CLI flag per stage | More plumbing, and awkward to pass through `streamlit run`. |

Details:

- **Name:** `DATA_ROOT`, matching `docker-k8s-guide.md`.
- **Semantics:** points at the data directory itself (the folder containing `raw/`, `features/` and so on). Precedence is explicit `base` > `DATA_ROOT` > `<project>/data`; a blank value is ignored.
- **Container value:** `/data`, outside `/app`. This is deliberate: any code path that still ignores `DATA_ROOT` reads an empty directory and fails visibly, rather than accidentally working the way it would at `/app/data`.

### 3.2 Graceful shutdown on SIGTERM — **adopt, in the app**

| Option | Stop time | Verdict |
|---|---|---|
| (a) Do nothing | 10 s, then SIGKILL (exit 137) — measured | The kill can land mid-`to_csv` or mid-`joblib.dump`. |
| (b) `init: true` (tini as PID 1 forwards the signal) | ~instant | Zero code, but Python's default SIGTERM action is still "die now", so a write can still be cut off. A reasonable fallback if code changes were off the table. |
| **(c) Handler sets a flag; the loop finishes its current iteration and exits 0** | 0.5 s measured (worst case: one iteration plus 0.2 s) | **Chosen.** No half-written files from shutdown, a clean exit code that works with `restart: on-failure`, and a "stopped" log line. |

Details:

- **Why a plain flag instead of `threading.Event`.** `Event.set()` takes a non-reentrant lock. If SIGTERM arrives while the main thread is inside `Event.wait()`'s own locked section, the handler deadlocks. A bool assignment can't deadlock. The loop sleeps in 0.2 s slices so it notices the flag quickly.
- **Handlers are installed only in `main()`.** Tests call `run_loop(stop=...)` directly and never touch pytest's own signal handlers.
- **SIGINT is handled the same way.** Ctrl-C on `make simulator` now prints `simulator stopped` instead of a `KeyboardInterrupt` traceback. `make stop` (SIGTERM) also becomes graceful.
- **Dashboard: no change.** Streamlit already handles SIGTERM (F6).

### 3.3 Health checks — **adopt** (dashboard: HTTP; workers: heartbeat)

- **Dashboard.** Use Streamlit's `/_stcore/health`, probed with Python's `urllib`, because `python:3.12-slim` has no `curl` or `wget`. Rejected alternatives:
  - A raw TCP connect: this only proves the port is open.
  - `/_stcore/script-health-check`: it executes `app.py` on every probe, is disabled by default, and our script's 2-second auto-refresh loop makes it a poor probe.
- **Workers** have no port, so the choice is what "alive" means:

| Option | Verdict |
|---|---|
| Process alive (`pgrep`) | Meaningless: if PID 1 dies, the container exits anyway. |
| Output freshness (for example, "new file in `raw/` within N s") | Wrong for this pipeline: train is legitimately idle between thresholds, and infer idles until the first checkpoint. It would report healthy stages as unhealthy. |
| **Heartbeat file touched after every loop iteration** | **Chosen.** Detects a *hung* loop (blocked I/O, deadlock). A *crashed* loop exits the container, which `restart: on-failure` handles. |

Heartbeat details:

- **Location.** Container-local `/tmp/dashbite/<stage>.heartbeat`, not the shared volume. With `--scale infer=2`, a shared file would let one live replica mask a hung one.
- **Opt-in.** The heartbeat is only written when `HEARTBEAT_DIR` is set (the image sets it), so host runs gain no side effects.
- **Staleness limit.** A worker is unhealthy when its heartbeat is older than `HEARTBEAT_MAX_AGE_SECONDS`, which defaults to `max(30, 3 × POLL_INTERVAL_SECONDS)`. See "How the limit relates to the poll interval" below.
- **Honest limits:**
  - This is *liveness*, not *progress*.
  - Plain Docker Compose **does not restart unhealthy containers**. Health appears in `docker compose ps` and can gate `depends_on: condition: service_healthy`.
  - Acting on "unhealthy" is Kubernetes' job: the same command becomes an `exec` `livenessProbe` there.
  - Prototype timing: a frozen `train` turned `unhealthy` about 60 s after being frozen and returned to `healthy` about 10 s after it resumed.

**How the limit relates to the poll interval.** Each iteration is *step → touch heartbeat → sleep `POLL_INTERVAL_SECONDS`*, so in a healthy worker the heartbeat's age never exceeds one step's duration plus one poll interval. The limit has to sit comfortably above that, and the two terms of `max(30, 3 × poll)` cover the two ways that can go wrong:

| `POLL_INTERVAL_SECONDS` | Limit | Normal worst-case age | Room left for a slow step |
|---|---|---|---|
| 2 (demo default) | 30 s | ≈ 2 s + step | ≈ 28 s |
| 10 | 30 s | ≈ 10 s + step | ≈ 20 s |
| 20 | 60 s | ≈ 20 s + step | ≈ 40 s |

- **The 30 s floor** protects fast polls. At a 2 s poll, `3 × poll` would be only 6 s, and a single slow iteration would trip it: after an hour, one full re-read of the features takes ~1.6 s (R6), and train or infer do more than one read per step.
- **The `3 × poll` term** protects slow polls. Without it, a poll of 30 s or more would fail every probe even when nothing is wrong. With it, a slow step always has at least `2 × poll` of headroom.
- `HEARTBEAT_MAX_AGE_SECONDS` overrides both, for tests or unusual deployments. Keep it above `poll + slowest step`.

**How long until Docker says "unhealthy".** Docker needs `retries` consecutive failing probes, spaced `interval` apart. Measured from the last heartbeat, that is between `limit + (retries − 1) × interval` and `limit + retries × interval`: **about 50–60 s** with the defaults (30 s limit, 10 s interval, 3 retries). The prototype's frozen `train` flipped with a heartbeat 57 s old. The start period doesn't delay this for a worker that hangs later; it only excuses failures while a container is starting.

**What "stuck" means to the probe.** The probe runs as a separate process, so it doesn't matter *why* the loop stopped touching the file: frozen (SIGSTOP), blocked in a system call, deadlocked or spinning in an endless loop all look the same. The process is still running, so `restart: on-failure` does nothing. The health status is the only signal.

**One consequence for graceful shutdown.** A worker blocked inside a system call never returns to its loop, so it can't see the stop flag. SIGTERM then does nothing, and Docker SIGKILLs it after the 10 s grace period. On the host, a preprocess process blocked reading a FIFO was still alive 2 s after SIGTERM. That is the correct outcome: the grace period is the backstop for exactly this case (R13).

### 3.4 Running the test suite inside a container — **adopt**

| Option | Verdict |
|---|---|
| `docker run --rm dashbite:local pytest` from the Makefile | Works, but duplicates the image name and build config outside Compose. |
| **A `tests` service under `profiles: ["test"]`, run by `make docker-test`** | **Chosen.** Same image and build definition as the pipeline. Excluded from `up`, and it mounts no volume, so tests can never touch pipeline data. |
| A separate multi-stage `test` target | Keeps pytest and tests out of the runtime image, but adds a second build path to maintain. Not worth it at this size. |

What makes the suite container-safe:

- **Environment isolation.** An **autouse fixture** clears `DATA_ROOT`, `HEARTBEAT_DIR` and `HEARTBEAT_MAX_AGE_SECONDS` for every test. The image sets these variables. Without the fixture, 2 of the new tests fail inside the image (checked by disabling it), and future tests would silently depend on the machine they run on.
- **Read-only code directory.** `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1` avoid cache-write warnings, because `/app` is not writable by the `app` user. Pytest's `tmp_path` lives in `/tmp`, which is writable.
- **Skip what can't run.** The three compose/Dockerfile tests skip inside the image (there is no `compose.yaml` or Docker CLI there), and the `/data` ownership test skips on the host. Expected in-image result: **56 passed, 3 skipped**.
- **Why it's worth it:** it runs the suite on Linux with Python 3.12 and the exact wheels in the image. That catches the host-vs-image drift described in F7 and R7.

### 3.5 Ownership of the shared volume on first start

This is the one place where running as non-root can break the pipeline, so it gets its own acceptance checks.

**Who owns `/data`.** When Compose creates `dashbite-data` and mounts it at `/data` for the first time, Docker copies the *image's* `/data` directory into the empty volume, including its owner and permissions. So the volume is owned by whoever owns `/data` in the image, and only the Dockerfile decides that. I checked all three cases on the prototype image:

| Case | Volume owner | Worker as uid 10001 |
|---|---|---|
| Image has `/data` owned by `app`; fresh volume | 10001 | writes fine |
| Image has no `/data` (Docker creates the mount point) | **root** | `PermissionError: [Errno 13]` |
| Volume already holds files, owned by root from an earlier build | **root** (no re-copy into a non-empty volume) | `PermissionError: [Errno 13]` |

**What failure looks like.** Every worker calls `ensure_data_dirs()` at start-up, which does `mkdir /data/raw` and so on. If `/data` isn't writable, simulator, preprocess, train and infer all crash immediately with `PermissionError: [Errno 13] Permission denied: '/data/raw'` (or another subdirectory). `restart: on-failure` then turns that into a loop: `make docker-ps` shows `Restarting (1)` on all four workers while the dashboard (read-only, never writes) stays `healthy` and shows zeros. Health checks never get a chance to report it, because the processes die before the first heartbeat.

**The stale-volume trap.** The copy only happens into an *empty* volume. Fixing a wrong Dockerfile and rebuilding does not repair a volume that a broken build already wrote to; it needs `make docker-clean` first. The reverse also matters for testing: a smoke test run on a volume left over from an earlier session does not exercise first creation at all.

**How it is caught:**

1. **Automated, in `make docker-test`:** a new in-image test asserts that `/data` in the image is owned by the running user and writable (§5). The `tests` service mounts no volume, so this checks exactly the directory Docker will copy into a fresh volume. I confirmed it fails on an image whose `/data` is root-owned.
2. **Manual, in the smoke test:** start from `make docker-clean` so the volume really is new, then check ownership and a write explicitly before looking at anything else (§7, Step 2).
3. **Acceptance checklist** includes both (§8).

**Not adopted:** an entrypoint that runs as root, `chown`s `/data`, then drops privileges. It would also repair stale volumes, but it adds a shell script and a privilege-dropping tool (`gosu`/`setpriv`) to a teaching image. The in-image test plus `docker-clean` covers the realistic failure modes more simply. Bind mounts get no copy at all; see R9.

### 3.6 Atomic writes for handoff files — **adopt, as the last step**

**The problem.** Each stage writes straight to the final filename, and readers find new work by globbing those names. So a reader can open a file that exists but isn't written yet. This predates containers.

**How likely, measured with the original code on the host:**

| Measurement | Result |
|---|---|
| Time a new file is visible but empty | about 0.25 ms |
| System calls to write a 20-row batch (1.8 KB) | 1, so a reader can only catch an *empty* file |
| System calls to write a 500-row batch (44 KB) | 6, so a *truncated* read is possible in principle |
| 90 s stress run, every stage polling 200× faster than the demo | 1 failure in 6,461 batches: preprocess crashed with `EmptyDataError` |
| 500-row batches, 2,510 of them | 0 truncated reads |

At the demo's 2 s poll, readers scan 200× less often. That suggests roughly one crash per tens to hundreds of hours of running, most likely early in a run while folders are small. This is an estimate from one stress run, not a precise rate.

**Consequences.**
- An empty raw or features file crashes preprocess, train or infer; an empty checkpoint crashes infer. The stage restarts and redoes the work, so nothing is lost.
- The dashboard shows an error for one refresh.
- Silent row loss needs batches over ~90 rows and was never observed.

**Why it belongs in this plan.** Containers don't make it more likely: a named volume behaves like a normal Linux disk. But `restart: on-failure` turns each occurrence into a silent restart, visible only in the restart count. A user would have no way to tell a real bug from this race. The fix is small, doesn't change behaviour, and was verified:

| Check on the prototype | Result |
|---|---|
| Same 90 s stress run with the fix | 0 failures in 6,351 batches |
| Temp files left behind | none |
| Full suite | 58 passed, 1 skipped on the host; 56 passed, 3 skipped in the image |

**Why it's the last step.** It is independent of the container work and touches pipeline I/O, which the earlier steps don't. Keeping it in its own commit lets it be reviewed, or reverted, on its own.

**Residual risk:**
- A hard kill (R13) can leave a hidden `.tmp` file behind. No reader sees it, and `make clean-data` / `make docker-clean` remove it.
- The quality log stays append-only (§2.5).

### 3.7 Other small defaults adopted

- `PYTHONUNBUFFERED=1` (F5)
- Non-root `app` user (uid 10001)
- Localhost-only port
- Read-only dashboard mount
- `restart: on-failure`
- `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false` (no telemetry from a headless container)
- `PYTHONUNBUFFERED` also exported by the Makefile so `.logs/*.log` update live during `make run`

### 3.8 Considered and not adopted (now)

| Idea | Why not |
|---|---|
| Catch exceptions inside `run_forever` and keep looping | It hides bugs and turns a visible restart into a silent, repeating traceback. Crash plus `restart: on-failure` is the container-native pattern. |
| A lock file / `constraints.txt` for exact versions | Real reproducibility needs a lock generated *inside* the image, per Python version, plus a regeneration workflow. Deferred; `make docker-test` guards the risk in the meantime (R7). |
| Bind-mount `./data` into the containers | It's nice for `ls`, but it mixes host and container runs in one folder and hits uid mismatches on Linux with the non-root user. Named volume by default; see the R9 override. |
| Pinning the base image by digest | It adds reproducibility, but security updates then need manual bumps. `python:3.12-slim` is a reasonable teaching default. |

---

## 4. Risks and design concerns

| # | Risk | Impact | Mitigation in this plan / follow-up |
|---|---|---|---|
| R1 | **Non-atomic file handoffs (pre-existing).** Readers glob final filenames while writers are still writing, so preprocess or the dashboard can read a half-written CSV, and infer a half-written checkpoint. A zero-byte `orders_*.csv` makes `pd.read_csv` raise, so preprocess can crash-loop on it (a "poison file"). | Rare (measured: 1 crash in 6,461 batches at 200× the demo's poll rate). Each one is a crash that `restart: on-failure` quietly recovers, so it shows only in the restart count | **Fixed in step 6** (§3.6): writers publish via `atomic_path()`, so readers never see a partial file. The graceful stop also removes the other cause (SIGKILL mid-write). The quality log stays append-only (dashboard-only reader). Follow-up only if needed: per-file error handling in `process_new_raw_files` for files dropped in from outside the pipeline. |
| R2 | **The dashboard pins `PROJECT_ROOT`** (F3) | Empty dashboard in containers while everything else works | Fixed in §2.5, plus a loader test and a source check (§5). `/data` outside `/app` makes regressions obvious. |
| R3 | **"Data location" now has two meanings**: `base` means *project root* (→ `base/data`), while `DATA_ROOT` means *the data dir itself* | Confusion for future contributors | Precedence documented in the `data_root()` docstring and pinned by `test_explicit_base_wins_over_env`. Renaming `base` would break the tested API, so it isn't renamed. |
| R4 | **Container env leaking into tests** | Tests that pass on laptops and fail in the image, or the reverse | Autouse fixture (§3.4); shown to be necessary. |
| R5 | **Health semantics** | People expect Compose to restart "unhealthy" containers; it won't | Stated in the README and in the smoke test; Kubernetes probes are the real consumer. |
| R6 | **Unbounded growth.** Train, infer and the dashboard re-read *every* CSV on every poll. Measured: 1,800 feature files (~1 h at a 2 s poll) take ~1.6 s per full read. | Loops slow down over long sessions; the volume grows | Heartbeat limit ≥ 30 s leaves headroom for hours. Use `make docker-clean` between sessions. Incremental reads are out of scope. |
| R7 | **Unpinned dependencies** (F7) | A rebuild next month may resolve different majors | `make docker-test` must pass before merging. Lock file is a follow-up. |
| R8 | **Scaling.** File markers are not multi-writer safe. | `--scale infer=2` double-scores; two `train` replicas race on `train_state.json`; two simulators duplicate events | Keep 1 replica per service (as the guide says). Claim or shard logic is a prerequisite for Kubernetes autoscaling. |
| R9 | **Non-root user versus bind mounts on Linux** | `PermissionError` if a host directory owned by another uid is mounted at `/data` | The named volume is the default (it inherits `app:app` from the image). For a bind mount on Linux, `chown 10001` the directory or add `user: "<your uid>:<gid>"`. Docker Desktop on macOS maps ownership for you. |
| R10 | **Image size and first build** | ~0.8 GB; the first build takes a few minutes and needs network access | One shared image, with a dependency layer that stays cached across code edits. |
| R11 | **Port clash with the host pipeline** | `make docker-up` fails with "port is already allocated" if `make run` is active | Documented in the smoke test: `make stop` first. The data never clashes (C7). |
| R12 | **Shared volume not writable by the non-root user** (wrong `/data` ownership in the image, or a stale root-owned volume) | All four workers crash-loop with `PermissionError` on first start; the dashboard shows zeros | §3.5: ownership rule in the Dockerfile, in-image test, smoke test starts from a fresh volume and checks ownership |
| R13 | **A hung worker ignores SIGTERM** (blocked in a system call, so it never checks the stop flag) | `docker compose stop` takes the full 10 s for that service, then SIGKILL | Expected and acceptable: health shows it as `unhealthy` first (§3.3), and the grace period is the backstop. |

---

## 5. Automated tests to add or update

**Existing 33 tests: no edits.** The frozen config test stays valid because `DATA_ROOT` lives in `paths.py`, not in `Config`. The `stage0` path tests stay valid because an explicit `base` still wins. The "train/infer don't import each other" checks still pass: both now import `pipeline.lifecycle`, which is neither.

**Test infrastructure updates**

- `pytest.ini`: register `container: Dockerfile / compose checks (skip when Docker is not installed)`.
- `tests/conftest.py`: add the autouse `_isolate_container_env` fixture (§3.4).

**New tests (26)**

| File | Marker | Tests | What they pin down |
|---|---|---|---|
| `tests/unit/test_data_root.py` | unit | 4 | Default is `<project>/data`; `DATA_ROOT` is used as-is (`raw_dir() == $DATA_ROOT/raw`); explicit `base` beats the env var; a blank value is ignored |
| `tests/unit/test_lifecycle.py` | unit | 3 | A requested `StopFlag` cuts a 5 s sleep to under 0.5 s; `run_forever` steps, writes the heartbeat and stops; no heartbeat and no error when `HEARTBEAT_DIR` is unset |
| `tests/unit/test_healthcheck.py` | unit | 4 | Worker heartbeat missing → 1, fresh → 0, 120 s old → 1; the limit scales with `POLL_INTERVAL_SECONDS=60`; an unknown stage → 2; the dashboard probe passes against a stdlib `http.server` stub and fails once it is shut down |
| `tests/integration/test_worker_lifecycle.py` | integration | 5 | Parametrized over the 4 workers: `run_loop(stop=StopAfterFirstIteration())` returns, writes `<stage>.heartbeat`, and created `raw/` under `DATA_ROOT`. **Real signal test:** start `python -m pipeline.simulator` as a subprocess (0.2 s poll), wait for its heartbeat, send SIGTERM, then assert exit code 0 within 5 s, `simulator stopped` in the output, and raw files under `DATA_ROOT`. |
| `tests/integration/test_dashboard_data_root.py` | integration | 2 | With `DATA_ROOT` pointing at fixture copies, `app.load_features()` / `load_predictions()` / `load_quality_log()` return 5 / 3 / 0 rows; `"PROJECT_ROOT" not in` the source of `app.py` (same style as the existing import checks) |
| `tests/integration/test_container_config.py` | container | 3 | Parses `docker compose --profile test config --format json` (Docker's own parser, so no PyYAML dependency). Checks: all 5 pipeline services have `DATA_ROOT=/data`, mount `dashbite-data` at `/data`, and have a health check naming their stage; the dashboard mount is read-only and published on `127.0.0.1:8501`; `tests` is in profile `test` with no volume; the Dockerfile contains `PYTHONUNBUFFERED=1`, `DATA_ROOT=/data`, `HEARTBEAT_DIR=` and `USER app`. Skips when there is no Docker CLI or Compose plugin, or no `compose.yaml` (inside the image). |
| `tests/integration/test_stuck_worker.py` | integration | 1 | **A worker that is alive but stuck is reported unhealthy.** Start `python -m pipeline.preprocess` as a subprocess with a temporary `DATA_ROOT` and `HEARTBEAT_DIR`, `POLL_INTERVAL_SECONDS=0.1` and `HEARTBEAT_MAX_AGE_SECONDS=1`. Wait for the heartbeat and assert the probe exits 0. Then create a FIFO named `orders_stuck.csv` in `raw/`: with no writer, the worker's `read_csv` blocks in `open()` forever, a real I/O hang with no test hooks in production code. After ~2.5 s, assert the process is still running and `python -m pipeline.healthcheck preprocess` exits 1. Always `kill()` the child in a `finally`: SIGTERM can't stop it (§3.3). About 3 s. |
| `tests/unit/test_atomic_path.py` | unit | 2 | Inside the `with` block the final file doesn't exist and the reader's glob (`orders_*.csv`) finds nothing; after it, the file has the full content and is the only file in the folder. If the block raises, nothing is published and no temp file is left. |
| `tests/integration/test_no_temp_leftovers.py` | integration | 1 | One full cycle on a temporary data tree (3 simulator ticks → preprocess → train with a low threshold → infer) produces its normal outputs and leaves no `.*.tmp` files anywhere under the data root. |
| `tests/integration/test_image_data_dir.py` | container | 1 | Runs only inside the image (skips unless the project root is `/app` and `/data` exists): `/data` is owned by the current uid and writable. This is the directory Docker copies into a fresh volume (§3.5). |

Implementation notes:

- The subprocess test must set `cwd=PROJECT_ROOT` rather than overriding `PYTHONPATH`. Overriding it drops the interpreter's own entries and broke the test inside the image.
- On failure, the test should `kill()` the child and include its output in the assertion message.

**Expected counts**

| Where | Result |
|---|---|
| Host with Docker CLI (`make test`) | **58 passed, 1 skipped** (~6 s, up from 1.4 s) |
| Host without Docker | **56 passed, 3 skipped** (the Dockerfile text check needs no Docker, so it still runs) |
| Inside the image (`make docker-test`) | **56 passed, 3 skipped** |

**Deliberately not automated:**

- A full `compose up` end-to-end run: it builds a 0.8 GB image, which is too slow for the default gate. That's what the manual smoke test in §7 is for. It could become an opt-in `make docker-e2e` later.
- A Streamlit `AppTest` render of `app.py`: I tried it, and it times out because the page's auto-refresh (`sleep(2)` + `st.rerun()`) never finishes a run. This is consistent with the repo's rule of testing the helpers, not the UI.

---

## 6. Suggested implementation order

Each step is one small commit that keeps `make test` green:

1. `Add DATA_ROOT override` — `paths.py`, `app.py`, conftest fixture, `test_data_root.py`, `test_dashboard_data_root.py`
2. `Handle SIGTERM in workers` — `lifecycle.py`, the four `run_loop`/`main` changes, `test_lifecycle.py`, `test_worker_lifecycle.py`
3. `Add health probe` — `healthcheck.py`, `test_healthcheck.py`, `test_stuck_worker.py`
4. `Add Docker and compose` — `Dockerfile`, `.dockerignore`, `compose.yaml`, Makefile targets, `pytest.ini` marker, `test_container_config.py`, `test_image_data_dir.py`
5. `Document Docker workflow` — README "Run with Docker" section plus rows for `DATA_ROOT`, `HEARTBEAT_DIR` and `HEARTBEAT_MAX_AGE_SECONDS` in the config table; update the checklist in `docker-k8s-guide.md`
6. `Write handoff files atomically` — `atomic_path()` in `paths.py`, the six call sites, `.*.tmp` cleanup in `clean-data`, `test_atomic_path.py`, `test_no_temp_leftovers.py`. Independent of steps 1–5; can be reviewed or reverted on its own.

---

## 7. Manual smoke test

Run from the repo root with Docker Desktop or Docker Engine running. Commands are for bash or zsh. Times are from the prototype and are approximate.

**Step 0 — Pre-flight**

```bash
docker compose version     # must be Compose v2 ("docker compose", not "docker-compose")
make stop                  # make sure no host pipeline is holding port 8501
make test                  # host gate: 58 passed, 1 skipped (56 passed, 3 skipped without the Docker CLI)
```

**Step 1 — Test the image itself**

```bash
make docker-test           # first run builds the image (~0.8 GB, a few minutes)
```

Watch for: `56 passed, 3 skipped`. The three skips are the compose and Dockerfile checks, which can't run inside the image. A failure in `test_image_data_dir.py` means the image's `/data` is not owned by `app`; stop here and fix the Dockerfile (§3.5).

**Step 2 — Start on a fresh volume and check it is writable**

```bash
make docker-clean          # make sure the volume does not exist yet, so first creation is tested
make docker-up
docker volume ls | grep dashbite                                  # dashbite_dashbite-data, just created
docker compose exec simulator id                                  # uid=10001(app) gid=10001(app)
docker compose exec simulator stat -c '%U:%G %a' /data            # app:app 755
docker compose exec simulator ls /data                            # features  models  predictions  quality  raw
make docker-ps             # repeat until all five say (healthy), about 20–30 s
```

`make docker-clean` deletes any data from earlier runs; that is intended here.

Watch for:

- **The ownership line must say `app:app`.** `root:root` means the volume was not initialised from the image (§3.5).
- **The five subdirectories exist,** which proves the workers could `mkdir` inside `/data`.
- **Permission failure signature:** all four workers show `Restarting (1)` within seconds while the dashboard is `healthy`, and `make docker-logs SERVICE=simulator` ends in `PermissionError: [Errno 13] Permission denied: '/data/raw'`. Fix the Dockerfile, then run `make docker-clean` before `make docker-up`; rebuilding alone won't repair a volume that already holds files.

- STATUS goes from `Up … (health: starting)` to `Up … (healthy)` for `simulator`, `preprocess`, `train`, `infer` and `dashboard`.
- The dashboard row shows `127.0.0.1:8501->8501/tcp`. The workers' `8501/tcp` is just the image's `EXPOSE` and is harmless.
- `Restarting (1)` on any row means a crash loop. Check it with `make docker-logs SERVICE=<name>`.

**Step 3 — Watch data flow**

```bash
make docker-logs           # all services; Ctrl-C stops following, containers keep running
make docker-logs SERVICE=infer
```

In order, you should see:

1. `new orders arrived (20 orders) -> orders_….csv` every ~2 s; about 1 in 4 is tagged `[corrupted]`.
2. `preprocessed … (N/20 rows kept, drop_rate=…)`, with a non-zero drop rate on corrupted batches.
3. `trained checkpoint checkpoint_… (accuracy=…, labeled=…)` within ~10 s, then again after every ~50 new labeled rows.
4. From infer: `no checkpoint available yet — waiting` (once, only if it starts before the first checkpoint), then `using checkpoint …` and `scored N orders with …`.

**Step 4 — Dashboard**

```bash
curl -fsS http://localhost:8501/_stcore/health; echo    # prints: ok
open http://localhost:8501                               # macOS (Linux: xdg-open, or paste into a browser)
```

Watch for:

- **Model Pulse:** "Sample volume" and "Batches processed" climb every ~2 s. The field-level failures chart is populated. "Score distribution" appears after the first checkpoint.
- **Ops Control:** "Late rate" settles to a stable percentage; "Orders at risk (value)" is above $0 once predictions exist.
- **A dashboard stuck at zero while the logs show activity** means `DATA_ROOT` wiring is broken (R2).

**Step 5 — Data lives in the volume, not in `./data`**

```bash
docker compose exec infer ls /data                 # features  models  predictions  quality  raw
docker compose exec infer ls /data/models | tail -3
ls data/raw                                        # host folder stays empty (only .gitkeep)
docker compose exec dashboard touch /data/x        # expect: Read-only file system
```

**Step 6 — Graceful shutdown of one worker**

```bash
time docker compose stop simulator         # ~0.5–1 s (the baseline code takes ~10 s)
docker compose ps -a simulator             # Exited (0)  (the baseline code gives Exited (137))
docker compose logs --tail=2 simulator     # last line: simulator stopped
docker compose start simulator
```

**Step 7 (optional) — Watch a health check catch a stuck worker**

Two ways to make a worker stuck but still running. Either one shows `(unhealthy)` after ~50–60 s (§3.3).

*a) Freeze it* (simplest, fully reversible):

```bash
docker compose kill -s SIGSTOP train       # freezes the loop; Compose prints "Killed" but the container keeps running
make docker-ps                             # after ~60 s: train shows (unhealthy)
docker inspect --format '{{json .State.Health.Log}}' dashbite-train-1 | tail -c 300
                                           # "... train heartbeat 57.3s old (limit 30s)"
docker compose kill -s SIGCONT train       # resume; back to (healthy) within ~10 s
```

*b) Hang it in I/O,* like a real stuck read. Preprocess blocks forever opening a FIFO that has no writer:

```bash
docker compose exec preprocess python -c "import os; os.mkfifo('/data/raw/orders_stuck.csv')"
docker compose exec preprocess python -m pipeline.healthcheck preprocess   # a direct probe; exit 1 after >30 s
make docker-ps                                                             # preprocess (unhealthy) after ~60 s
docker compose exec preprocess rm /data/raw/orders_stuck.csv
docker compose restart preprocess          # takes ~10 s: SIGTERM can't interrupt the blocked open(), so Docker SIGKILLs it
```

Remove the FIFO *before* restarting. Otherwise the restarted worker opens it again and hangs again.

Watch for, in both cases:

- **The process never exits,** so there's no `Restarting`. The health status is the only signal.
- **The recorded reason** (the `.State.Health.Log` line) names the stage, the heartbeat's age and the limit.
- **Compose only reports unhealthy;** it doesn't restart the container (R5).

**Step 8 — Stop and clean up**

```bash
make docker-down                   # stops and removes containers (~1 s); the volume is kept
make docker-up                     # optional: counts continue where they left off
make docker-clean                  # also deletes the volume, for a fresh start
docker compose ps -a               # empty
docker volume ls | grep dashbite   # nothing after docker-clean
```

**Troubleshooting**

| Symptom | Cause and fix |
|---|---|
| `port is already allocated` | The host pipeline or another app is on 8501. Run `make stop`. |
| No log lines at all | The image was built without `PYTHONUNBUFFERED=1`. Rebuild with `make docker-build`. |
| Change a knob | `make docker-up TRAIN_EVERY_N_EVENTS=200` recreates the containers with the new value. |
| Services slow or turning unhealthy after hours | Growing re-reads (R6). Run `make docker-clean`, then `make docker-up`. |

---

## 8. Acceptance checklist

- [ ] `make test` on the host: 58 passed, 1 skipped; the 33 original tests are unmodified
- [ ] `make docker-test`: 56 passed, 3 skipped, including the `/data` ownership and stuck-worker tests
- [ ] After a run, no `.*.tmp` files remain in the volume: `docker compose exec infer find /data -name '.*.tmp'` prints nothing
- [ ] A worker frozen with SIGSTOP shows `(unhealthy)` within ~60 s and returns to `(healthy)` after SIGCONT (smoke test Step 7)
- [ ] After `make docker-clean && make docker-up`, `/data` in the new volume is `app:app` and no worker restarts
- [ ] `make docker-up`: all five services `(healthy)` within 60 s; the dashboard shows growing numbers
- [ ] `docker compose stop <worker>`: under 2 s, `Exited (0)`, log ends with `<stage> stopped`
- [ ] `make docker-clean` leaves no containers and no `dashbite_dashbite-data` volume
- [ ] `make run` / `make stop` / `make clean-data` behave as before on the host
- [ ] README documents the `docker-*` targets and `DATA_ROOT`

---

## Appendix A — How this plan was checked

Before writing this plan, I tried the design in a throwaway copy of the repository to confirm it was feasible. The repository was not modified. That prototype is not part of the plan or a reference for the Builder; the measurements below are what the Builder's implementation should reproduce (§8).

**Measured**

| Check | Result |
|---|---|
| Host suite | 58 passed, 1 skipped, 6.2 s |
| In-image suite (non-root) | 56 passed, 3 skipped |
| All five services | `healthy` |
| Dashboard health | `/_stcore/health` → 200 `ok` |
| Dashboard data wiring | Loaders read 954 rows from `/data` |
| Dashboard mount | Read-only (write fails with EROFS) |
| Volume ownership | Owned by uid 10001 |
| Makefile knobs | Reached the containers |
| Stop time | 10.1 s / exit 137 (baseline code) → 0.5 s / exit 0 |
| SIGSTOP hang | `unhealthy` after ~60 s, `healthy` ~10 s after SIGCONT |
| Data persistence | Survived `docker-down` → `docker-up` |
| Cleanup | `docker-clean` removed the volume |
| Volume ownership cases | Fresh volume over app-owned `/data` → writable; no `/data` in image → root-owned, `PermissionError`; non-empty root-owned volume reused → `PermissionError` |
| Ownership test | Fails on an image whose `/data` is root-owned |
| Partial-file race (host, 90 s at 200× poll rate) | Original code: 1 `EmptyDataError` crash in 6,461 batches. With `atomic_path()`: 0 in 6,351, and no temp files left. 500-row batches: 0 truncated reads in 2,510 (original). |
| Stuck worker (host, 2 s limit) | SIGSTOP: probe exit 0 → 1 after 3 s → 0 after SIGCONT. FIFO hang: process alive in `open()`, probe exit 1, SIGTERM ignored. Automated test passes in ~3 s on host and in the image. |

**Not verified**

- **The base image.** The sandbox's network policy blocks Docker Hub, so the prototype image was built on a locally assembled Python 3.12 base with the same packages, not on `python:3.12-slim`.
- **The steps that depend on it:** installing requirements and creating the `app` user and its `/data` directory were not executed on `python:3.12-slim`. In the prototype, `/data` was app-owned because the base image already contained it that way, so **the prototype does not show that the Builder's Dockerfile gets ownership right.** That is why the in-image ownership test and the fresh-volume smoke step exist; the first `make docker-test` on a real machine is where it is proven.
- **One prototype-only workaround.** Streamlit's development-mode detection misfires when packages are installed outside `site-packages`; the prototype needed `STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false` for that reason. A normal `pip install` in the real image doesn't hit this, so the setting is not part of the plan.
