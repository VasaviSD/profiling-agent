#!/usr/bin/env python3
# See LICENSE for details

import argparse
import os
import sys
import time
import glob # For finding files

# Add project root to sys.path to allow direct imports of step and core modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from core.utils import read_yaml, write_yaml
    from step.profiler.profiler_agent import Profiler
    from step.analyzer.analyzer_agent import Analyzer
    from step.replicator.replicator_agent import Replicator
    from step.patcher.patcher_agent import Patcher
except ImportError as e:
    print(f"Error: Could not import necessary modules. Ensure CWD is in the project root, or that PYTHONPATH is set correctly. Details: {e}")
    sys.exit(1)

def find_cpp_files(input_dir):
    """Recursively finds C++ implementation files (.cpp, .cc, .cxx) in the input directory."""
    patterns = ['*.cpp', '*.cc', '*.cxx']
    cpp_files = []
    for pattern in patterns:
        # Using os.path.join for correct path construction and recursive glob
        cpp_files.extend(glob.glob(os.path.join(input_dir, '**', pattern), recursive=True))
    return cpp_files

def main():
    parser = argparse.ArgumentParser(description="Orchestrates a C++ performance optimization pipeline (Optimizer Pipe) for C++ files in an input directory.")
    parser.add_argument("--input-dir", required=True, help="Directory containing C++ source files to process.")
    parser.add_argument("--output-dir", required=True, help="Main directory to store all intermediate and final outputs.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of optimization iterations (Profiler -> Analyzer -> Replicator -> Patcher) per C++ file.")

    args = parser.parse_args()

    # --- Validate input directory ---
    if not os.path.isdir(args.input_dir):
        print(f"Error: Input directory not found or is not a directory: {args.input_dir}")
        sys.exit(1)

    # --- Discover C++ files ---
    cpp_files_to_process = find_cpp_files(args.input_dir)
    if not cpp_files_to_process:
        print(f"No C++ files (.cpp, .cc, .cxx) found in {args.input_dir} to process.")
        sys.exit(0)
    
    print(f"Found {len(cpp_files_to_process)} C++ files to process: {cpp_files_to_process}")

    # --- Main Orchestration Loop (Outer: per C++ file) ---
    pipeline_start_time = time.time()

    for current_source_file_abs_path in cpp_files_to_process:
        original_file_name = os.path.basename(current_source_file_abs_path)
        source_file_dir = os.path.dirname(current_source_file_abs_path)
        relative_path_from_input = os.path.relpath(current_source_file_abs_path, args.input_dir)
        # Sanitize relative path for directory creation (remove extension, replace slashes if needed)
        sanitized_relative_path_for_output = os.path.splitext(relative_path_from_input)[0].replace(os.sep, '_')
        
        file_specific_output_dir = os.path.join(args.output_dir, sanitized_relative_path_for_output)
        if not os.path.exists(file_specific_output_dir):
            os.makedirs(file_specific_output_dir)
        
        print(f"\nProcessing file: {current_source_file_abs_path}")
        print(f"Outputs for this file will be in: {file_specific_output_dir}")

        # Dynamically create profiler input YAML for the current file's directory
        profiler_input_for_file_data = {'source_dir': source_file_dir}
        current_profiler_input_yaml = os.path.join(file_specific_output_dir, f"profiler_input_for_{original_file_name}.yaml")
        write_yaml(profiler_input_for_file_data, current_profiler_input_yaml)

        # --- Inner Loop: Optimization Iterations for the current file ---
        for i in range(args.iterations):
            iteration = i + 1
            print(f"\n=== Starting Optimizer Pipeline Iteration: {iteration}/{args.iterations} for file: {original_file_name} ===")

            profiler_output_path = os.path.join(file_specific_output_dir, f"profiler_output_iter{iteration}.yaml")
            analyzer_output_path = os.path.join(file_specific_output_dir, f"analyzer_output_iter{iteration}.yaml")
            replicator_output_path = os.path.join(file_specific_output_dir, f"replicator_output_iter{iteration}.yaml")
            patcher_output_path = os.path.join(file_specific_output_dir, f"patcher_output_iter{iteration}.yaml")

            try:
                print(f"\n--- Running Profiler Step (Iteration {iteration}) for {original_file_name} ---")
                # Profiler input data is already written to current_profiler_input_yaml
                profiler_input_disk_data = read_yaml(current_profiler_input_yaml) 
                if not profiler_input_disk_data:
                    print(f"Error: Could not read/parse dynamically created Profiler input YAML: {current_profiler_input_yaml}")
                    break # Break from inner loop (iterations for this file)
                
                profiler = Profiler()
                profiler.set_io(current_profiler_input_yaml, profiler_output_path)
                profiler.setup()
                profiler_output_data = profiler.run(profiler_input_disk_data)
                
                if profiler_output_data.get('profiler_error'):
                    print(f"Error in Profiler (iter {iteration}, file {original_file_name}): {profiler_output_data['profiler_error']}")
                    break 
                write_yaml(profiler_output_data, profiler_output_path)
                print(f"Profiler (iter {iteration}, file {original_file_name}) completed. Output: {profiler_output_path}")

                print(f"\n--- Running Analyzer Step (Iteration {iteration}) for {original_file_name} ---")
                analyzer = Analyzer()
                analyzer.set_io(profiler_output_path, analyzer_output_path)
                analyzer.setup()
                analyzer_output_data = analyzer.run(profiler_output_data)
                if not analyzer_output_data.get('performance_analysis'):
                    print(f"Error: Analyzer (iter {iteration}, file {original_file_name}) produced no 'performance_analysis'.")
                    break 
                write_yaml(analyzer_output_data, analyzer_output_path)
                print(f"Analyzer (iter {iteration}, file {original_file_name}) completed. Output: {analyzer_output_path}")

                print(f"\n--- Running Replicator Step (Iteration {iteration}) for {original_file_name} ---")
                replicator = Replicator()
                replicator.set_io(analyzer_output_path, replicator_output_path)
                replicator.setup()
                replicator_output_data = replicator.run(analyzer_output_data)
                if replicator_output_data.get('replication_error'):
                    print(f"Error in Replicator (iter {iteration}, file {original_file_name}): {replicator_output_data['replication_error']}")
                    break
                elif not replicator_output_data.get('modified_code_variants'):
                    print(f"Warning/Error: Replicator (iter {iteration}, file {original_file_name}) produced no 'modified_code_variants'.")
                write_yaml(replicator_output_data, replicator_output_path)
                print(f"Replicator (iter {iteration}, file {original_file_name}) completed. Output: {replicator_output_path}")

                print(f"\n--- Running Patcher Step (Iteration {iteration}) for {original_file_name} ---")
                if not replicator_output_data.get('modified_code_variants'):
                    print(f"Skipping Patcher for iter {iteration}, file {original_file_name} as Replicator produced no 'modified_code_variants'.")
                else:
                    patcher_input_data_for_run = replicator_output_data.copy()
                    patcher_input_data_for_run['original_file_name'] = original_file_name # Use the file name from the outer loop
                    
                    patcher = Patcher()
                    patcher.set_io(replicator_output_path, patcher_output_path) 
                    patcher.setup()
                    patcher_output_data = patcher.run(patcher_input_data_for_run)
                    
                    write_yaml(patcher_output_data, patcher_output_path)
                    print(f"Patcher (iter {iteration}, file {original_file_name}) completed. Output YAML: {patcher_output_path}")
                    if patcher_output_data.get('patcher_overall_error') or patcher_output_data.get('patcher_status') == 'all_failed':
                        print(f"Warning/Error in Patcher (iter {iteration}, file {original_file_name}): {patcher_output_data.get('patcher_overall_error', 'Patcher status was all_failed.')}")

                if iteration < args.iterations:
                    print(f"Iteration {iteration} for file {original_file_name} finished. Multi-iteration source update logic TBD.")

            except Exception as e:
                print(f"Pipeline error (iteration {iteration}, file {original_file_name}): {e}")
                import traceback
                traceback.print_exc()
                break # Break from inner loop (iterations for this file)
        
        print(f"Completed all iterations for file: {current_source_file_abs_path}")
    
    pipeline_end_time = time.time()
    print(f"\nOptimizer Pipeline finished processing all files in {(pipeline_end_time - pipeline_start_time):.2f}s. Outputs in: {args.output_dir}")

if __name__ == "__main__":
    main() 