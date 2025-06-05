# C++ Performance Analyzer Agent

## Overview

The Analyzer agent is a Python-based tool designed to analyze C++ performance data. It leverages a Large Language Model (LLM) to interpret Linux `perf` tool output alongside the corresponding C++ source code. The agent identifies significant performance bottlenecks, explains their likely causes based on `perf` metrics and code structure, and reports these findings in a structured format.

This agent is intended to be part of a larger profiling and optimization pipeline, where its output can feed into subsequent agents (like a code Replicator) that attempt to fix the identified bottlenecks.

## Functionality

-   **Input Processing:** Reads C++ source code, the `perf` command used for profiling, and the textual report from `perf report`.
-   **LLM Interaction:** Uses a configured LLM (via `step/analyzer/prompts/performance_analysis_prompt.yaml`) to analyze the provided data.
-   **Bottleneck Identification:** The LLM identifies key performance bottlenecks.
-   **Cause Analysis:** For each bottleneck, the LLM provides a hypothesis on why it might be slow, referencing code and `perf` metrics.
-   **Structured Output:** Produces a YAML output containing the raw LLM analysis and also parses this analysis into distinct fields for easier downstream consumption:
    -   `performance_analysis`: The full textual analysis from the LLM.
    -   `bottleneck_location`: The specific location (e.g., function name, file:line) of the primary bottleneck identified.
    -   `bottleneck_type`: The nature or impact of the bottleneck (e.g., percentage of CPU samples).
    -   `analysis_hypothesis`: The LLM's hypothesis for the cause of the bottleneck.

## Input Data

The agent expects an input YAML file containing the following fields:

-   `source_code` (string): The C++ source code of the project (or relevant parts).
-   `perf_command` (string): The Linux `perf` command that was used to generate the profiling data.
-   `perf_report_output` (string): The textual output from `perf report` (e.g., from `perf report --stdio`).
-   `threshold` (integer, optional): The percentage threshold for considering a code region a significant bottleneck (e.g., `5` for 5%). Defaults to the value in `performance_analysis_prompt.yaml`.
-   `context` (integer, optional): The number of lines of code context to show around a bottleneck. Defaults to the value in `performance_analysis_prompt.yaml`.

**Example Input YAML (`analyzer_input.yaml`):**
```yaml
source_code: |
  #include <iostream>
  void my_function() {
    for (long i = 0; i < 100000000; ++i) {
      // intensive work
    }
  }
  int main() {
    my_function();
    return 0;
  }
perf_command: "perf record -g --call-graph dwarf ./my_program"
perf_report_output: |
  # Children      Self  Command          Shared Object      Symbol
  # ........  ........  ...............  .................  ....................
      99.80%    99.80%  my_program       my_program         [.] my_function
threshold: 5
context: 3
```

## How to Run

The Analyzer agent is run from the command line, typically from the root of the project directory.

```bash
python -m step.analyzer.analyzer_agent -o <path_to_output_yaml> <path_to_input_yaml>
```

**Example:**

Assuming your input YAML is `step/analyzer/examples/analyzer_input.yaml` and you want the output in `step/analyzer/examples/analyzer_output.yaml`:

```bash
# Make sure you are in the root directory of the profiling-agent project
poetry run python -m step.analyzer.analyzer_agent -o step/analyzer/examples/analyzer_output.yaml step/analyzer/examples/analyzer_input.yaml
```

This command will process the input, interact with the LLM as configured in `step/analyzer/prompts/performance_analysis_prompt.yaml`, and write the structured analysis to the specified output YAML file.

## Dependencies

-   Python 3.x
-   Core modules of the `profiling-agent` project (`Step`, `LLM_template`, `LLM_wrap`).
-   An accessible LLM configured as per `LLM_wrap` requirements.
