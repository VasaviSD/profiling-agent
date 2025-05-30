#!/usr/bin/env python3
# See LICENSE for details

import argparse
import os
import sys
import time
import glob # For finding files
import shutil # For copying files for variant profiling

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
        cpp_files.extend(glob.glob(os.path.join(input_dir, '**', pattern), recursive=True))
    return cpp_files

def main():
    parser = argparse.ArgumentParser(description="Orchestrates a C++ performance optimization pipeline (Optimizer Pipe) for C++ files in an input directory.")
    parser.add_argument("--input-dir", required=True, help="Directory containing C++ source files to process.")
    parser.add_argument("--output-dir", required=True, help="Main directory to store all intermediate and final outputs.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of optimization iterations (Profiler -> Analyzer -> Replicator -> Patcher -> Profile Variants) per C++ file.")

    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"Error: Input directory not found or is not a directory: {args.input_dir}")
        sys.exit(1)

    cpp_files_to_process = find_cpp_files(args.input_dir)
    if not cpp_files_to_process:
        print(f"No C++ files (.cpp, .cc, .cxx) found in {args.input_dir} to process.")
        sys.exit(0)
    
    print(f"Found {len(cpp_files_to_process)} C++ files to process: {cpp_files_to_process}")

    pipeline_overall_start_time = time.time()
    # Create a single Patcher instance to use its _sanitize_filename method if needed
    # This instance is not run in the main loop here, but used for utility.
    # The actual Patcher runs happen per iteration.
    utility_patcher_instance = Patcher()

    for current_source_file_abs_path in cpp_files_to_process:
        original_file_name = os.path.basename(current_source_file_abs_path)
        source_file_dir = os.path.dirname(current_source_file_abs_path)
        relative_path_from_input = os.path.relpath(current_source_file_abs_path, args.input_dir)
        sanitized_relative_path_for_output = os.path.splitext(relative_path_from_input)[0].replace(os.sep, '_')
        
        file_specific_output_dir = os.path.join(args.output_dir, sanitized_relative_path_for_output)
        if not os.path.exists(file_specific_output_dir):
            os.makedirs(file_specific_output_dir)
        
        print(f"\nProcessing file: {current_source_file_abs_path}")
        print(f"Outputs for this file will be in: {file_specific_output_dir}")

        profiler_input_for_initial_run_data = {'source_dir': source_file_dir}
        current_initial_profiler_input_yaml = os.path.join(file_specific_output_dir, f"profiler_input_initial_{original_file_name}.yaml")
        write_yaml(profiler_input_for_initial_run_data, current_initial_profiler_input_yaml)

        for i in range(args.iterations):
            iteration = i + 1
            print(f"\n=== Starting Optimizer Pipeline Iteration: {iteration}/{args.iterations} for file: {original_file_name} ===")

            iter_output_dir = os.path.join(file_specific_output_dir, f"iter_{iteration}")
            if not os.path.exists(iter_output_dir):
                os.makedirs(iter_output_dir)

            profiler_output_path = os.path.join(iter_output_dir, f"profiler_output.yaml")
            analyzer_output_path = os.path.join(iter_output_dir, f"analyzer_output.yaml")
            replicator_output_path = os.path.join(iter_output_dir, f"replicator_output.yaml")
            patcher_output_path = os.path.join(iter_output_dir, f"patcher_output.yaml")

            current_profiler_input_yaml_for_iteration = current_initial_profiler_input_yaml 

            try:
                print(f"\n--- Running Initial Profiler Step (Iteration {iteration}) for {original_file_name} ---")
                profiler_input_disk_data = read_yaml(current_profiler_input_yaml_for_iteration)
                if not profiler_input_disk_data:
                    print(f"Error: Could not read/parse Profiler input YAML: {current_profiler_input_yaml_for_iteration}")
                    break 
                
                profiler = Profiler()
                profiler.set_io(current_profiler_input_yaml_for_iteration, profiler_output_path)
                profiler.setup()
                profiler_output_data = profiler.run(profiler_input_disk_data)
                
                if profiler_output_data.get('profiler_error'):
                    print(f"Error in Initial Profiler (iter {iteration}, file {original_file_name}): {profiler_output_data['profiler_error']}")
                    break 
                write_yaml(profiler_output_data, profiler_output_path)
                print(f"Initial Profiler (iter {iteration}, file {original_file_name}) completed. Output: {profiler_output_path}")

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
                    print(f"Warning: Replicator (iter {iteration}, file {original_file_name}) produced no 'modified_code_variants'.")
                write_yaml(replicator_output_data, replicator_output_path)
                print(f"Replicator (iter {iteration}, file {original_file_name}) completed. Output: {replicator_output_path}")

                print(f"\n--- Running Patcher Step (Iteration {iteration}) for {original_file_name} ---")
                actual_patcher_instance = Patcher() # Instance for this specific Patcher run
                if not replicator_output_data.get('modified_code_variants'):
                    print(f"Skipping Patcher for iter {iteration}, file {original_file_name} as Replicator produced no 'modified_code_variants'.")
                    patcher_output_data = replicator_output_data.copy() 
                    patcher_output_data['patcher_status'] = 'skipped_no_variants'
                else:
                    patcher_input_data_for_run = replicator_output_data.copy()
                    patcher_input_data_for_run['original_file_name'] = original_file_name
                    
                    actual_patcher_instance.set_io(replicator_output_path, patcher_output_path) 
                    actual_patcher_instance.setup()
                    patcher_output_data = actual_patcher_instance.run(patcher_input_data_for_run)
                    
                    write_yaml(patcher_output_data, patcher_output_path)
                    print(f"Patcher (iter {iteration}, file {original_file_name}) completed. Output YAML: {patcher_output_path}")
                    if patcher_output_data.get('patcher_overall_error') or patcher_output_data.get('patcher_status') == 'all_failed':
                        print(f"Warning/Error in Patcher (iter {iteration}, file {original_file_name}): {patcher_output_data.get('patcher_overall_error', 'Patcher status was all_failed.')}")
                
                print(f"\n--- Profiling Patched Variants (Iteration {iteration}, File {original_file_name}) ---")
                if patcher_output_data.get('patcher_status') not in ['all_success', 'partial_success'] or not patcher_output_data.get('patched_variants_results'):
                    print(f"Patcher did not write files successfully or produced no results for iter {iteration}, file {original_file_name}. Skipping profiling of patched variants.")
                else:
                    successful_written_variants_sources = []
                    for variant_res in patcher_output_data.get('patched_variants_results', []):
                        # Only check if Patcher successfully WROTE the variant source file
                        if variant_res.get('status') == 'success' and variant_res.get('patched_file_path'): 
                            successful_written_variants_sources.append({
                                'variant_id': variant_res.get('variant_id'),
                                'source_path': variant_res.get('patched_file_path') # This is the source path written by Patcher
                            })

                    if not successful_written_variants_sources:
                        print(f"No successfully written variant source files to profile for iter {iteration}, file {original_file_name}.")
                    else:
                        print(f"Found {len(successful_written_variants_sources)} successfully written variant source files to profile for iter {iteration}, file {original_file_name}.")
                        
                        for var_info in successful_written_variants_sources:
                            variant_id = var_info['variant_id']
                            patched_variant_source_path = var_info['source_path']
                            # Use the utility_patcher_instance for _sanitize_filename
                            sanitized_variant_id = utility_patcher_instance._sanitize_filename(variant_id).lower()

                            print(f"\n  --- Profiling Patched Variant Source: {variant_id} (File: {original_file_name}, Iter: {iteration}) ---")

                            variant_profiler_run_base_dir = os.path.join(iter_output_dir, f"profiler_run_variant_{sanitized_variant_id}")
                            variant_profiler_src_dir = os.path.join(variant_profiler_run_base_dir, "src")
                            if not os.path.exists(variant_profiler_src_dir):
                                os.makedirs(variant_profiler_src_dir)

                            target_source_in_profiler_dir = os.path.join(variant_profiler_src_dir, original_file_name)
                            shutil.copy(patched_variant_source_path, target_source_in_profiler_dir)
                            print(f"    Copied patched source {patched_variant_source_path} to {target_source_in_profiler_dir}")

                            variant_profiler_input_data = {'source_dir': variant_profiler_src_dir}
                            variant_profiler_input_yaml_path = os.path.join(variant_profiler_run_base_dir, f"profiler_input_variant_{sanitized_variant_id}.yaml")
                            write_yaml(variant_profiler_input_data, variant_profiler_input_yaml_path)

                            variant_profiler_output_yaml_path = os.path.join(variant_profiler_run_base_dir, f"profiler_output_variant_{sanitized_variant_id}.yaml")

                            try:
                                variant_profiler = Profiler()
                                variant_profiler.set_io(variant_profiler_input_yaml_path, variant_profiler_output_yaml_path)
                                variant_profiler.setup()
                                profiler_input_for_variant_run = read_yaml(variant_profiler_input_yaml_path)
                                if not profiler_input_for_variant_run:
                                    print(f"    Error reading profiler input for variant {variant_id}. Skipping.")
                                    continue
                                
                                variant_profiler_output = variant_profiler.run(profiler_input_for_variant_run)
                                
                                if variant_profiler_output.get('profiler_error'):
                                    print(f"    Error during Profiler run for variant {variant_id}: {variant_profiler_output['profiler_error']}")
                                else:
                                    print(f"    Profiler run for variant {variant_id} completed.")
                                write_yaml(variant_profiler_output, variant_profiler_output_yaml_path)
                                print(f"    Profiler output for variant {variant_id} saved to: {variant_profiler_output_yaml_path}")

                            except Exception as e_var_prof:
                                print(f"    Error during profiling setup/run for variant {variant_id}: {e_var_prof}")
                                import traceback
                                traceback.print_exc()
                                continue 

                if iteration < args.iterations:
                    print(f"Iteration {iteration} for file {original_file_name} finished. Multi-iteration source update logic TBD.")

            except Exception as e:
                print(f"Pipeline error (iteration {iteration}, file {original_file_name}): {e}")
                import traceback
                traceback.print_exc()
                break 
        
        print(f"Completed all iterations for file: {current_source_file_abs_path}")
    
    pipeline_overall_end_time = time.time()
    print(f"\nOptimizer Pipeline finished processing all files in {(pipeline_overall_end_time - pipeline_overall_start_time):.2f}s. Outputs in: {args.output_dir}")

if __name__ == "__main__":
    main() 