-- HoloSkill Gym run/metric/solution store.
--
-- Purpose: jobs/ and results/ are gitignored and Harbor rewrites them per run,
-- so a paid run's evidence is otherwise unrecoverable once the directory is
-- cleaned. This schema keeps the durable facts: what was run, what it scored,
-- what code produced the score, and the complexity claim for that code.
--
-- Complexity columns are ANNOTATIONS, not measurements. Nothing here derives a
-- bound automatically; a human or an agent records the claim and the reasoning
-- goes in complexity_notes. Treat them as documentation that can be wrong.

CREATE TABLE IF NOT EXISTS tasks (
    task_id           TEXT PRIMARY KEY,
    dataset           TEXT NOT NULL,               -- e.g. algotune@1.0
    dataset_commit    TEXT,                        -- provenance pin
    family            TEXT,                        -- bottleneck family / domain
    difficulty        TEXT,
    problem_size      BIGINT,
    declared_cpus     INTEGER,
    declared_memory   TEXT,                        -- as written in task.toml
    benchmark_trust   TEXT,                        -- synthetic_canary | external
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            BIGSERIAL PRIMARY KEY,
    job_name          TEXT NOT NULL,
    trial_name        TEXT,
    task_id           TEXT NOT NULL REFERENCES tasks(task_id),
    agent             TEXT NOT NULL,               -- oracle | codex | claude-code
    model             TEXT,                        -- null for oracle
    reasoning_effort  TEXT,
    environment       TEXT NOT NULL DEFAULT 'docker',
    paid              BOOLEAN NOT NULL DEFAULT FALSE,
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    harbor_version    TEXT,
    input_tokens      BIGINT,
    output_tokens     BIGINT,
    cost_usd          NUMERIC(12, 6),              -- null when pricing unavailable
    exception_type    TEXT,
    notes             TEXT,
    UNIQUE (job_name, trial_name)
);

CREATE TABLE IF NOT EXISTS metrics (
    metric_id         BIGSERIAL PRIMARY KEY,
    run_id            BIGINT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    name              TEXT NOT NULL,               -- reward | raw_speedup | baseline_time_s | ...
    value             DOUBLE PRECISION,
    unit              TEXT,
    valid             BOOLEAN,                     -- verifier validity, where reported
    UNIQUE (run_id, name)
);

CREATE TABLE IF NOT EXISTS solutions (
    solution_id       BIGSERIAL PRIMARY KEY,
    run_id            BIGINT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    language          TEXT NOT NULL DEFAULT 'python',
    source            TEXT NOT NULL,               -- the solver as submitted
    source_sha256     TEXT NOT NULL,
    algorithm         TEXT,                        -- e.g. 'FFT convolution (convolution theorem)'
    time_complexity   TEXT,                        -- annotation, e.g. 'O(P^2 log P)'
    space_complexity  TEXT,                        -- annotation, e.g. 'O(P^2)'
    baseline_time_complexity  TEXT,
    baseline_space_complexity TEXT,
    complexity_notes  TEXT,                        -- why the bound holds; symbol definitions
    generality_caveats TEXT,                       -- where the solution stops being correct
    UNIQUE (run_id)
);

CREATE INDEX IF NOT EXISTS metrics_name_idx ON metrics (name);
CREATE INDEX IF NOT EXISTS runs_task_idx ON runs (task_id);
CREATE INDEX IF NOT EXISTS runs_paid_idx ON runs (paid);

-- Leaderboard: best scoring run per task, with its complexity claim.
CREATE OR REPLACE VIEW solution_leaderboard AS
SELECT
    r.task_id,
    t.dataset,
    r.agent,
    r.model,
    r.paid,
    m.value       AS reward,
    s.algorithm,
    s.time_complexity,
    s.space_complexity,
    s.baseline_time_complexity,
    r.input_tokens,
    r.output_tokens,
    r.cost_usd,
    r.finished_at
FROM runs r
JOIN tasks t   ON t.task_id = r.task_id
LEFT JOIN metrics m  ON m.run_id = r.run_id AND m.name = 'reward'
LEFT JOIN solutions s ON s.run_id = r.run_id
ORDER BY r.task_id, m.value DESC NULLS LAST;

-- Agent vs oracle on the same task: the comparison that says whether the agent
-- beat the reference implementation, and by how much.
CREATE OR REPLACE VIEW agent_vs_oracle AS
SELECT
    a.task_id,
    a.agent                       AS agent,
    a.model,
    am.value                      AS agent_reward,
    om.value                      AS oracle_reward,
    CASE WHEN om.value > 0 THEN am.value / om.value END AS ratio_vs_oracle,
    a.input_tokens,
    a.output_tokens
FROM runs a
JOIN metrics am ON am.run_id = a.run_id AND am.name = 'reward'
JOIN runs o     ON o.task_id = a.task_id AND o.agent = 'oracle'
JOIN metrics om ON om.run_id = o.run_id AND om.name = 'reward'
WHERE a.agent <> 'oracle';
