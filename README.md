# AI Performance Profiling Agent for C++

This project aims to build an AI agent that uses the Linux `perf` tool to automatically:
1. Identify performance bottlenecks in a given C++ program.
2. Understand the nature of these bottlenecks.
3. Propose and apply code modifications to address them.
4. Generate multiple variants of the optimized code.
5. Test these variants using `perf` to verify performance improvements.
6. Iterate through this process 2-3 times to find the best performing version.
7. Log the entire process and its findings.

## Directory Structure

- `README.md`: This file - an overview of the project.
- `core/`: Contains core components, base classes (like `Step`), and utilities shared across the project.
- `pipe/`: Contains orchestration scripts that combine multiple steps into a pipeline.
  - [`pipe/optimizer/README.md`](pipe/optimizer/README.md): Orchestrates the Profiler, Analyzer, and Replicator agents.
- `step/`: Contains the different autonomous steps or "agents" that form the profiling and optimization pipeline. Each sub-directory typically represents a distinct stage with its own `README.md`:
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
