# Optimizer Pipe

## Overview

The Optimizer Pipe (`optimizer.py`) is an executable script that orchestrates a sequence of agents (steps) to perform automated C++ performance analysis and code modification proposals. It has been refactored to first perform a global profiling run on a specified executable and its associated source directory. Then, for each C++ source file found in that directory, it initiates an optimization loop.

This pipe aims to:
1.  Perform an initial, global performance profile of a given C++ executable using its source directory for context.
2.  For each C++ implementation file (`.cpp`, `.cc`, `.cxx`) in the source directory:
    a.  Combine the content of the individual C++ file with the global performance profile data.
    b.  Analyze this combined data to identify potential bottlenecks specific to that file's context within the overall profile.
    c.  Generate potential code variants (via Replicator) to address these bottlenecks.
    d.  Save these code variants as new source files (via Patcher).
    e.  **(Currently Disabled)** Profile each generated variant. This would involve recompiling the variant within a copy of the full project context.
    f.  **(Currently Disabled)** Evaluate each profiled variant against a baseline and select the best one to inform subsequent iterations for that specific file.
3.  Support iterative refinement if multiple iterations are specified (though automatic selection of improved variants is currently disabled).

## Functionality

-   **Initial Global Profiling:** Runs the `Profiler` agent once using the provided `--executable` and `--source-dir` to get a baseline performance profile.
-   **Source File Iteration:** Discovers C++ implementation files (`.cpp`, `.cc`, `.cxx`) in the `--source-dir` and processes each one individually through an optimization loop.
-   **Orchestration (per C++ file):** For each discovered C++ file, sequentially runs the `Analyzer`, `Replicator`, and `Patcher` agents.
-   **Data Flow:** Manages the flow of data: the global profiler output is combined with individual C++ file content for the Analyzer. Subsequent agents use outputs from the previous step.
-   **Variant Generation:** The `Replicator` suggests modifications, and the `Patcher` writes these as new source files.
-   **Variant Profiling (Currently Disabled):** The logic to re-profile patched variants by recompiling them within a full project copy is present but commented out.
-   **Variant Evaluation (Currently Disabled):** The `Evaluator` step and automatic selection of the best variant are commented out.
-   **Input:** Takes a source directory (`--source-dir`) and a path to a pre-compiled executable (`--executable`), along with a general output directory (`--output-dir`).
-   **Output:** Saves the initial global profiler output. For each processed C++ file, it saves YAML outputs from `Analyzer`, `Replicator`, `Patcher`, and any generated patched source files into a structured hierarchy within the specified output directory.
-   **Iteration:** Supports multiple optimization iterations for each C++ file. However, with evaluation disabled, each iteration for a file will re-analyze its original state based on the global profile (or the state from the last manual update to its source if external changes were made).

## How to Run

The Optimizer Pipe is run from the command line, typically from the root of the `profiling-agent` project directory.

```bash
python -m pipe.optimizer.optimizer --source-dir <path_to_cpp_source_directory> --executable <path_to_executable> --output-dir <path_to_output_directory>
```

**Command-Line Arguments:**

-   `--source-dir` (string, **required**):
    Path to the directory containing the C++ source files for the target executable. The script will search for `.cpp`, `.cc`, `.cxx` files directly within this directory for individual optimization loops.
    *Example:* `projects/my_project/src/`

-   `--executable` (string, **required**):
    Path to the pre-compiled C++ executable that will be profiled initially to get a global performance overview.
    *Example:* `projects/my_project/build/my_app`

-   `--output-dir` (string, **required**):
    Path to a directory where all intermediate and final YAML outputs from each agent, as well as patched source files, will be saved. The directory will be created if it doesn't exist. Subdirectories will be created for the initial global profile and then for each processed source file and each iteration.
    *Example:* `./optimizer_run_outputs`

-   `--iterations` (integer, optional, default: `1`):
    The number of times to run the Analyzer -> Replicator -> Patcher sequence for each discovered C++ file.

**Example Usage:**

```bash
# Ensure you are in the root directory of the profiling-agent project
poetry run python -m pipe.optimizer.optimizer \
    --source-dir ./my_project/src \
    --executable ./my_project/build/my_app \
    --output-dir ./optimizer_run_1 \
    --iterations 1
```

## Pipeline Steps & Outputs

1.  **Initial Global Profiler Agent:**
    -   Input: `source_dir` and `executable` provided via CLI. An input YAML (`initial_global_profiler_input.yaml`) is generated by the pipe in the `output-dir`.
    -   Output: `initial_global_profiler_output.yaml` (saved in `output-dir`). This contains the `perf_command` and `perf_report_output` for the initial executable run.

2.  **C++ Source File Discovery:** The pipe finds all `.cpp`, `.cc`, `.cxx` files in the `source-dir`.

3.  **Main Loop (For each discovered C++ source file `current_cpp_file`):
    -   A base directory for this file's outputs is created: `<output-dir>/<sanitized_original_cpp_filename>/`
    -   **Inner Loop (For each iteration `N` from 1 to `--iterations`):
        -   Output subdirectory: `<output-dir>/<sanitized_original_cpp_filename>/iter_<N>/`
        1.  **Analyzer Agent:**
            -   Input: An `analyzer_input.yaml` is generated by the pipe. It contains the *source code content* of `current_cpp_file` and the `perf_command` / `perf_report_output` from the `initial_global_profiler_output.yaml` (or from a previous iteration's champion if evaluation were active).
            -   Output: `analyzer_output.yaml`. This includes `performance_analysis` and `identified_hotspots` if any.
            -   *Note:* If no actionable hotspots are found for `current_cpp_file`, the pipe skips further processing (Replicator, Patcher, further iterations) for this specific file and moves to the next C++ file.

        2.  **Replicator Agent:**
            -   Input: Takes `analyzer_output.yaml` from the previous step.
            -   Output: `replicator_output.yaml`. This contains `modified_code_variants` for `current_cpp_file`.

        3.  **Patcher Agent:**
            -   Input: Takes `replicator_output.yaml`. The pipe injects `original_file_name` (basename of `current_cpp_file`).
            -   Output: 
                -   `patcher_output.yaml`. Details success/failure of writing each variant.
                -   Patched source files for each variant of `current_cpp_file` are saved (typically in a subdirectory structure managed by the Patcher, e.g., under `data/sources/patched_variants/...` by default, or as specified if Patcher's `output_base_dir` logic is used).

        4.  **Variant Profiling (Currently Disabled):**
            -   This step is commented out in the script.
            -   If active, it would involve: For each successfully patched variant of `current_cpp_file`:
                -   Creating a temporary full copy of the project from `--source-dir`.
                -   Replacing `current_cpp_file` in this temporary copy with the variant's code.
                -   Running the `Profiler` agent on this temporary project (forcing recompilation) to get a variant-specific profile.
                -   Saving `profiler_output_variant_<ID>.yaml`.

        5.  **Evaluator Agent & Best Variant Selection (Currently Disabled):**
            -   These steps are commented out in the script.
            -   If active, the `Evaluator` would compare each variant's profile (from step 4) against the profile of the code that was fed to the `Analyzer` in the current iteration. A best variant would be selected to inform the next iteration for `current_cpp_file`.
            -   Since this is disabled, the input to the `Analyzer` for `current_cpp_file` in the next iteration (if any) will effectively be its original version combined with the initial global profile.

## Dependencies

-   Python 3.x
-   All dependencies for the `Profiler`, `Analyzer`, `Replicator`, and `Patcher` agents.
-   External tools required by the agents (e.g., C++ compiler, Linux `perf`). 