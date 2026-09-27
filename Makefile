# DashBite pipeline — common teaching commands
# Usage: make help

PYTHON      ?= python3
VENV        ?= .venv
BIN         := $(VENV)/bin
PY          := $(BIN)/python
PIP         := $(BIN)/pip
PYTEST      := $(BIN)/pytest
STREAMLIT   := $(BIN)/streamlit

# Demo-friendly defaults (override on the command line)
export TRAIN_EVERY_N_EVENTS    ?= 50
export BATCH_SIZE              ?= 20
export POLL_INTERVAL_SECONDS   ?= 2.0
export CORRUPT_BATCH_RATE      ?= 0.25
export PYTHONPATH              := $(CURDIR)
# Flush print() output immediately, so .logs/*.log update live during make run
export PYTHONUNBUFFERED        := 1

# Host data directory used by clean-data (deliberately not exported).
# A blank value counts as unset, as in pipeline/paths.py; 'override' makes that
# hold for 'make clean-data DATA_ROOT=' on the command line too.
# Keep comments on their own lines: Make keeps spaces before a trailing '#'.
override DATA_ROOT := $(or $(strip $(DATA_ROOT)),$(CURDIR)/data)

# Container runtime (the docker compose plugin)
COMPOSE ?= docker compose

LOG_DIR := .logs
PIDS    := $(LOG_DIR)/pids

.PHONY: help install test test-unit test-regression test-integration \
	simulator preprocess train infer dashboard \
	run stop clean clean-data \
	docker-build docker-up docker-ps docker-logs docker-down docker-clean docker-test

help:
	@echo "DashBite Make targets"
	@echo ""
	@echo "  make install              Create .venv and install requirements"
	@echo "  make test                 Run full pytest suite (unit+regression+integration)"
	@echo "  make test-unit            Run unit tests only"
	@echo "  make test-regression      Run regression tests only"
	@echo "  make test-integration     Run integration tests only"
	@echo "  make simulator            Run order feed (foreground)"
	@echo "  make preprocess           Run preprocess loop (foreground)"
	@echo "  make train                Run training loop (foreground)"
	@echo "  make infer                Run inference loop (foreground)"
	@echo "  make dashboard            Run Streamlit on :8501 (foreground)"
	@echo "  make run                  Start all stages in background + dashboard"
	@echo "  make stop                 Stop background pipeline processes"
	@echo "  make clean-data           Remove runtime files under data/ (keep .gitkeep)"
	@echo "  make clean                clean-data + logs + pytest cache"
	@echo ""
	@echo "Docker (no local Python needed):"
	@echo "  make docker-build         Build the dashbite:local image"
	@echo "  make docker-up            Start all five services (dashboard on localhost:8501)"
	@echo "  make docker-ps            Show container status and health"
	@echo "  make docker-logs          Follow logs (SERVICE=<name> for one service)"
	@echo "  make docker-down          Stop and remove containers (keeps the data volume)"
	@echo "  make docker-clean         docker-down + delete the data volume"
	@echo "  make docker-test          Run the pytest suite inside the image"
	@echo ""
	@echo "Env defaults: TRAIN_EVERY_N_EVENTS=$(TRAIN_EVERY_N_EVENTS) BATCH_SIZE=$(BATCH_SIZE)"

install: $(VENV)/.installed

$(VENV)/.installed: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $@

test: install
	$(PYTEST)

test-unit: install
	$(PYTEST) -m unit

test-regression: install
	$(PYTEST) -m regression

test-integration: install
	$(PYTEST) -m integration

simulator: install
	$(PY) -m pipeline.simulator

preprocess: install
	$(PY) -m pipeline.preprocess

train: install
	$(PY) -m pipeline.train

infer: install
	$(PY) -m pipeline.infer

dashboard: install
	PYTHONPATH=$(CURDIR) $(STREAMLIT) run pipeline/dashboard/app.py \
		--server.headless true --server.port 8501

run: install stop
	@mkdir -p $(LOG_DIR) $(PIDS)
	@echo "Starting pipeline (logs in $(LOG_DIR)/)..."
	@nohup $(PY) -m pipeline.simulator >$(LOG_DIR)/simulator.log 2>&1 & echo $$! > $(PIDS)/simulator.pid
	@nohup $(PY) -m pipeline.preprocess >$(LOG_DIR)/preprocess.log 2>&1 & echo $$! > $(PIDS)/preprocess.pid
	@nohup $(PY) -m pipeline.train >$(LOG_DIR)/train.log 2>&1 & echo $$! > $(PIDS)/train.pid
	@nohup $(PY) -m pipeline.infer >$(LOG_DIR)/infer.log 2>&1 & echo $$! > $(PIDS)/infer.pid
	@nohup env PYTHONPATH=$(CURDIR) $(STREAMLIT) run pipeline/dashboard/app.py \
		--server.headless true --server.port 8501 >$(LOG_DIR)/dashboard.log 2>&1 & echo $$! > $(PIDS)/dashboard.pid
	@echo "Dashboard: http://localhost:8501"
	@echo "Stop with: make stop"

stop:
	@if [ -d "$(PIDS)" ]; then \
		for f in $(PIDS)/*.pid; do \
			[ -f "$$f" ] || continue; \
			pid=$$(cat "$$f"); \
			kill $$pid 2>/dev/null || true; \
			rm -f "$$f"; \
		done; \
	fi
	@pkill -f "python -m pipeline.simulator" 2>/dev/null || true
	@pkill -f "python -m pipeline.preprocess" 2>/dev/null || true
	@pkill -f "python -m pipeline.train" 2>/dev/null || true
	@pkill -f "python -m pipeline.infer" 2>/dev/null || true
	@pkill -f "streamlit run pipeline/dashboard/app.py" 2>/dev/null || true
	@echo "Pipeline stopped."

clean-data:
	@rm -f "$(DATA_ROOT)"/raw/*.csv \
		"$(DATA_ROOT)"/features/features_*.csv "$(DATA_ROOT)"/features/.done_* \
		"$(DATA_ROOT)"/models/checkpoint_*.joblib "$(DATA_ROOT)"/models/metrics_*.json "$(DATA_ROOT)"/models/train_state.json \
		"$(DATA_ROOT)"/predictions/predictions_*.csv \
		"$(DATA_ROOT)"/quality/*.csv \
		"$(DATA_ROOT)"/raw/.*.tmp "$(DATA_ROOT)"/features/.*.tmp "$(DATA_ROOT)"/models/.*.tmp \
		"$(DATA_ROOT)"/predictions/.*.tmp "$(DATA_ROOT)"/quality/.*.tmp
	@echo "Runtime data cleared."

clean: clean-data
	@rm -rf $(LOG_DIR) .pytest_cache
	@find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."

# --- Docker -------------------------------------------------------------------
# None of these depend on install: a machine with only Docker can use them.

docker-build:
	$(COMPOSE) build

docker-up:
	$(COMPOSE) up -d --build
	@echo "Dashboard: http://localhost:8501"
	@echo "Status: make docker-ps    Logs: make docker-logs    Stop: make docker-down"

docker-ps:
	$(COMPOSE) ps

docker-logs:
	$(COMPOSE) logs -f --tail=50 $(SERVICE)

docker-down:
	$(COMPOSE) down

docker-clean:
	$(COMPOSE) down -v --remove-orphans

docker-test:
	$(COMPOSE) build tests
	$(COMPOSE) run --rm tests
