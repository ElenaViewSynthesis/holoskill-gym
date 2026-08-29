# Terminal-Bench 2.0 task list

All **89** tasks in `terminal-bench@2.0`, read from
[laude-institute/terminal-bench-2](https://github.com/laude-institute/terminal-bench-2)
at the commit the Harbor registry pins (`69671fba`).

Harbor is the official harness for Terminal-Bench 2.0, so this dataset needs no
adapter — it runs directly:

```bash
harbor run --dataset terminal-bench@2.0 -a oracle -y            # credential-free
harbor run --dataset terminal-bench@2.0 \
  --agent codex --model gpt-5.6-sol --n-concurrent 1            # spends OPENAI_API_KEY
```

## Difficulty distribution

| Difficulty | Tasks |
|---|---:|
| easy | 4 |
| medium | 55 |
| hard | 30 |
| **total** | **89** |

GPU-requiring tasks: **0** — none.

Unlike AlgoTune, which is uniformly `medium`, Terminal-Bench 2.0 has a real
difficulty gradient. That matters for this project: a task set with no spread
cannot show whether a skill helps more on hard problems than easy ones.

## Tasks

| # | Task | Difficulty | Agent timeout (s) | Tags |
|---:|---|---|---:|---|
| 1 | `cobol-modernization` | easy | 900.0 | coding |
| 2 | `fix-git` | easy | 900.0 | coding, version-control |
| 3 | `overfull-hbox` | easy | 750.0 | latex, document-processing, combinatorial-optimization |
| 4 | `prove-plus-comm` | easy | 900.0 | coding |
| 5 | `adaptive-rejection-sampler` | medium | 900.0 | applied-statistics, adaptive-rejection-sampling, Bayesian-in |
| 6 | `break-filter-js-from-html` | medium | 1200.0 | security |
| 7 | `build-cython-ext` | medium | 900.0 | coding, dependency, compilation |
| 8 | `build-pmars` | medium | 900.0 | build-tools, compilation, debian, gaming, pmars, corewars |
| 9 | `build-pov-ray` | medium | 12000.0 | build-tools, compilation, graphics, ray-tracing, legacy-soft |
| 10 | `caffe-cifar-10` | medium | 1200.0 | cnn, caffe |
| 11 | `chess-best-move` | medium | 900.0 | - |
| 12 | `code-from-image` | medium | 1200.0 | ocr |
| 13 | `compile-compcert` | medium | 2400.0 | compilation, compilers |
| 14 | `constraints-scheduling` | medium | 1200.0 | calendar, scheduling, constraint-satisfaction, ics-parsing,  |
| 15 | `count-dataset-tokens` | medium | 900.0 | machine-learning, data, datasets, tokenization, huggingface |
| 16 | `crack-7z-hash` | medium | 1800.0 | decrypt, security, file-operations |
| 17 | `custom-memory-heap-crash` | medium | 1800.0 | cpp, memory-management, debugging |
| 18 | `db-wal-recovery` | medium | 900.0 | database, encryption, recovery |
| 19 | `distribution-search` | medium | 3600.0 | coding, statistics, machine-learning |
| 20 | `dna-insert` | medium | 1800.0 | biology, cloning |
| 21 | `extract-elf` | medium | 900.0 | - |
| 22 | `filter-js-from-html` | medium | 1800.0 | security |
| 23 | `financial-document-processor` | medium | 1200.0 | ocr, image-processing, financial, file-operations |
| 24 | `gcode-to-text` | medium | 900.0 | file-operations |
| 25 | `git-leak-recovery` | medium | 900.0 | git, security |
| 26 | `git-multibranch` | medium | 900.0 | system, version-control, web |
| 27 | `headless-terminal` | medium | 900.0 | bash, terminal |
| 28 | `hf-model-inference` | medium | 900.0 | api, coding, data-processing, data-science |
| 29 | `kv-store-grpc` | medium | 900.0 | coding, file-operations, system |
| 30 | `large-scale-text-editing` | medium | 1200.0 | text-editing, large-scale-text-manipulation, vim, vim-macros |
| 31 | `largest-eigenval` | medium | 900.0 | coding, optimization, constraint, numerical-approximation |
| 32 | `log-summary-date-ranges` | medium | 900.0 | log-analysis, report-generation, data-processing |
| 33 | `mailman` | medium | 1800.0 | email-server, mailing-list |
| 34 | `merge-diff-arc-agi-task` | medium | 900.0 | git, coding |
| 35 | `modernize-scientific-stack` | medium | 600.0 | python-migration, scientific-computing, legacy-modernization |
| 36 | `mteb-leaderboard` | medium | 3600.0 | retrieval, mteb |
| 37 | `mteb-retrieve` | medium | 1800.0 | data-processing, data-science, mteb |
| 38 | `multi-source-data-merger` | medium | 900.0 | data-processing, etl, schema-mapping, conflict-resolution, p |
| 39 | `nginx-request-logging` | medium | 900.0 | web-server |
| 40 | `openssl-selfsigned-cert` | medium | 900.0 | coding, file-operations, security, system |
| 41 | `polyglot-c-py` | medium | 900.0 | coding |
| 42 | `portfolio-optimization` | medium | 3600.0 | c-programming, python-extension, optimization |
| 43 | `pypi-server` | medium | 900.0 | coding, system |
| 44 | `pytorch-model-cli` | medium | 900.0 | coding, C, pytorch |
| 45 | `pytorch-model-recovery` | medium | 900.0 | coding, pytorch, machine-learning |
| 46 | `qemu-alpine-ssh` | medium | 900.0 | sys-admin |
| 47 | `qemu-startup` | medium | 900.0 | sys-admin |
| 48 | `query-optimize` | medium | 900.0 | query-optimization, sql-query |
| 49 | `raman-fitting` | medium | 900.0 | coding, fitting, analysis, physics |
| 50 | `regex-log` | medium | 900.0 | regex, string-parsing, log-analysis |
| 51 | `reshard-c4-data` | medium | 3600.0 | coding, data-processing, file-operations |
| 52 | `rstan-to-pystan` | medium | 1800.0 | pystan, rstan, gaussian-process |
| 53 | `sanitize-git-repo` | medium | 900.0 | security, system, version-control |
| 54 | `schemelike-metacircular-eval` | medium | 2400.0 | software-engineering |
| 55 | `sqlite-db-truncate` | medium | 900.0 | file-operations |
| 56 | `sqlite-with-gcov` | medium | 900.0 | software-installation, system |
| 57 | `tune-mjcf` | medium | 900.0 | mujoco, physics, simulation, numerical-optimization |
| 58 | `vulnerable-secret` | medium | 900.0 | security, file-operations |
| 59 | `winning-avg-corewars` | medium | 3600.0 | pmars, corewars, gaming |
| 60 | `bn-fit-modify` | hard | 3600.0 | bayesian-network, stats |
| 61 | `cancel-async-tasks` | hard | 900.0 | async, concurrency, python |
| 62 | `circuit-fibsqrt` | hard | 3600.0 | software-engineering |
| 63 | `configure-git-webserver` | hard | 900.0 | system, version-control, web |
| 64 | `dna-assembly` | hard | 1800.0 | biology, cloning |
| 65 | `extract-moves-from-video` | hard | 1800.0 | file-operations, web, video-processing |
| 66 | `feal-differential-cryptanalysis` | hard | 1800.0 | software-engineering |
| 67 | `feal-linear-cryptanalysis` | hard | 1800.0 | software-engineering |
| 68 | `fix-code-vulnerability` | hard | 900.0 | security, code-vulnerability, common-weakness-enumeration |
| 69 | `fix-ocaml-gc` | hard | 3600.0 | troubleshooting |
| 70 | `gpt2-codegolf` | hard | 900.0 | - |
| 71 | `install-windows-3.11` | hard | 3600.0 | virtualization, qemu, windows-3.11, vnc, sys-admin, retro-co |
| 72 | `llm-inference-batching-scheduler` | hard | 1800.0 | batching, inference, performance-optimization, scheduling |
| 73 | `make-doom-for-mips` | hard | 900.0 | software-engineering |
| 74 | `make-mips-interpreter` | hard | 1800.0 | software-engineering |
| 75 | `mcmc-sampling-stan` | hard | 1800.0 | R, stan, bayesian-statistics, mcmc |
| 76 | `model-extraction-relu-logits` | hard | 900.0 | security |
| 77 | `password-recovery` | hard | 900.0 | system, file-operations, troubleshooting |
| 78 | `path-tracing` | hard | 1800.0 | images |
| 79 | `path-tracing-reverse` | hard | 1800.0 | images |
| 80 | `polyglot-rust-c` | hard | 900.0 | coding, no-verified-solution |
| 81 | `protein-assembly` | hard | 1800.0 | biology, cloning, proteins |
| 82 | `regex-chess` | hard | 3600.0 | software-engineering |
| 83 | `sam-cell-seg` | hard | 7200.0 | image-processing, machine-learning, histopathology |
| 84 | `sparql-university` | hard | 900.0 | knowledge-graph, sparql-query, information-retrieval |
| 85 | `torch-pipeline-parallelism` | hard | 900.0 | system |
| 86 | `torch-tensor-parallelism` | hard | 900.0 | system |
| 87 | `train-fasttext` | hard | 3600.0 | data-processing, data-science |
| 88 | `video-processing` | hard | 3600.0 | video-processing |
| 89 | `write-compressor` | hard | 900.0 | coding |

## Suitability for this project

Terminal-Bench 2.0 is a **general agent benchmark**, not a code-optimization
one. Its tasks are pass/fail against their own verifiers, so they carry no
before/after benchmark measurement and cannot produce a `speedup`. This
project's reward — correctness-gated speedup — has nothing to compute from
them, and neither `correct_speedup_geomean` nor `algotune_score` is defined.

That makes it useful here for one thing rather than as a task source: it is a
**broad harness smoke test**. Running a handful under `-a oracle` exercises
Harbor's image build, network policy and verifier plumbing across far more
varied environments than the five synthetic canaries do. Use it to shake out
infrastructure, not to score a skill.

