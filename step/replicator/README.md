# C++ Code Replicator Agent

## Overview

The Replicator agent is a Python-based tool that processes C++ source code along with identified performance bottleneck information (typically from an upstream agent like the Analyzer). It utilizes a Large Language Model (LLM) to understand the bottleneck and then proposes a fix strategy. Following this strategy, it generates multiple distinct C++ code variants aimed at addressing the identified performance issue.

This agent is designed to be a part of a profiling and automated code optimization pipeline, taking insights about performance problems and attempting to generate potential solutions.

## Functionality

-   **Input Processing:** Reads C++ source code, and details about a specific performance bottleneck including its location, type/nature, and the hypothesis regarding its cause.
-   **LLM Interaction:** Uses a configured LLM (via `step/replicator/prompts/code_replication_prompt.yaml`) to analyze the bottleneck and generate solutions.
-   **Fix Strategy Proposal:** The LLM first outlines a high-level strategy for addressing the bottleneck.
-   **Code Variant Generation:** The LLM generates multiple (typically 3, as per the default prompt) distinct C++ code modifications. Each variant represents a different approach to potentially fixing the bottleneck while aiming for correctness.
-   **Structured Output:** Produces a YAML output containing:
    -   `proposed_fix_strategy`: The LLM's textual description of the fix strategy.
    -   `modified_code_variants`: A list of dictionaries. Each dictionary represents a code variant and includes:
        -   `variant_id`: An identifier for the variant (e.g., "Variant 1").
        -   `explanation`: A brief explanation or rationale for the variant (if provided by the LLM).
        -   `code`: The modified C++ code snippet or function.

## Input Data

The agent expects an input YAML file (often the output of the Analyzer agent) containing the following fields:

-   `source_code` (string): The C++ source code of the project (or relevant parts containing the bottleneck).
-   `bottleneck_location` (string): A description of where the bottleneck is located (e.g., "`my_function()`", "`file.cpp:123`").
-   `bottleneck_type` (string): A description of the bottleneck's nature or impact (e.g., "95% CPU samples", "High cache miss rate").
-   `analysis_hypothesis` (string): The hypothesis from a performance analysis tool or agent explaining the likely cause of the bottleneck.

**Example Input YAML (`replicator_input.yaml`, potentially from Analyzer output):**
```yaml
source_code: |
  #include <iostream>
  void my_slow_function(int* data, int size) {
    for (int i = 0; i < size; ++i) {
      for (int j = 0; j < size; ++j) {
        data[i*size + j] *= 2; // Example operation
      }
    }
  }
  // ... rest of the code
bottleneck_location: "`my_slow_function` inner loop"
bottleneck_type: "High CPU usage due to nested loops"
analysis_hypothesis: "The nested loops in `my_slow_function` cause excessive computation. Loop unrolling, parallelization, or algorithmic changes might improve performance."
```

## How to Run

The Replicator agent is run from the command line, typically from the root of the project directory.

```bash
python -m step.replicator.replicator_agent -o <path_to_output_yaml> <path_to_input_yaml>
```

**Example:**

Assuming your input YAML is `step/analyzer/examples/analyzer_output.yaml` (output from the Analyzer) and you want the Replicator's output in `step/replicator/examples/replicator_output.yaml`:

```bash
# Make sure you are in the root directory of the profiling-agent project
poetry run python -m step.replicator.replicator_agent -o step/replicator/examples/replicator_output.yaml step/analyzer/examples/analyzer_output.yaml
```

This command will process the input, interact with the LLM as configured in `step/replicator/prompts/code_replication_prompt.yaml`, and write the proposed strategy and code variants to the specified output YAML file.

## Dependencies

-   Python 3.x
-   Core modules of the `profiling-agent` project (`Step`, `LLM_template`, `LLM_wrap`).
-   An accessible LLM configured as per `LLM_wrap` requirements.
