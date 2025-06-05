# AI Performance Profiling Agent for C++

This project aims to build an AI agent that uses the Linux `perf` tool to automatically:
1. Identify performance bottlenecks in a given C++ program.
2. Understand the nature of these bottlenecks.
3. Propose and apply code modifications to address them.
4. Generate multiple variants of the optimized code.
5. Test these variants using `perf` to verify performance improvements.
6. Iterate through this process 2-3 times to find the best performing version.
7. Log the entire process and its findings.

## Getting Started

### Prerequisites

- Linux environment (as `perf` is a Linux tool)
- Python (version 3.8+ recommended)
- `perf` tool installed (usually available via system package manager, e.g., `sudo apt-get install linux-tools-common linux-tools-generic`)
- A C++ compiler (e.g., `g++`)
- Poetry for dependency management (recommended)
- OpenAI API key (if using LLM-based agents like Analyzer or Replicator), set as an environment variable `OPENAI_API_KEY`.

### Installation

1.  **Set up the project:**
    Ensure you have the project files on your local system.

2.  **Install dependencies using Poetry:**
    If you don't have Poetry, install it first (see [Poetry documentation](https://python-poetry.org/docs/#installation)).
    Navigate to the project's root directory in your terminal, then run:
    ```bash
    poetry install
    ```
    This will create a virtual environment and install all necessary packages defined in `pyproject.toml`.

3.  **Verify `perf` permissions:**
    Using `perf` often requires specific permissions. You might need to adjust `perf_event_paranoid` settings:
    ```bash
    sudo sh -c 'echo -1 > /proc/sys/kernel/perf_event_paranoid'
    ```
    To make this change permanent, you'd typically modify `/etc/sysctl.conf`.
    *Note: Setting `perf_event_paranoid` to -1 is permissive; understand the security implications for your system.* Refer to `man perf_event_open` for more details.

### Basic Usage

The primary way to run the full optimization pipeline is using the Optimizer script.

1.  **Activate the Poetry virtual environment:**
    Navigate to the project's root directory in your terminal, then run:
    ```bash
    poetry shell
    ```

2.  **Prepare your C++ source code:**
    Place your C++ source files (e.g., `my_program.cpp`, `another_module.cpp`) in a directory. For example, create a directory named `my_cpp_sources` and put your files there:
    ```
    my_cpp_sources/
    ├── my_program.cpp
    └── another_module.cpp
    ```
    The Optimizer pipe will recursively find all `.cpp`, `.cc`, and `.cxx` files in the specified input directory.

3.  **Run the Optimizer pipe:**
    Use the `--input-dir` argument to specify the directory containing your C++ source files and `--output-dir` to specify where the results should be saved.
    ```bash
    poetry run python -m pipe.optimizer.optimizer --input-dir my_cpp_sources/ --output-dir optimizer_run_1
    ```
    This will run the Profiler, then Analyzer, then Replicator, Patcher, and Evaluator agents in sequence for each C++ file found in `my_cpp_sources/`.
    The Optimizer profiles the initial code, then enters an iterative loop:
    1.  **Analyzer**: Identifies bottlenecks in the (current baseline) profiled code.
    2.  **Replicator**: Generates code variants to address these bottlenecks.
    3.  **Patcher**: Writes these variants to disk.
    4.  **Profiler (for variants)**: Each successfully patched variant is compiled and profiled.
    5.  **Evaluator**: Each profiled variant is compared against the current baseline profile (initially, the original code's profile).
    If a variant shows improvement, it becomes the new baseline for the next iteration.
    The results, intermediate files, and patched variants will be saved in the `optimizer_run_1` directory.

4.  **Running individual agents:**
    Each agent in the `step/` directory can also be run individually. Refer to their respective `README.md` files (linked in the Directory Structure section) for specific instructions. These typically require a specific input YAML file.
    For example, to run the Profiler directly (which needs a profiler input YAML):
    ```bash
    poetry run python -m step.profiler.profiler_agent -o profiler_output.yaml step/profiler/examples/profiler_input.yaml
    ```

## Directory Structure

- `README.md`: This file - an overview of the project.
- `core/`: Contains core components, base classes (like `Step`), and utilities shared across the project.
- `pipe/`: Contains orchestration scripts that combine multiple steps into a pipeline.
  - [`pipe/optimizer/README.md`](pipe/optimizer/README.md): Orchestrates the Profiler, Analyzer, and Replicator agents.
- `step/`: Contains the different autonomous steps or "agents" that form the profiling and optimization pipeline. Each sub-directory typically represents a distinct stage with its own [`README.md`](step/README.md):
  - [`step/profiler/README.md`](step/profiler/README.md): Compiles the code and gathers initial `perf` data and reports.
  - [`step/analyzer/README.md`](step/analyzer/README.md): Analyzes `perf` reports (potentially using LLMs) to identify bottlenecks.
  - [`step/replicator/README.md`](step/replicator/README.md): Proposes and applies code modifications based on analysis.
  - [`step/evaluator/README.md`](step/evaluator/README.md): Evaluates the performance of modified code variants.
  - [`step/patcher/README.md`](step/patcher/README.md): Applies a selected code variant to the original source file.
- `tool/`: Contains Python wrappers and interfaces for external command-line tools used by the steps.
  - `tool/compile/`: Wrapper for the C++ compiler (e.g., `g++`).
  - `tool/perf/`: Wrapper for the Linux `perf` tool (handling `record`, `report`, etc.).
- `data/`: Contains data generated and used during the process. Subdirectories might include:
  - `data/sources/`: Input C++ source files.
