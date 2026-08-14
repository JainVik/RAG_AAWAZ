PYTHON ?= python
BACKEND := backend
E5_MODEL := intfloat/multilingual-e5-small
E5_REVISION := 614241f622f53c4eeff9890bdc4f31cfecc418b3
SARVAM_PCM ?= evaluation/fixtures/sarvam-smoke.pcm
VOICE_FIXTURE ?= evaluation/private/voice-latency.jsonl
COLD_LATENCY_PREFIX ?= evaluation/reports/final/latency-cold
FINAL_LATENCY_PREFIX ?= evaluation/reports/final/latency-warm
LATENCY_DEADLINE_MS ?= 200
CORPUS_LANGUAGE ?= hi
CORPUS_SPLIT ?= validation
CORPUS_TARGET_PASSAGES ?= 10000
PARTITION_DIR ?= data/evaluation/partition
DEVELOPMENT_SCORE_PREFIX ?= evaluation/reports/development/development-retrieval-scores
FINAL_RETRIEVAL_PREFIX ?= evaluation/reports/final/retrieval-eval

.PHONY: dev audit-data download-e5 build-corpus build-index partition-evaluation \
	score-development calibrate-thresholds check test lint typecheck \
	sarvam-smoke eval-retrieval eval-guardrails eval-guardrails-smoke ablation \
	benchmark benchmark-text-smoke benchmark-cold benchmark-final

dev:
	cd $(BACKEND) && $(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

audit-data:
	cd $(BACKEND) && $(PYTHON) scripts/inspect_dataset.py --max-rows 500

download-e5:
	cd $(BACKEND) && hf download $(E5_MODEL) --revision $(E5_REVISION)

build-corpus:
	cd $(BACKEND) && $(PYTHON) scripts/build_corpus.py --language $(CORPUS_LANGUAGE) --split $(CORPUS_SPLIT) --target-unique-passages $(CORPUS_TARGET_PASSAGES)

build-index:
	cd $(BACKEND) && $(PYTHON) scripts/build_index.py

partition-evaluation:
	cd $(BACKEND) && $(PYTHON) scripts/split_evaluation_fixture.py --fixture data/corpus/evaluation-fixtures.jsonl --corpus-manifest data/corpus/corpus-manifest.json --output-dir $(PARTITION_DIR) --final-count 500 --require-final-relevance-labels

score-development:
	cd $(BACKEND) && $(PYTHON) scripts/score_development.py --fixture $(PARTITION_DIR)/development-fixtures.jsonl --output-prefix $(DEVELOPMENT_SCORE_PREFIX)

calibrate-thresholds:
	cd $(BACKEND) && $(PYTHON) scripts/calibrate_thresholds.py --fixture $(DEVELOPMENT_SCORE_PREFIX).jsonl

check: lint typecheck test

test:
	cd $(BACKEND) && $(PYTHON) -m pytest

lint:
	cd $(BACKEND) && $(PYTHON) -m ruff check .

typecheck:
	cd $(BACKEND) && $(PYTHON) -m mypy app scripts

eval-retrieval:
	cd $(BACKEND) && $(PYTHON) scripts/run_retrieval_eval.py --fixture $(PARTITION_DIR)/final-fixtures.jsonl --corpus-manifest data/corpus/corpus-manifest.json --partition-manifest $(PARTITION_DIR)/partition-manifest.json --output-prefix $(FINAL_RETRIEVAL_PREFIX)

sarvam-smoke:
	cd $(BACKEND) && $(PYTHON) scripts/run_sarvam_smoke.py --pcm "$(SARVAM_PCM)" --output data/sarvam-smoke.json

benchmark: benchmark-final

benchmark-text-smoke:
	cd $(BACKEND) && $(PYTHON) scripts/run_latency_benchmark.py --mode text-smoke --allow-small-smoke --output-prefix evaluation/reports/development/latency-text-smoke

benchmark-cold:
	cd $(BACKEND) && $(PYTHON) scripts/run_latency_benchmark.py --mode voice --fixture "$(VOICE_FIXTURE)" --startup-condition cold --warmup 0 --limit 1 --deadline-ms $(LATENCY_DEADLINE_MS) --chunk-ms 100 --pace-audio --cache-policy disabled --output-prefix "$(COLD_LATENCY_PREFIX)"

benchmark-final:
	cd $(BACKEND) && $(PYTHON) scripts/run_latency_benchmark.py --mode voice --fixture "$(VOICE_FIXTURE)" --startup-condition warm --warmup 3 --limit 303 --deadline-ms $(LATENCY_DEADLINE_MS) --chunk-ms 100 --pace-audio --cache-policy disabled --cold-start-report "$(COLD_LATENCY_PREFIX).json" --output-prefix "$(FINAL_LATENCY_PREFIX)"

eval-guardrails:
	cd $(BACKEND) && $(PYTHON) scripts/run_guardrail_eval.py

eval-guardrails-smoke:
	cd $(BACKEND) && $(PYTHON) scripts/run_guardrail_eval.py --offline-deterministic-smoke --output-prefix evaluation/reports/development/guardrail-smoke

ablation:
	cd $(BACKEND) && $(PYTHON) scripts/run_ablation.py
