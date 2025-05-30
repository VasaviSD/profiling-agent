# Patcher Agent (`step/patcher/`)

## Overview

The Patcher agent is responsible for taking multiple code variants (e.g., from a Replicator agent) and saving each one as a new file into a structured directory hierarchy. It processes all provided variants, creating a dedicated subdirectory for each.

This agent is a file-writing utility. It does not perform intelligent merging or diffing. Its main purpose is to persist generated code variants to the filesystem. All input key-value pairs from the input YAML are preserved in the output YAML, with the Patcher's results added or updated.

## Functionality

-   **Input:** Reads the original C++ source code (for context), a list of `modified_code_variants` (each with a `variant_id` and the full `code`), and the `original_file_name`.
-   **Variant Processing:** Iterates through all variants in the `modified_code_variants` list.
-   **Directory Management:**
    -   Uses a default base output directory: `data/sources/patched_variants/`.
    -   For each variant, creates a subdirectory within the base directory. The subdirectory name is derived from the `variant_id` (sanitized and lowercased, e.g., "Variant 1" becomes "variant_1").
-   **File Creation:**
    -   Inside each variant-specific subdirectory, saves the variant's `code` to a file.
    -   The filename used is the `original_file_name` provided in the input (e.g., `heavy_computation.cpp`).
-   **Output:** Produces a YAML output that includes all original input data, plus:
    -   A `patcher_status` indicating the overall outcome (`all_success`, `partial_success`, `all_failed`).
    -   A list (`patched_variants_results`) detailing the success or failure for each processed variant, including the path to the created file.
-   **Filename Sanitization:** Uses a helper to sanitize `variant_id` (for directory names) and `original_file_name` (for filenames) to ensure they are filesystem-friendly, preserving dots for extensions.

## Input Data (from input YAML)

The agent expects an input YAML file (or a dictionary if called programmatically) with the following primary keys:

-   `source_code` (string): The content of the original C++ source file. (This is primarily for context if the Patcher is part of a pipeline; the `code` within each variant is what gets written).
-   `modified_code_variants` (list, **required**): A list of dictionaries. Each dictionary represents a code variant and **must** contain:
    -   `variant_id` (string): An identifier for the variant (e.g., "Variant 1", "Optimized Loop"). This is used to name the output subdirectory.
    -   `code` (string): The full C++ code content of this specific variant.
-   `original_file_name` (string, **required**): The name of the original source file (e.g., `main.cpp`, `heavy_computation.cpp`). This will be the name of the file saved in each variant's subdirectory.

Any other key-value pairs present in the input YAML will be preserved and included in the output YAML.

**Example Input YAML (`patcher_input.yaml`):**
```yaml
source_code: |
  #include <iostream>
  // ... original content ...
  int main() { std::cout << "Original" << std::endl; return 0;}
original_file_name: "my_program.cpp"
modified_code_variants:
  - variant_id: "Variant Alpha"
    code: |
      #include <iostream>
      // ... variant alpha content ...
      int main() { std::cout << "Alpha Version" << std::endl; return 0;}
    explanation: "Changed cout message for Alpha."
  - variant_id: "Variant Beta (Optimized)"
    code: |
      #include <iostream>
      #include <vector> // Added for Beta
      // ... variant beta content ...
      int main() { std::cout << "Beta Version - Optimized" << std::endl; return 0;}
    explanation: "Changed cout and added vector for Beta."
# Other fields from a previous step (e.g., Replicator) might also be here
perf_command: "perf record -g -- ./a.out"
analysis_hypothesis: "Initial cout was too slow."
```

## Output Data (output YAML)

The agent produces an output YAML file (or dictionary) containing:

-   All key-value pairs from the input YAML are preserved.
-   `patcher_status` (string): Indicates the overall outcome: 'all_success', 'partial_success', or 'all_failed'. (This will overwrite any field named `patcher_status` from the input).
-   `patcher_overall_error` (string, optional): A high-level error message if a fundamental issue prevented processing (e.g., missing required inputs). (Overwrites if present in input).
-   `patched_variants_results` (list): A list of dictionaries, one for each variant found in `modified_code_variants`. Each dictionary contains: (Overwrites if present in input).
    -   `variant_id` (string): The ID of the processed variant.
    -   `patched_file_path` (string): The absolute path to the newly created patched source file if successful, otherwise `None`.
    -   `status` (string): 'success' or 'failed' for this specific variant.
    -   `error` (string, optional): An error message if patching this specific variant failed, otherwise `None`.

**Example Output YAML (`patcher_output.yaml`):**
```yaml
source_code: |
  #include <iostream>
  // ... original content ...
  int main() { std::cout << "Original" << std::endl; return 0;}
original_file_name: "my_program.cpp"
modified_code_variants:
  - variant_id: "Variant Alpha"
    code: |
      #include <iostream>
      // ... variant alpha content ...
      int main() { std::cout << "Alpha Version" << std::endl; return 0;}
    explanation: "Changed cout message for Alpha."
  - variant_id: "Variant Beta (Optimized)"
    code: |
      #include <iostream>
      #include <vector> // Added for Beta
      // ... variant beta content ...
      int main() { std::cout << "Beta Version - Optimized" << std::endl; return 0;}
    explanation: "Changed cout and added vector for Beta."
perf_command: "perf record -g -- ./a.out"
analysis_hypothesis: "Initial cout was too slow."
patcher_status: "all_success"
patcher_overall_error: null
patched_variants_results:
  - variant_id: "Variant Alpha"
    patched_file_path: "/home/user/profiling-agent/data/sources/patched_variants/variant_alpha/my_program.cpp"
    status: "success"
    error: null
  - variant_id: "Variant Beta (Optimized)"
    patched_file_path: "/home/user/profiling-agent/data/sources/patched_variants/variant_beta_optimized/my_program.cpp"
    status: "success"
    error: null
```

## How to Run

The Patcher agent is run using the `core.Step` CLI framework.

```bash
# Ensure you are in the root directory of the profiling-agent project
poetry run python -m step.patcher.patcher_agent path/to/your/patcher_input.yaml -o path/to/your/patcher_output.yaml
```
For example:
```bash
poetry run python -m step.patcher.patcher_agent step/patcher/examples/patcher_input.yaml -o step/patcher/examples/patcher_output.yaml
```
(Assuming `patcher_input.yaml` is structured as per the new requirements).

In a pipeline, an orchestrator would prepare an input dictionary matching the Patcher's expected input schema and call its `run()` method or use the `step()` method.

## Dependencies

-   Python 3.x
-   `core.step.Step` (base class)
-   `copy` module (for deep copying input data)
-   `re` module (for filename sanitization)
-   Standard Python `os` module. 