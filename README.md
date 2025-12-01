# Sprint analysis through JQL

> [!WARNING]
> **AI-authored:** This change was autonomously planned and implemented by an AI software factory from a human-authored specification, with possible subsequent human review or modification.

> [!WARNING]
> This experiment is effectively abandoned. The generated material is retained primarily as a research artifact.

Acquire one Jira board's sprint issue sets through ACLI JQL queries (shell) and analyze them locally with one standard-library Python script, publishing immutable observations. All inputs, fixtures, scripts, and outputs are local files within this experiment. See [VISION.md](VISION.md), the [implementation plan](PLAN.md), and the provisional [acquisition contract](contract.md).

```sh
python3 analyze.py --input fixtures/sprint-42 --output work/analysis.json

python3 analyze.py --input fixtures/sprint-42 \
    --snapshots fixtures/snapshots --history fixtures/history \
    --output work/analysis.json

bash publish.sh work/analysis.json

bash publish.sh work/analysis.json /tmp/replay-analysis

python3 -m unittest discover -s tests -p 'test_*.py'
bash tests/test_acquire.sh
```

## Notes

- experiment; see whether JQL alone could support analysis/estimation
- got reasonably far pulling useful information directly through JQL
- limitation; eventually needed Python for meaningful analysis
- once Python is required, mixed JQL + Python approach starts feeling unnecessarily complicated
- better direction may be to codify the taxonomy more explicitly
- then use a simple data-insights layer in a programming language suited to large-scale analysis
- versioned taxonomy would make this even stronger
- overall; JQL useful for retrieval/filtering, less convincing as the core analytical model
