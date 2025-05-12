# Linux Perf Utilities

## Overview

This directory (`tool/perf/`) is dedicated to Python scripts and modules that serve as wrappers or helpers for interacting with the Linux `perf` performance analysis tool. These utilities are crucial for agents in the profiling pipeline that need to collect performance data or process `perf` output.

## Purpose

The `perf` utilities aim to:

-   **Automate Profiling:** Provide functions to programmatically execute `perf record` with appropriate arguments to profile C++ executables. This includes setting event types (e.g., CPU cycles, cache misses), sampling frequency, call graph collection method (e.g., DWARF, LBR), and output file paths.
-   **Standardize Data Collection:** Ensure consistent `perf` data collection across different runs or for different code variants.
-   **Process `perf` Output:** Offer tools to parse the output of `perf report` or `perf script`, or to process the binary `perf.data` files if needed. This allows agents to extract structured information from `perf` results.
-   **Simplify `perf` Interaction:** Abstract the command-line complexities of `perf` and provide a more Python-friendly interface for the agents.

## Potential Functionality

Key functionalities that might be implemented in this directory include:

-   A Python function or class to run `perf record`:
    -   Takes the path to an executable, desired `perf` arguments (events, frequency, call graph type), and an output path for `perf.data` as input.
    -   Executes `perf record` using `subprocess.run()`.
    -   Handles errors and returns a status.
-   A Python function or class to run `perf report` or `perf script`:
    -   Takes a `perf.data` file as input.
    -   Executes `perf report --stdio` (or `perf script`) to generate a textual representation of the profiling data.
    -   Captures and returns the textual output.
-   Potentially, parsers for specific `perf report` formats if the agents need more structured data than the raw text.

## Usage Example (Conceptual)

An `Analyzer` agent or a dedicated `Profiler` agent might use these tools:

```python
# Conceptual usage within an agent
from tool.perf.perf_runner import PerfRunner # Assuming a PerfRunner class exists

profiler = PerfRunner(default_perf_events=['cycles', 'cache-misses'])
executable_path = './my_compiled_program'
perf_data_file = 'perf.data'

# Record performance data
record_success, stderr = profiler.record(executable_path, output_file=perf_data_file, record_args=['-g', '-F', '99'])

if record_success:
    print(f"Successfully recorded perf data to {perf_data_file}")
    
    # Generate a textual report
    report_success, report_text, report_stderr = profiler.report(perf_data_file, report_args=['--stdio'])
    if report_success:
        print("Perf Report:\n", report_text)
        # Pass report_text to an LLM or further parsing logic
    else:
        print(f"Failed to generate perf report: {report_stderr}")
else:
    print(f"Perf recording failed: {stderr}")
```

## Note

This README describes the *intended* purpose and potential functionality. The actual tools and their specific APIs would be defined by the Python modules implemented within this directory.
