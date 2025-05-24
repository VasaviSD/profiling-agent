#!/usr/bin/env python3
# See LICENSE for details

import argparse
import os
import sys
import time

# Add project root to sys.path to allow direct imports of step and core modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from core.utils import read_yaml, write_yaml
    from step.profiler.profiler_agent import Profiler
    from step.analyzer.analyzer_agent import Analyzer
    from step.replicator.replicator_agent import Replicator
except ImportError as e:
    print(f"Error: Could not import necessary modules. Ensure CWD is in the project root, or that PYTHONPATH is set correctly. Details: {e}")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Orchestrates a C++ performance optimization pipeline (Optimizer Pipe) using Profiler, Analyzer, and Replicator agents.")
    parser.add_argument("--profiler-input-yaml", required=True, help="Path to the input YAML file for the Profiler step (e.g., containing source_dir).")
    parser.add_argument("--output-dir", required=True, help="Directory to store all intermediate and final outputs.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of optimization iterations (Profiler -> Analyzer -> Replicator -> [future Evaluator -> Profiler cycle]). Currently supports 1 full pass.")

    args = parser.parse_args()

    # --- Create output directory ---
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        print(f"Created output directory: {args.output_dir}")
    else:
        print(f"Output directory already exists: {args.output_dir}")

    # --- Orchestration ---
    pipeline_start_time = time.time()
    current_profiler_input_yaml = args.profiler_input_yaml

    for i in range(args.iterations):
        iteration = i + 1
        print(f"\n=== Starting Optimizer Pipeline Iteration: {iteration}/{args.iterations} ===")

        profiler_output_path = os.path.join(args.output_dir, f"profiler_output_iter{iteration}.yaml")
        analyzer_output_path = os.path.join(args.output_dir, f"analyzer_output_iter{iteration}.yaml")
        replicator_output_path = os.path.join(args.output_dir, f"replicator_output_iter{iteration}.yaml")

        try:
            print(f"\n--- Running Profiler Step (Iteration {iteration}) ---")
            profiler_input_data = read_yaml(current_profiler_input_yaml) 
            if not profiler_input_data:
                print(f"Error: Could not read/parse Profiler input YAML: {current_profiler_input_yaml} for iteration {iteration}")
                break 
            
            profiler = Profiler()
            profiler.set_io(current_profiler_input_yaml, profiler_output_path)
            profiler.setup()
            profiler_output_data = profiler.run(profiler_input_data)
            
            if profiler_output_data.get('profiler_error'):
                print(f"Error in Profiler (iter {iteration}): {profiler_output_data['profiler_error']}")
                break 
            write_yaml(profiler_output_data, profiler_output_path)
            print(f"Profiler (iter {iteration}) completed. Output: {profiler_output_path}")

            print(f"\n--- Running Analyzer Step (Iteration {iteration}) ---")
            analyzer = Analyzer()
            analyzer.set_io(profiler_output_path, analyzer_output_path)
            analyzer.setup()
            analyzer_output_data = analyzer.run(profiler_output_data)
            if not analyzer_output_data.get('performance_analysis'):
                 print(f"Error: Analyzer (iter {iteration}) produced no 'performance_analysis'.")
                 break 
            write_yaml(analyzer_output_data, analyzer_output_path)
            print(f"Analyzer (iter {iteration}) completed. Output: {analyzer_output_path}")

            print(f"\n--- Running Replicator Step (Iteration {iteration}) ---")
            replicator = Replicator()
            replicator.set_io(analyzer_output_path, replicator_output_path)
            replicator.setup()
            replicator_output_data = replicator.run(analyzer_output_data)
            if replicator_output_data.get('replication_error'):
                 print(f"Error in Replicator (iter {iteration}): {replicator_output_data['replication_error']}")
                 break
            elif not replicator_output_data.get('modified_code_variants'):
                print(f"Warning/Error: Replicator (iter {iteration}) produced no 'modified_code_variants'.")
            write_yaml(replicator_output_data, replicator_output_path)
            print(f"Replicator (iter {iteration}) completed. Output: {replicator_output_path}")

            if iteration < args.iterations:
                print(f"Iteration {iteration} finished. Multi-iteration source update logic TBD.")

        except Exception as e:
            print(f"Pipeline error (iteration {iteration}): {e}")
            import traceback
            traceback.print_exc()
            break 
    
    pipeline_end_time = time.time()
    print(f"\nOptimizer Pipeline finished in {(pipeline_end_time - pipeline_start_time):.2f}s. Outputs in: {args.output_dir}")

if __name__ == "__main__":
    main() 