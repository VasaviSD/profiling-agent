# Tools, C++ Sources, and Profiling Data

This directory serves as a workspace for the C++ code being profiled and the data generated during the performance analysis process.

## Subdirectories:

- `cpp_sources/`: Contains the target C++ source files that the AI agent will analyze and optimize.
- `compile/`: Stores compiled executables of the C++ programs from the `cpp_sources/` directory. These are the binaries that `perf` will be run against.
- `perf/`: Stores output data from the `perf` tool, such as `perf.data` files and generated reports or scripts.
