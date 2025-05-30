# Patcher Agent (`step/patcher/`)

## Overview

The Patcher agent is responsible for applying a selected code variant to an original source file, saving the result as a new file. It assumes that the code variant provided is the complete, modified content for the source file.

This agent is a simple file-writing utility and does not perform intelligent merging, diffing, or LLM-based patching in its current form. It is designed to take a full code variant (as typically produced by the `Replicator` agent) and persist it to the filesystem in a structured way.

## Functionality

-   **Input:** Takes the original file name (for naming), the full code of a selected variant, a variant ID, and a base output directory.
-   **File Creation:** Constructs a new filename by appending the variant ID to the original filename (e.g., `originalName_variantID.cpp`).
-   **Directory Management:** Creates the specified output directory if it doesn't exist.
-   **Output:** Writes the `selected_variant_code` to the newly created file path and reports the path and status.

## Input Data (from input YAML)

The agent expects an input YAML file (or a dictionary if called programmatically) with the following keys:

-   `original_source_code` (string): The content of the original C++ source file. (Note: This is primarily for context in a pipeline; the `selected_variant_code` is what gets written.)
-   `original_file_name` (string, **required**): The name of the original source file (e.g., `main.cpp`). This is used to derive the new patched filename.
-   `selected_variant_code` (string, **required**): The full C++ code content of the chosen variant that should be saved.
-   `variant_id` (string, **required**): An identifier for the variant (e.g., "Variant_1", "Alpha"). This will be part of the new filename.
-   `output_base_dir` (string, **required**): The base directory where the new patched source file will be saved (e.g., `data/sources/patched_variants`).

*(Optional, for context, but not directly used by this simple Patcher version):*
-   `proposed_fix_strategy` (string): A textual description of the fix strategy that led to this variant.

**Example Input YAML (`patcher_input.yaml`):**
```yaml
original_source_code: |
  #include <iostream>
  int main() {
    // ... original code ...
    std::cout << "Original version" << std::endl;
    return 0;
  }
original_file_name: "my_program.cpp"
selected_variant_code: |
  #include <iostream>
  int main() {
    // ... modified code ...
    std::cout << "Patched Version - Variant Alpha" << std::endl;
    return 0;
  }
variant_id: "Alpha"
output_base_dir: "./data/sources/patched_variants"
proposed_fix_strategy: "Replaced the cout message with an updated one."
```

## Output Data (output YAML)

The agent produces an output YAML file (or dictionary) containing:

-   `patched_file_path` (string): The absolute path to the newly created patched source file. `None` if an error occurred.
-   `patcher_status` (string): Indicates the outcome, either 'success' or 'failed'.
-   `patcher_error` (string, optional): If `patcher_status` is 'failed', this field contains an error message.

**Example Output YAML (`patcher_output.yaml`):**
```yaml
patched_file_path: "/home/user/profiling-agent/data/sources/patched_variants/my_program_Alpha.cpp"
patcher_status: "success"
patcher_error: null
```

## How to Run

While the Patcher agent can be run as a standalone step using the `core.Step` CLI (by providing `--input` and `--output` YAML files), it is more commonly orchestrated as part of a larger pipeline (e.g., by an `Optimizer` pipe after a `Replicator` step).

**Standalone (less common):**
```bash
# Ensure you are in the root directory of the profiling-agent project
poetry run python -m step.patcher.patcher_agent --input step/patcher/examples/patcher_input_example.yaml --output step/patcher/examples/patcher_output_example.yaml
```

In a pipeline, the orchestrator would prepare an input dictionary with the required fields (often derived from a `Replicator`'s output) and call the `Patcher.run()` method.

## Dependencies

-   Python 3.x
-   `core.step.Step` (base class)
-   Standard Python `os` module. 