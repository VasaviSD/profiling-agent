# Optimizer Pipe

## Overview

The Optimizer Pipe (`optimizer.py`) is an executable script that orchestrates a sequence of agents (steps) to perform automated C++ performance analysis and code modification proposals. It first performs a global profiling run on a specified executable and its associated source directory. Then, for each C++ source file found in that directory, it initiates an optimization loop.

This pipe aims to:
1.  Perform an initial, global performance profile of a given C++ executable using its source directory for context.
2.  For each C++ implementation file (`.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx`) in the source directory:
    a.  Combine the content of the individual C++ file with the global performance profile data.
    b.  Analyze this combined data to identify potential bottlenecks specific to that file's context within the overall profile.
    c.  Generate potential code variants (via Replicator) to address these bottlenecks.
    d.  Save these code variants as new source files (via Patcher).
    e.  **Profile each generated variant.** This involves profiling the variant within its own directory context.
    f.  **Evaluate each profiled variant against the baseline.** The Evaluator compares the variant's profile to the original and prints if a variant is a "Significant Improvement".
3.  Support iterative refinement if multiple iterations are specified (though automatic selection of improved variants for the next iteration is not yet implemented).

## Functionality

-   **Initial Global Profiling:** Runs the `Profiler` agent once using the provided `--executable` and `--source-dir` to get a baseline performance profile.
-   **Source File Iteration:** Discovers C++ implementation and header files (`.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx`) in the `--source-dir` and processes each one individually through an optimization loop.
-   **Orchestration (per C++ file):** For each discovered C++ file, sequentially runs the `Analyzer`, `Replicator`, and `Patcher` agents.
-   **Variant Profiling:** For each successfully patched variant, runs the `Profiler` agent to collect performance data.
-   **Variant Evaluation:** For each variant, runs the `Evaluator` agent to compare its profile to the original and prints if a "Significant Improvement" is detected.
-   **Data Flow:** Manages the flow of data: the global profiler output is combined with individual C++ file content for the Analyzer. Subsequent agents use outputs from the previous step.
-   **Input:** Takes a source directory (`--source-dir`) and a path to a pre-compiled executable (`--executable`), along with a general output directory (`--output-dir`).
-   **Output:** Saves the initial global profiler output. For each processed C++ file, it saves YAML outputs from `Analyzer`, `Replicator`, `Patcher`, `Profiler` (for variants), and `Evaluator` (for variants), as well as patched source files into a structured hierarchy within the specified output directory.
-   **Iteration:** Supports multiple optimization iterations for each C++ file. However, the pipeline does not yet automatically select the best variant as the new baseline for the next iteration.

## How to Run

The Optimizer Pipe is run from the command line, typically from the root of the `profiling-agent` project directory.

```bash
python -m pipe.optimizer.optimizer --source-dir <path_to_cpp_source_directory> --executable <path_to_executable> --output-dir <path_to_output_directory>
```

**Command-Line Arguments:**

-   `--source-dir` (string, **required**):  
    Path to the directory containing the C++ source files for the target executable. The script will search for `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` files directly within this directory for individual optimization loops.  
    *Example:* `projects/my_project/src/`

-   `--executable` (string, **required**):  
    Path to the pre-compiled C++ executable that will be profiled initially to get a global performance overview.  
    *Example:* `projects/my_project/build/my_app`

-   `--output-dir` (string, **required**):  
    Path to a directory where all intermediate and final YAML outputs from each agent, as well as patched source files, will be saved. The directory will be created if it doesn't exist. Subdirectories will be created for the initial global profile and then for each processed source file and each iteration.  
    *Example:* `./optimizer_run_outputs`

-   `--iterations` (integer, optional, default: `1`):  
    The number of times to run the Analyzer → Replicator → Patcher sequence for each discovered C++ file.

**Example Usage:**

```bash
g++ -g -O3 -o data/compile/heavy_computation data/sources/heavy_computation.cpp
```

```bash
# Ensure you are in the root directory of the profiling-agent project
poetry run python -m pipe.optimizer.optimizer \
    --source-dir data/sources/ \
    --executable data/compile/heavy_computation \
    --output-dir ./optimizer_run_1 \
    --iterations 1
```

## Pipeline Steps & Outputs

1.  **Initial Global Profiler Agent:**
    -   Input: `source_dir` and `executable` provided via CLI. An input YAML (`global_profiler_input.yaml`) is generated by the pipe in the `output-dir`.
    -   Output: `global_profiler_output.yaml` (saved in `output-dir`). This contains the `perf_command` and `perf_report_output` for the initial executable run.

2.  **C++ Source File Discovery:** The pipe finds all `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` files in the `source-dir`.

3.  **Main Loop (For each discovered C++ source/header file):**
    -   For each iteration, a subdirectory is created: `<output-dir>/iter_<N>/<filename>/`
    -   **Analyzer Agent:**
        -   Input: The *source code content* of the file and the global profiler output.
        -   Output: `analyzer_output.yaml` (includes `performance_analysis` and `bottleneck_location` if any).
        -   If no actionable hotspots are found, the pipe skips further processing for this file.
    -   **Replicator Agent:**
        -   Input: `analyzer_output.yaml`
        -   Output: `replicator_output.yaml` (contains `modified_code_variants`).
    -   **Patcher Agent:**
        -   Input: `replicator_output.yaml` and the original file name.
        -   Output: 
            -   `patcher_output.yaml` (details success/failure of writing each variant).
            -   Patched source files for each variant.
    -   **Profiler Agent (on variants):**
        -   For each successfully patched variant, runs the Profiler agent on the variant's directory.
        -   Output: `profiler_output.yaml` for each variant.
    -   **Evaluator Agent (on variants):**
        -   For each variant, runs the Evaluator agent to compare its profile to the original.
        -   Output: `evaluator_output.yaml` for each variant.
        -   If a variant is a "Significant Improvement", this is printed to the console.

4.  **Iteration:**  
    The above steps are repeated for the specified number of iterations. The pipeline currently does not automatically select the best variant as the new baseline for the next iteration.

## Dependencies

-   Python 3.x
-   All dependencies for the `Profiler`, `Analyzer`, `Replicator`, `Patcher`, and `Evaluator` agents.
-   External tools required by the agents (e.g., C++ compiler, Linux `perf`).