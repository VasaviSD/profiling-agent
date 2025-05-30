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

-   **Purpose:** To apply a selected code variant (which is a full file content) to an original source file, saving it as a new file in a specified output directory.
-   **Functionality:** Takes the original file name, the full code of a selected variant, a variant ID, and an output directory. It then writes the variant's code to a new file, named using the original name and variant ID (e.g., `original_filename_Variant1.cpp`).
-   **Output:** Produces a YAML file confirming the `patched_file_path` and status.
-   **Details:** For more information on its specific inputs, outputs, and how to run it, please see `step/patcher/README.md`.

## Pipeline Workflow Example

These agents are designed to work in a sequence. A common workflow would be:

1.  **Run the Profiler Agent:** Provide it with an input YAML specifying the C++ source directory and other options. It outputs profiling results (`profiler_output.yaml`) structured for the Analyzer.
    ```bash
    # Example assumes input config is in step/profiler/examples/profiler_input_example.yaml
    poetry run python -m step.profiler.profiler_agent step/profiler/examples/profiler_input_example.yaml -o step/profiler/examples/profiler_output.yaml
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
    poetry run python -m step.patcher.patcher_agent step/patcher/examples/patcher_input_example.yaml -o step/patcher/examples/patcher_output_example.yaml
    ```

This pipeline allows for an automated flow from performance data collection and analysis to the generation of potential code optimizations and their application to new files.

## Further Steps (Conceptual)

Future agents in this directory could extend the pipeline, for example:

-   An **Evaluator Agent:** To compile and test the code variants (from the Patcher's output files or Replicator's direct output) using `perf` or other benchmarks.
-   An **Integrator Agent:** To attempt to integrate successfully evaluated code changes back into the original codebase (e.g., by generating diffs or patches, or by replacing the original file if desired).
