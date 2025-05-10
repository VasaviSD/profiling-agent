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
- `agent/`: Contains the Python source code for the AI agent.
- `tool/`: Contains tools, C++ source code for profiling, compilation outputs, and `perf` results.
  - `tool/cpp_sources/`: Target C++ source files for performance analysis.
  - `tool/compile/`: Stores compiled executables of the C++ programs.
  - `tool/perf/`: Stores `perf` data files and reports generated during analysis.
- `.git/`: Git version control files.
- `.gitignore`: Specifies intentionally untracked files that Git should ignore.
