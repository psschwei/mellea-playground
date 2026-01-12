## 9. Future Evaluations (Placeholder)
- Comparative experiments across models/program versions with standard metrics (latency, cost, token usage, accuracy) plus dataset/prompt management remain deferred.
- Future capability: define experiments that sweep model/backend parameters for a program, aggregate metrics, and rank/annotate runs to highlight “best” results per chosen criteria (e.g., highest accuracy under cost ceiling).
- Planned building blocks:
  - Dataset/prompt registry with versioning, tags, and sharing to ensure reproducibility.
  - Metric capture pipeline collecting system metrics automatically plus pluggable domain scoring adapters (rubrics, structured scoring functions, human annotations).
  - Experiment definitions that orchestrate sweeps and produce comparison tables with custom ranking formulas.
  - Review/annotation UI for human-in-the-loop scoring or notes stored alongside run results.

