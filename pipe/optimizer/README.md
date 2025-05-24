# Optimizer Pipe

## Overview

The Optimizer Pipe (`optimizer.py`) is an executable script that orchestrates a sequence of agents (steps) to perform automated C++ performance analysis and code modification proposals. It provides a user-friendly command-line interface to run the Profiler, Analyzer, and Replicator agents in a connected pipeline.

This pipe is intended to simplify the process of:
1.  Profiling C++ code to gather performance data.
2.  Analyzing the performance data to identify bottlenecks.
3.  Generating potential code variants to address these bottlenecks.

## Functionality

-   **Orchestration:** Sequentially runs the `Profiler`, `Analyzer`, and `Replicator` agents.
-   **Data Flow:** Manages the flow of data between these agents, using the output of one step as the input for the next.
-   **Input:** Takes an initial YAML configuration file for the `Profiler` (specifying the C++ source directory and profiling options) and a general output directory.
-   **Output:** Saves the YAML output from each agent step (`Profiler`, `Analyzer`, `Replicator`) into the specified output directory. The final output from the `Replicator` contains the proposed code variants.
-   **Iteration (Basic):** Includes a basic loop for iterations. For multiple iterations, the output of the Replicator would ideally feed back into the Profiler (e.g., by updating the source code path to a modified version). This feedback loop is currently a placeholder in the script.

## How to Run

The Optimizer Pipe is run from the command line, typically from the root of the `profiling-agent` project directory.

```bash
python -m pipe.optimizer.optimizer --profiler-input-yaml <path_to_profiler_config.yaml> --output-dir <path_to_output_directory>
```

**Command-Line Arguments:**

-   `--profiler-input-yaml` (string, **required**):
    Path to the YAML file containing the input configuration for the initial `Profiler` step. This file should define at least `source_dir` and can include other profiler-specific options (see `step/profiler/README.md` for details).
    *Example:* `data/examples/profiler_input_initial.yaml`

-   `--output-dir` (string, **required**):
    Path to a directory where all intermediate and final YAML outputs from each agent in the pipeline will be saved. The directory will be created if it doesn't exist.
    *Example:* `./optimizer_run_outputs`

-   `--iterations` (integer, optional, default: `1`):
    The number of times to run the Profiler -> Analyzer -> Replicator sequence. 
    **Note:** True multi-iteration (where the Replicator's output modifies the source for the next Profiler run) is not fully implemented; this argument currently just repeats the sequence with the initial profiler input for each iteration unless the script is manually modified to update the source path based on previous Replicator outputs.

**Example Usage:**

```bash
# Ensure you are in the root directory of the profiling-agent project
poetry run python -m pipe.optimizer.optimizer \
    --profiler-input-yaml step/profiler/examples/profiler_input_example.yaml \
    --output-dir ./optimizer_run_1
```

## Pipeline Steps & Outputs

1.  **Profiler Agent:** 
    -   Input: Uses the `--profiler-input-yaml` provided to the pipe.
    -   Output: `profiler_output_iter<N>.yaml` (saved in `--output-dir`). This contains `source_code`, `perf_command`, and `perf_report_output`.

2.  **Analyzer Agent:**
    -   Input: Takes `profiler_output_iter<N>.yaml` from the previous step.
    -   Output: `analyzer_output_iter<N>.yaml` (saved in `--output-dir`). This includes `performance_analysis` and structured bottleneck details.

3.  **Replicator Agent:**
    -   Input: Takes `analyzer_output_iter<N>.yaml` from the previous step.
    -   Output: `replicator_output_iter<N>.yaml` (saved in `--output-dir`). This is the final output of one pipeline pass, containing `replication_strategy` and `replicated_variants`.

## Dependencies

-   Python 3.x
-   All dependencies for the `Profiler`, `Analyzer`, and `Replicator` agents (including `core.utils`, and the respective agent modules).
-   External tools required by the agents (e.g., C++ compiler, Linux `perf`). 