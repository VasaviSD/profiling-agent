# C++ Profiler Agent

## Overview

The Profiler agent is a Python-based tool responsible for the initial stages of performance analysis for C++ code. It takes C++ source files from a directory (if compilation is needed), or uses a pre-compiled executable. It then runs the Linux `perf` tool to collect performance data, generates a textual `perf report`, and selects the report from a preferred preset to output.
If a pre-compiled executable is provided via the input YAML, the compilation step is skipped, and the agent proceeds directly to profiling that executable.

This agent acts as the first step in a typical analysis pipeline, preparing the necessary performance data (a selected `perf report` and the command used to generate it) for downstream agents like the `Analyzer`.

## Functionality

-   **Input Processing:** Reads configuration from an input YAML file. This includes the path to the C++ source directory (used for compilation if no executable is provided) and optional parameters for compilation, `perf record`, and output selection. If an `executable` path is provided, compilation is skipped.
-   **Multi-Preset Compilation (Optional):** If no pre-compiled executable is given, it compiles the C++ source files from `source_dir` using different optimization presets (e.g., debug, optimized, debug-optimized). It uses the `CppCompiler` tool.
-   **Perf Record:** For each successfully compiled executable (or a provided one), it executes `perf record` to gather performance profiling data. It uses the `PerfTool`.
-   **Perf Report:** For each successful `perf record`, it executes `perf report --stdio` to produce a human-readable textual summary of the performance profile using `PerfTool`.
-   **Preferred Output Selection:** Selects the `perf record` command and `perf report` output from a "preferred" optimization preset (defaulting to 'opt_only' or the first successful one if the preferred fails).
-   **Structured Output:** Produces a YAML output file containing the fields listed in the "Output Data" section below.

## Input Data (from input YAML)

This section mirrors the `Reads from:` section of the agent's docstring.
The agent expects an input YAML file specified via the `--input` command-line argument, containing the following keys:

-   `source_dir`: str (Path to the directory containing .cpp, .hpp, .h source files. Used for compilation if 'executable' is not provided. Still required even if 'executable' is provided, for context, though not directly output by this agent.)
-   `perf_record_args` (optional): list[str] (Base arguments for 'perf record')
-   `target_args` (optional): list[str] (Arguments for the compiled executable)
-   `base_executable_name` (optional): str (Base name for executables, defaults to 'a.out')
-   `base_perf_data_name` (optional): str (Base name for perf data, defaults to 'perf')
-   `compile_output_dir` (optional): str (Directory for executables, defaults './data/compile')
-   `perf_output_dir` (optional): str (Directory for perf.data files, defaults './data/perf')
-   `preferred_preset` (optional): str (Preset to prioritize for output, defaults 'opt_only')
-   `executable` (optional): str (Path to a pre-compiled executable. If provided, compilation is skipped. `source_dir` is still required for context but its content is not output by this agent.)

**Example Input YAML (`profiler_input.yaml`):**
```yaml
source_dir: "./projects/my_cpp_project/src"
# To compile the code:
# perf_record_args: ["-g", "-F", "99"]
# target_args: ["--input", "data/input.txt", "--iterations", "100"]
# preferred_preset: "opt_only"
# compile_output_dir: "./output_binaries"
# perf_output_dir: "./output_perf_data"

# To use a pre-compiled executable:
executable: "./precompiled_binaries/my_app"
perf_record_args: ["-g", "-F", "99"]
target_args: ["--input", "data/input.txt", "--iterations", "100"]
perf_output_dir: "./output_perf_data_direct" # source_dir is still required for context by the agent, even if not used for compilation here.
```

## Output Data (output YAML for Analyzer)

This section mirrors the `Emits:` section of the agent's docstring.
The agent produces an output YAML file specified via the `--output` command-line argument. This file is structured to be directly consumable by the `Analyzer` agent and contains:

-   `perf_command`: str (The specific perf record command used for the selected report)
-   `perf_report_output`: str (The textual output from perf report for the selected run)
-   `profiler_error` (optional): str (Error message if profiling failed critically)
-   `profiling_details` (optional): dict (Detailed results for all presets, for debugging)

**Example Output YAML (`profiler_output.yaml` for Analyzer):**
```yaml
perf_command: "perf record -g -F 99 -o data/perf/perf_opt_only.data -- ./data/compile/a.out_opt_only --input data/input.txt --iterations 100"
perf_report_output: |
  # Children      Self  Command          Shared Object         Symbol
  # ........  ........  ...............  ....................  ..................................
  #
    98.76%    98.70%  a.out_opt_only   a.out_opt_only        [.] intensive_function
  # ... (rest of perf report) ...
profiler_error: null
profiling_details:
  opt_only:
    status: "success"
    compile: { ... }
    perf_record: { ... }
    perf_report: { ... }
  debug_opt:
    status: "success"
    # ... details ...
  debug_only:
    status: "compile_failed"
    # ... details ...
```

## How to Run

The Profiler agent is run from the command line using the `Step` class's argument parsing. You need to provide paths for an input YAML configuration file and an output YAML file.

```bash
python -m step.profiler.profiler_agent --input <path_to_input_yaml> --output <path_to_output_yaml>
```

**Example:**

Assuming your input YAML is `step/profiler/examples/profiler_input.yaml` and you want the output in `step/profiler/examples/profiler_output.yaml`:

```bash
# Make sure you are in the root directory of the profiling-agent project
poetry run python -m step.profiler.profiler_agent -o step/profiler/examples/profiler_output.yaml step/profiler/examples/profiler_input.yaml
```

This command will read settings from `profiler_input.yaml`, compile the C++ code from the specified `source_dir` with different presets, run `perf record` and `perf report` for each, select the output from the preferred preset, and save the results to `profiler_output.yaml`.

## Dependencies

-   Python 3.x
-   A C++ compiler (e.g., `g++`) accessible in the system PATH (used by `CppCompiler` tool).
-   The Linux `perf` tool accessible in the system PATH (used by `PerfTool`).
-   Core modules of the `profiling-agent` project (e.g., `core.step.Step`).
-   The `CppCompiler` tool (from `tool.compile.cpp_compiler`).
-   The `PerfTool` (from `tool.perf.perf_tool`).

## Note on Tools

This agent relies on external tool wrappers: `tool.compile.cpp_compiler.CppCompiler` for C++ compilation and `tool.perf.perf_tool.PerfTool` for `perf` execution (record and report). Ensure these tools are correctly implemented and available.
