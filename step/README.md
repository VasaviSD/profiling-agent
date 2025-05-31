# Profiling Agent Steps

This directory (`step/`) contains individual agents or "steps" that form parts of a larger automated C++ performance analysis and code optimization pipeline.

Each subdirectory typically represents a distinct agent with its own specific role, configuration, and an associated LLM prompt to guide its behavior.

## Available Agents

Currently, the following agents are implemented:

### 1. Profiler Agent (`step/profiler/`)

-   **Purpose:** To compile C++ source code with multiple optimization presets, run `perf record` on each, generate `perf report`, and select the report from a preferred preset.
-   **Functionality:** Reads a source directory path from YAML, uses `CppCompiler` and `PerfTool` to perform compilation and profiling for different presets (e.g., `opt_only`, `debug_opt`), and selects the results from a preferred preset for output.
-   **Output:** Produces a YAML file containing the source code content, the `perf record` command, and the (potentially truncated) `perf report --stdio` output from the selected preset, structured for consumption by the Analyzer agent.
-   **Details:** For more information on its specific inputs, outputs, and how to run it, please see `step/profiler/README.md`.

### 2. Analyzer Agent (`step/analyzer/`)

-   **Purpose:** To analyze C++ performance data, typically from Linux `perf` output, in conjunction with the source code.
-   **Functionality:** It uses an LLM to identify performance bottlenecks, determine their likely causes, and extract key information like bottleneck location, type, and a detailed hypothesis.
-   **Output:** Produces a YAML file containing the full analysis from the LLM, along with parsed, structured fields (`bottleneck_location`, `bottleneck_type`, `analysis_hypothesis`) for easy consumption by subsequent agents.
-   **Details:** For more information on its specific inputs, outputs, and how to run it, please see `step/analyzer/README.md`.

### 3. Replicator Agent (`step/replicator/`)

-   **Purpose:** To take the analyzed performance bottleneck information and propose potential code modifications to address it.
-   **Functionality:** It uses an LLM to understand the provided bottleneck details (location, type, hypothesis) and the original source code. It then generates a proposed fix strategy and multiple distinct C++ code variants that attempt to implement a solution.
-   **Output:** Produces a YAML file containing the proposed fix strategy and a list of modified code variants, each with an explanation and the C++ code.
-   **Details:** For more information on its specific inputs, outputs, and how to run it, please see `step/replicator/README.md`.

### 4. Patcher Agent (`step/patcher/`)

-   **Purpose:** To save all provided C++ code variants as separate source files.
-   **Functionality:** Reads an input YAML (typically from the Replicator Agent) containing the `original_file_name` and a list of `modified_code_variants`. Each variant in the list should have a `variant_id` and the full `code` for that variant. The Patcher then creates a base output directory (defaults to `data/patched_variants/`) and, for each variant, creates a subdirectory named after a sanitized version of its `variant_id`. Inside this subdirectory, it saves the variant's `code` into a file named after the `original_file_name`.
-   **Output:** Produces a YAML file that includes all input fields, along with `patcher_status` (e.g., 'all_success', 'partial_success', 'all_failed') and a `patched_variants_results` list. Each item in this list details the outcome for a specific variant, including its `variant_id`, the `patched_file_path` (if successful), and a `status` ('success' or 'failed') for the file writing operation.
-   **Details:** For more information on its specific inputs, outputs, and how to run it, please see `step/patcher/README.md`.

### 5. Evaluator Agent (`step/evaluator/`)

-   **Purpose:** To compare the performance of a C++ code variant against an original version using their respective `perf report` outputs.
-   **Functionality:** Takes two Profiler output YAML files (one for original, one for variant) as input. It uses an LLM to analyze the `perf_report_output` from both, determine if the variant is an improvement, quantify changes, and provide an explanatory analysis.
-   **Output:** Produces a YAML file containing the LLM's structured evaluation, including a comparison summary, an `is_improvement` flag, details of changes, a confidence score, and identified hotspots from both reports.
-   **Details:** For more information on its specific inputs, outputs, and how to run it, please see `step/evaluator/README.md`.

## Pipeline Workflow Example

These agents are designed to work in a sequence. A common workflow would be:

1.  **Run the Profiler Agent:** Provide it with an input YAML specifying the C++ source directory and other options. It outputs profiling results (`profiler_output.yaml`) structured for the Analyzer.
    ```bash
    # Example assumes input config is in step/profiler/examples/profiler_input_example.yaml
    poetry run python -m step.profiler.profiler_agent step/profiler/examples/profiler_input.yaml -o step/profiler/examples/profiler_output.yaml
    ```
2.  **Run the Analyzer Agent:** Use the output from the Profiler (`profiler_output.yaml`) as the input for the Analyzer. It outputs an analysis YAML (`analyzer_output.yaml`).
    ```bash
    # Example assumes analyzer_input_example.yaml is compatible or profiler_output.yaml is used directly
    poetry run python -m step.analyzer.analyzer_agent step/profiler/examples/profiler_output.yaml -o step/analyzer/examples/analyzer_output.yaml 
    ```
3.  **Run the Replicator Agent:** Use the output from the Analyzer (`analyzer_output.yaml`) as the input for the Replicator. It will then generate potential code fixes based on the analysis.
    ```bash
    poetry run python -m step.replicator.replicator_agent step/analyzer/examples/analyzer_output.yaml -o step/replicator/examples/replicator_output.yaml
    ```
4.  **Run the Patcher Agent:** If you want to save one of the `Replicator`'s variants to a new file, prepare an input YAML for the Patcher (or orchestrate it programmatically) using data from the Replicator's output and the original source details. 
    ```bash
    poetry run python -m step.patcher.patcher_agent step/patcher/examples/patcher_input.yaml -o step/patcher/examples/patcher_output.yaml
    ```
5.  **Run the Evaluator Agent:** After profiling a code variant (which might be done by the Optimizer pipe or manually after using the Patcher), use the Profiler's output for the original code and the Profiler's output for the variant code as inputs to the Evaluator. 
    ```bash
    # Example assumes profiler_original.yaml and profiler_variant.yaml are available
    poetry run python -m step.evaluator.evaluator_agent step/evaluator/examples/profiler_original.yaml step/evaluator/examples/profiler_variant.yaml -o step/evaluator/examples/evaluator_output.yaml
    ```

This pipeline allows for an automated flow from performance data collection and analysis to the generation of potential code optimizations and their application to new files.

