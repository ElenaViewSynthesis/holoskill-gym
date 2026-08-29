# Harbor registry datasets

The 80 datasets in `reference/seagym/reference/harbor/registry.json` at the
pinned Harbor revision. Address one as `name@version`:

```bash
harbor run --dataset algotune@1.0 -a oracle -y
```

Task counts are registry entries, not necessarily what a single run costs --
several of these are very large and must be sampled rather than run whole.

| Dataset | Version | Tasks |
|---|---|---:|
| `ade-bench` | `1.0` | 48 |
| `aider-polyglot` | `1.0` | 225 |
| `aime` | `1.0` | 60 |
| `algotune` | `1.0` | 154 |
| `arc_agi_2` | `1.0` | 167 |
| `autocodebench` | `lite200` | 200 |
| `bfcl` | `1.0` | 3,641 |
| `bfcl_parity` | `1.0` | 123 |
| `bigcodebench-hard-complete` | `1.0.0` | 145 |
| `binary-audit` | `1.0` | 46 |
| `bird-bench` | `parity` | 150 |
| `bixbench` | `1.5` | 205 |
| `bixbench-cli` | `1.5` | 205 |
| `code-contests` | `1.0` | 9,644 |
| `codepde` | `1.0` | 5 |
| `compilebench` | `1.0` | 15 |
| `cooperbench` | `1.0` | 652 |
| `crustbench` | `1.0` | 100 |
| `dabstep` | `1.0` | 450 |
| `deveval` | `1.0` | 63 |
| `ds-1000` | `head` | 1,000 |
| `evoeval` | `1.0` | 100 |
| `featurebench` | `1.0` | 200 |
| `featurebench-lite` | `1.0` | 30 |
| `featurebench-lite-modal` | `1.0` | 30 |
| `featurebench-modal` | `1.0` | 200 |
| `financeagent` | `public` | 50 |
| `gaia` | `1.0` | 165 |
| `gpqa-diamond` | `1.0` | 198 |
| `gso` | `1.0` | 102 |
| `hello-world` | `1.0` | 1 |
| `humanevalfix` | `1.0` | 164 |
| `ineqmath` | `1.0` | 100 |
| `kumo` | `1.0` | 5,300 |
| `kumo` | `easy` | 5,050 |
| `kumo` | `hard` | 250 |
| `kumo` | `parity` | 212 |
| `labbench` | `1.0` | 181 |
| `lawbench` | `1.0` | 1,000 |
| `legacy-bench` | `1.0` | 10 |
| `livecodebench` | `6.0` | 100 |
| `medagentbench` | `1.0` | 300 |
| `ml-dev-bench` | `1.0` | 33 |
| `mlgym-bench` | `1.0` | 12 |
| `mmau` | `1.0` | 1,000 |
| `mmmlu` | `parity` | 150 |
| `openthoughts-tblite` | `2.0` | 100 |
| `otel-bench` | `1.0` | 26 |
| `pixiu` | `parity` | 435 |
| `qcircuitbench` | `1.0` | 28 |
| `quixbugs` | `1.0` | 80 |
| `reasoning-gym-easy` | `parity` | 288 |
| `reasoning-gym-hard` | `parity` | 288 |
| `replicationbench` | `1.0` | 90 |
| `researchcodebench` | `1.0` | 212 |
| `rexbench` | `1.0` | 2 |
| `satbench` | `1.0` | 2,100 |
| `scale-ai/swe-atlas-qna` | `1.0` | 124 |
| `scale-ai/swe-atlas-tw` | `1.0` | 90 |
| `seta-env` | `1.0` | 1,376 |
| `simpleqa` | `1.0` | 4,326 |
| `sldbench` | `1.0` | 8 |
| `spider2-dbt` | `1.0` | 64 |
| `spreadsheetbench-verified` | `1.0` | 400 |
| `strongreject` | `parity` | 150 |
| `swe-gen-js` | `1.0` | 1,000 |
| `swe-lancer-diamond` | `all` | 463 |
| `swe-lancer-diamond` | `ic` | 198 |
| `swe-lancer-diamond` | `manager` | 265 |
| `swebench-verified` | `1.0` | 500 |
| `swebench_multilingual` | `1.0` | 300 |
| `swebenchpro` | `1.0` | 731 |
| `swesmith` | `1.0` | 100 |
| `swtbench-verified` | `1.0` | 433 |
| `termigen-environments` | `1.0` | 3,566 |
| `terminal-bench` | `2.0` | 89 |
| `terminal-bench-pro` | `1.0` | 200 |
| `terminal-bench-sample` | `2.0` | 10 |
| `usaco` | `2.0` | 304 |
| `vmax-tasks` | `1.0` | 1,043 |

## GPU requirements

Most entries are CPU-only. **AlgoTune needs no GPU** -- none of its 154 tasks
declares a `gpus` field. Benchmarks that do involve GPUs, and therefore need a
GPU-capable provider before they can run: `rexbench` (declares GPUs in its task
template), and `deveval`, `featurebench`, `ml-dev-bench`, `mlgym-bench`,
`researchcodebench`, `scienceagentbench` (documented in their adapter READMEs).

## Relationship to Terminal-Bench

Harbor is built by the creators of Terminal-Bench and is the official harness
for Terminal-Bench 2.0 (`terminal-bench@2.0`, 89 tasks). Many registry entries
reached Harbor through a Terminal-Bench adapter first, which is why parity is
reported in two hops: original benchmark -> Terminal-Bench adapter -> Harbor
adapter. For AlgoTune the second hop scored 1.234 +/- 0.016 against the
Terminal-Bench adapter's 1.232 +/- 0.015 over three trials on all 154 tasks.
