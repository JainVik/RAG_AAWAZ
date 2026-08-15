# Google Colab Free offline-data workflow

This workflow covers bounded MSMARCO-XI profiling, deterministic corpus creation, and an optional
initial Qdrant index build. It does not run the voice API or the final latency benchmark in Colab.
The commands stream pinned Parquet files and keep restartable artifacts in Google Drive, so they do
not require downloading the full dataset or holding the corpus in RAM.

## 1. Start a CPU runtime and mount Drive

Use a standard Colab CPU runtime. Clone or upload this repository, then run:

```python
from google.colab import drive
drive.mount("/content/drive")
```

```bash
%cd /content/RAG/backend
!python -m pip install -e '.[data,embeddings]'
```

Drive is optional for a short profiler smoke, but required for a build that must survive an
ephemeral runtime. Use a project-specific directory:

```python
from pathlib import Path

DRIVE_ROOT = Path("/content/drive/MyDrive/awaaz-tiderag")
DRIVE_ROOT.mkdir(parents=True, exist_ok=True)
```

## 2. Run a bounded streaming audit

Begin with one pinned Hindi validation stream and one row. A cold first row can take several
minutes because the upstream file has a large physical row group.

```bash
!PYTHONUNBUFFERED=1 python scripts/inspect_dataset.py \
  --languages hi --splits validation --max-rows 1 --batch-size 2 \
  --json-output /content/drive/MyDrive/awaaz-tiderag/audit-smoke.json \
  --markdown-output /content/drive/MyDrive/awaaz-tiderag/audit-smoke.md
```

After the smoke succeeds, increase `--max-rows` and add languages. The report includes schema and
null checks, source/target pairs, query and passage distributions, duplicates, selected-label
rates, and explicitly heuristic 10k/25k/50k/100k resource estimates.

## 3. Build a deterministic restartable corpus

Use a separate output directory for every size. The bounded shuffle buffer avoids a first-N
sample; the manifest records the seed, target, overshoot, provenance, counts, and checksums.

```bash
!PYTHONUNBUFFERED=1 python scripts/build_corpus.py \
  --language hi --split validation --target-unique-passages 10000 \
  --seed 2026 --shuffle-buffer-size 10000 --batch-size 64 \
  --output-dir /content/drive/MyDrive/awaaz-tiderag/corpus-10k
```

If Colab disconnects, run the identical command again. It resumes from the checkpoint. Do not use
`--no-resume` unless intentionally starting a new build. Copy completed artifacts out of Drive only
as a full set: `corpus.jsonl`, `evaluation-fixtures.jsonl`, and `corpus-manifest.json`.

## 4. Optional initial Qdrant index build

`build_index.py` writes restartable chunk and sparse artifacts to `RAG_DATA_DIR/index` and upserts
the dense/sparse vectors into Qdrant. Colab does not provide Docker, so use a dedicated hosted
Qdrant collection for this optional step. Enter secrets interactively; never place them in a
notebook cell or commit them.

```python
import getpass
import os

os.environ["QDRANT_URL"] = input("Hosted Qdrant URL: ").strip()
os.environ["QDRANT_API_KEY"] = getpass.getpass("Qdrant API key: ")
os.environ["QDRANT_COLLECTION"] = "awaaz_corpus_10k_colab"
os.environ["RAG_DATA_DIR"] = "/content/drive/MyDrive/awaaz-tiderag/index-10k-data"
```

```bash
!huggingface-cli download intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
!PYTHONUNBUFFERED=1 python scripts/build_index.py \
  --corpus /content/drive/MyDrive/awaaz-tiderag/corpus-10k/corpus.jsonl \
  --corpus-manifest /content/drive/MyDrive/awaaz-tiderag/corpus-10k/corpus-manifest.json \
  --output-dir /content/drive/MyDrive/awaaz-tiderag/index-10k-data/index \
  --batch-size 64
```

Re-run the same command after interruption; deterministic IDs and the checkpoint make completed
batches idempotent. The hosted service must have enough quota for all produced vectors. A local
Windows/Linux build with the pinned Compose Qdrant remains the recommended final-index workflow.

## 5. Scale only from measured evidence

Repeat the corpus/index/evaluation workflow with distinct output directories and Qdrant collection
names. Use the same final held-out fixture, model revision, runtime contract, deadline, cache policy,
and concurrency. Then compare at least two retrieval reports:

```bash
!python scripts/compare_corpus_sizes.py \
  evaluation/reports/final/retrieval-10k.json \
  evaluation/reports/final/retrieval-25k.json \
  --minimum-recall-gain 0.01 \
  --output-prefix evaluation/reports/final/corpus-scaling-comparison
```

The comparator fails on incompatible fixtures/runtime contracts and marks its recommendation
provisional unless every source run is qualifying and uses a distinct corpus manifest and Qdrant
collection. Its disk metric is the deterministic local artifact footprint; record live Qdrant disk
and resident memory separately for deployment decisions.
