# Evaluator Agent (`step/evaluator/`)

## Overview

The Evaluator agent is responsible for comparing the performance of a C++ code variant against its original version. It takes a single YAML configuration file as input. This configuration file specifies the paths to two Profiler output YAML files (one for the original code and one for the variant). Using an LLM, the Evaluator analyzes the `perf report` outputs from these two specified profiler files to determine if the variant offers a significant performance improvement, regression, or has similar performance.

## Functionality

-   **Input (Primary Configuration YAML):** Requires a single YAML file specified via the `--input-file` CLI argument. This YAML must contain:
    -   `original_profiler_output_path`: (string, required) Path to the Profiler's output YAML for the "original" C++ code.
    -   `variant_profiler_output_path`: (string, required) Path to the Profiler's output YAML for the "variant" C++ code.
    -   `evaluator_specific_options` (object, optional): 
        -   `threshold` (integer, optional): Overrides the default threshold (from `prompts/evaluator_prompt.yaml`) for performance hotspot analysis. E.g., `5` for 5%.
        -   `context` (integer, optional): Overrides the default context lines (from `prompts/evaluator_prompt.yaml`). (Currently informational for this agent's prompt).
    -   The two referenced Profiler output YAMLs must each contain `perf_report_output` (text from `perf report --stdio`) and optionally `source_code`.

-   **LLM Configuration:** LLM settings (e.g., model, temperature) and detailed prompt structures are primarily configured within `step/evaluator/prompts/evaluator_prompt.yaml`. The `threshold` and `context` parameters within this prompt YAML act as defaults if not overridden in the primary input configuration YAML.

-   **Comparison:** The agent reads the two profiler YAML files specified in its primary input configuration.

-   **LLM Analysis:** It feeds the `perf_report_output` (and source code if available) from these two files, along with the configured `threshold`, to an LLM. The LLM is guided by `step/evaluator/prompts/evaluator_prompt.yaml` to:
    -   Identify key differences in function overheads and hotspots.
    -   Determine if the variant is an improvement.
    -   Quantify and explain any improvements or regressions.
    -   Provide a confidence score for its evaluation.

-   **Output:** Produces a YAML file (specified by `--output-file`) containing:
    -   `evaluator_input_config_path`: Path to the primary input YAML used by the Evaluator.
    -   `actual_original_profiler_output_path`: Absolute path to the original profiler YAML that was processed.
    -   `actual_variant_profiler_output_path`: Absolute path to the variant profiler YAML that was processed.
    -   The structured `evaluation_results` from the LLM (comparison_summary, is_improvement, etc.).
    -   An `evaluator_error` field if any issues occurred.

## How to Run

The Evaluator agent is run from the command line, typically from the root of the `profiling-agent` project.

```bash
poetry run python -m step.evaluator.evaluator_agent --input-file <path_to_evaluator_input_config.yaml> --output-file <path_to_evaluator_output.yaml>
```

**Command-Line Arguments (from base `Step` class):**

-   `--input-file INPUT_FILE` (string, **required**):
    Path to the Evaluator's primary input configuration YAML file.
    *Example:* `step/evaluator/examples/evaluator_input.yaml`

-   `--output-file OUTPUT_FILE` (string, **required**):
    Path to save the Evaluator's output YAML file.
    *Example:* `step/evaluator/examples/evaluator_output.yaml`

**Example Evaluator Input Configuration YAML (`evaluator_input_config_example.yaml`):**

```yaml
original_profiler_output_path: "optimizer_run_1/heavy_computation/iter_1/profiler_output.yaml"
variant_profiler_output_path: "optimizer_run_1/heavy_computation/iter_1/profiler_run_variant_variant_1/profiler_output_variant_variant_1.yaml"

# Optional: Override default threshold/context from prompts/evaluator_prompt.yaml
# evaluator_specific_options:
#   threshold: 10
#   context: 5 
```

**Example Usage:**

```bash
# Ensure you are in the root directory of the profiling-agent project
# Assuming evaluator_input_config.yaml exists and is populated correctly:
poetry run python -m step.evaluator.evaluator_agent \
    step/evaluator/examples/evaluator_input.yaml \
    -o step/evaluator/examples/evaluator_output.yaml
```

## Output Structure (Example `evaluator_output.yaml`)

```yaml
evaluator_input_config_path: /home/user/profiling-agent/step/evaluator/examples/evaluator_input_config.yaml
actual_original_profiler_output_path: /home/user/profiling-agent/optimizer_run_1/heavy_computation/iter_1/profiler_output.yaml
actual_variant_profiler_output_path: /home/user/profiling-agent/optimizer_run_1/heavy_computation/iter_1/profiler_run_variant_variant_1/profiler_output_variant_variant_1.yaml
evaluation_results:
  comparison_summary: |
    The variant shows a significant reduction in overhead for the 'main' function and relocates some overhead to a new 'bar' function which appears more efficient overall.
  is_improvement: true
  improvement_details: |
    - Overhead in 'main' decreased from 50.00% to 20.00%.
    - A new function 'bar' now accounts for 10.00%, which seems to have taken over work from the original 'foo' (30.00%) more efficiently.
  confidence_score: 0.85
  detailed_analysis: |
    The performance profile has shifted. The reduction in 'main' and the replacement of 'foo' with a lower-overhead 'bar' suggest that the variant is more performant. The overall distribution of samples indicates less time spent in the primary computation loop.
  original_hotspots: |
    - 50.00% program.orig [.] main
    - 30.00% program.orig [.] foo
  variant_hotspots: |
    - 20.00% program.var [.] main
    - 10.00% program.var [.] bar
evaluator_error: null
```
