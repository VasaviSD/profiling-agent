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
- `step/`: Contains the different autonomous steps or "agents" that form the profiling and optimization pipeline. Each sub-directory typically represents a distinct stage:
  - `step/profiler/`: Compiles the code and gathers initial `perf` data and reports.
  - `step/analyzer/`: Analyzes `perf` reports (potentially using LLMs) to identify bottlenecks.
  - `step/replicator/`: Proposes and applies code modifications based on analysis.
  - `step/evaluator/`: Evaluates the performance of modified code variants.
- `tool/`: Contains Python wrappers and interfaces for external command-line tools used by the steps.
  - `tool/compile/`: Wrapper for the C++ compiler (e.g., `g++`).
  - `tool/perf/`: Wrapper for the Linux `perf` tool (handling `record`, `report`, etc.).
- `data/`: Contains data generated and used during the process. Subdirectories might include:
  - `data/sources/`: Input C++ source files.
