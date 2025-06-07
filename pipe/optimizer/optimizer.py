#!/usr/bin/env python3
# See LICENSE for details

import argparse
import os
import sys
import time
import glob
import shutil
import json # For structured printing if needed
from collections import defaultdict

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
    from step.evaluator.evaluator_agent import Evaluator
except ImportError as e:
    print(f"Error: Could not import necessary modules. Ensure CWD is in the project root, or that PYTHONPATH is set correctly. Details: {e}")
    sys.exit(1)

def find_cpp_source_files(directory):
    """Finds C++ implementation files (.cpp, .cc, .cxx) and header files (.h, .hpp, .hxx) 
       in the given directory (non-recursive)."""
    patterns = ['*.cpp', '*.cc', '*.cxx', '*.h', '*.hpp', '*.hxx']
    cpp_files = []
    for pattern in patterns:
        cpp_files.extend(glob.glob(os.path.join(directory, pattern)))
    return sorted(list(set(cpp_files)))

def main():
    parser = argparse.ArgumentParser(description="Orchestrates a C++ performance optimization pipeline (Optimizer Pipe).")
    parser.add_argument("--source-dir", required=True, help="Directory containing C++ source files for the target executable.")
    parser.add_argument("--executable", required=True, help="Path to the pre-compiled C++ executable to profile initially.")
    parser.add_argument("--output-dir", required=True, help="Main directory to store all intermediate and final outputs.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of optimization iterations per C++ file.")

    args = parser.parse_args()

    if not os.path.isdir(args.source_dir):
        print(f"Error: Source directory not found or is not a directory: {args.source_dir}")
        sys.exit(1)
    if not os.path.isfile(args.executable):
        print(f"Error: Executable not found or is not a file: {args.executable}")
        sys.exit(1)
    
    os.makedirs(args.output_dir, exist_ok=True)
    pipeline_overall_start_time = time.time()
    utility_patcher_instance = Patcher() # For _sanitize_filename

    # --- Step 1: Initial Global Profiler Run --- 
    print(f"\n=== Step 1: Running Initial Global Profiler for executable: {args.executable} with sources in {args.source_dir} ===")
    global_profiler_input_data = {
        'source_dir': args.source_dir,
        'executable': args.executable
    }
    global_profiler_input_yaml_path = os.path.join(args.output_dir, "global_profiler_input.yaml")
    global_profiler_output_yaml_path = os.path.join(args.output_dir, "global_profiler_output.yaml")
    write_yaml(global_profiler_input_data, global_profiler_input_yaml_path)

    initial_profiler = Profiler()
    initial_profiler.set_io(global_profiler_input_yaml_path, global_profiler_output_yaml_path)
    initial_profiler.setup()
    global_profiler_output_data = initial_profiler.run(global_profiler_input_data)

    if global_profiler_output_data.get('profiler_error'):
        print(f"Error in Initial Global Profiler: {global_profiler_output_data['profiler_error']}")
        sys.exit(1)
    write_yaml(global_profiler_output_data, global_profiler_output_yaml_path)
    print(f"Initial Global Profiler completed. Output: {global_profiler_output_yaml_path}")

    cpp_files_to_process = find_cpp_source_files(args.source_dir)
    if not cpp_files_to_process:
        print(f"No C++ source or header files (.cpp, .cc, .cxx, .h, .hpp, .hxx) found directly in {args.source_dir} to process.")
        sys.exit(0)
    print(f"\nFound {len(cpp_files_to_process)} C++ source/header files in {args.source_dir} to process individually: {cpp_files_to_process}")

    # Place these before the main iterations loop
    overall_best = {
        'iteration': None,
        'variant_id': None,
        'improvement_percentage': float('-inf'),
        'file': None
    }
    iteration_summaries = []
    
    for i in range(args.iterations):
        
        iteration = i + 1
        # --- Step 2: Loop through each discovered C++ source file --- 
        print(f"\n=== Step 2: Processing each C++ source file for optimization iterations (Iteration {iteration}) ===")

        iter_output_dir_for_file = os.path.join(args.output_dir, f"iter_{iteration}")
        if not os.path.exists(iter_output_dir_for_file):
            os.makedirs(iter_output_dir_for_file)

        for current_source_file_abs_path in cpp_files_to_process:

            original_file_name = os.path.basename(current_source_file_abs_path)
            
            file_specific_output_base_dir = os.path.join(iter_output_dir_for_file, original_file_name)
            if not os.path.exists(file_specific_output_base_dir):
                os.makedirs(file_specific_output_base_dir)

            print(f"\n  >>> Processing C++ source file: {current_source_file_abs_path} >>>")
            print(f"  Outputs for this file will be in: {file_specific_output_base_dir}")

            try:
                with open(current_source_file_abs_path, 'r', encoding='utf-8') as f:
                    current_file_initial_source_code = f.read()
            except Exception as e:
                print(f"Error reading content of {current_source_file_abs_path}: {e}. Skipping this file.")
                continue
            
            analyzer_input_yaml_path = os.path.join(file_specific_output_base_dir, "analyzer_input.yaml")
            analyzer_output_path = os.path.join(file_specific_output_base_dir, f"analyzer_output.yaml")
            replicator_output_path = os.path.join(file_specific_output_base_dir, f"replicator_output.yaml")
            patcher_output_path = os.path.join(file_specific_output_base_dir, f"patcher_output.yaml")

            try:
                # --- Step 2.{iteration}.1: Prepare Analyzer Input & Run Analyzer --- 
                print(f"\n  --- Step 2.{iteration}.1: Running Analyzer for {original_file_name} (Iteration {iteration}) ---")

                try:
                    # current_file_initial_source_code = read_file_content(current_source_file_abs_path)
                    with open(current_source_file_abs_path, 'r', encoding='utf-8') as f:
                        current_file_initial_source_code = f.read()
                except Exception as e:
                    print(f"Error reading content of {current_source_file_abs_path}: {e}. Skipping this file.")
                    continue
                
                perf_data = read_yaml(global_profiler_output_yaml_path)
                if not perf_data:
                    print(f"    Error: Could not read profiler data from {global_profiler_output_yaml_path}. Skipping iteration.")
                    break
                
                analyzer_input_data_for_run = {
                    'source_code': current_file_initial_source_code, # The source code of the current C++ file
                    'perf_command': perf_data.get('perf_command', 'N/A'), # From global profile run
                    'perf_report_output': perf_data.get('perf_report_output', ''), # From global profile run
                    'profiling_details': perf_data.get('profiling_details') # Carry over details if any
                }
                write_yaml(analyzer_input_data_for_run, analyzer_input_yaml_path)
                
                analyzer = Analyzer()
                analyzer.set_io(analyzer_input_yaml_path, analyzer_output_path) # Analyzer reads the YAML itself
                analyzer.setup()
                analyzer_output_data = analyzer.run(analyzer_input_data_for_run) # Pass data in case it uses it directly over self.input_data
                
                # Always write analyzer output for record-keeping
                write_yaml(analyzer_output_data if analyzer_output_data else {"error": "Analyzer run resulted in no data"}, analyzer_output_path)

                if analyzer_output_data is None: # Should not happen if agent returns a dict
                    print(f"    Critical Error: Analyzer run returned None for {original_file_name}, iter {iteration}. Skipping further processing for this file.")
                    break # Break from iterations for this file

                print(f"    Analyzer completed for {original_file_name}, iter {iteration}. Output: {analyzer_output_path}")

                # Check 1: Analyzer step explicitly reported an error
                if analyzer_output_data.get('analyzer_error'):
                    print(f"    Analyzer reported an error for {original_file_name}, iter {iteration}: {analyzer_output_data['analyzer_error']}. Skipping further optimization for this file.")
                    break # Break from iterations for this file

                # Check 2: No performance analysis string produced (less likely if no error, but a safeguard)
                if not analyzer_output_data.get('performance_analysis'):
                    print(f"    Error: Analyzer produced no 'performance_analysis' text for {original_file_name}, iter {iteration}. Skipping further optimization for this file.")
                    break # Break from iterations for this file
                
                # Check 3: No actionable bottleneck_location identified
                actionable_bottleneck_found = False
                if isinstance(analyzer_output_data, dict) and analyzer_output_data.get('bottleneck_location'):
                    actionable_bottleneck_found = True
                
                if not actionable_bottleneck_found:
                    print(f"    Analyzer output for {original_file_name} (iter {iteration}) did not contain an actionable 'bottleneck_location'. Skipping further optimization attempts for this file.")
                    break # Break from iterations for this file, move to next C++ file

                # --- Step 2.{iteration}.2: Run Replicator --- 
                print(f"\n  --- Step 2.{iteration}.2: Running Replicator for {original_file_name} (Iteration {iteration}) ---")
                replicator = Replicator()
                # Replicator input is analyzer_output_path. Analyzer output should contain the source_code it analyzed.
                replicator.set_io(analyzer_output_path, replicator_output_path)
                replicator.setup()
                # The replicator_output_data should have 'source_code' (the one from analyzer input) and 'modified_code_variants'
                replicator_output_data = replicator.run(read_yaml(analyzer_output_path)) 
                
                if replicator_output_data.get('replication_error'):
                    print(f"    Error in Replicator for {original_file_name}, iter {iteration}: {replicator_output_data['replication_error']}")
                    write_yaml(replicator_output_data, replicator_output_path)
                    break
                elif not replicator_output_data.get('modified_code_variants'):
                    print(f"    Warning: Replicator produced no 'modified_code_variants' for {original_file_name}, iter {iteration}.")
                write_yaml(replicator_output_data, replicator_output_path)
                print(f"    Replicator completed for {original_file_name}, iter {iteration}. Output: {replicator_output_path}")

                # --- Step 2.{iteration}.3: Run Patcher --- 
                print(f"\n  --- Step 2.{iteration}.3: Running Patcher for {original_file_name} (Iteration {iteration}) ---")
                actual_patcher_instance = Patcher()
                if not replicator_output_data.get('modified_code_variants'):
                    print(f"    Skipping Patcher for {original_file_name}, iter {iteration} as Replicator produced no 'modified_code_variants'.")
                    patcher_output_data = replicator_output_data.copy() 
                    patcher_output_data['patcher_status'] = 'skipped_no_variants'
                else:
                    patcher_input_data_for_run = replicator_output_data.copy()
                    # Patcher needs original_file_name to name the output files correctly within its structure.
                    patcher_input_data_for_run['original_file_name'] = original_file_name 
                    
                    actual_patcher_instance.set_io(replicator_output_path, patcher_output_path) 
                    actual_patcher_instance.setup()
                    patcher_output_data = actual_patcher_instance.run(patcher_input_data_for_run)
                
                write_yaml(patcher_output_data, patcher_output_path)
                print(f"    Patcher completed for {original_file_name}, iter {iteration}. Output YAML: {patcher_output_path}")
                if patcher_output_data.get('patcher_overall_error') or patcher_output_data.get('patcher_status') == 'all_failed':
                    print(f"    Warning/Error in Patcher: {patcher_output_data.get('patcher_overall_error', 'Patcher status was all_failed.')}")
            
            except Exception as e_iter:
                print(f"  Error during Optimizer iteration {iteration} for file {original_file_name}: {e_iter}")
                import traceback
                traceback.print_exc()
                break # Break from iterations loop for this specific file
        
        # --- Step 3: Profiling & Evaluating Patched Variants ---
        print(f"\n=== Step 3: Profiling & Evaluating Patched Variants (Iteration {iteration}) ===")
        all_variant_profiler_inputs = {}
        variant_results = []

        for current_source_file_abs_path in cpp_files_to_process:
            original_file_name = os.path.basename(current_source_file_abs_path)
            file_specific_output_base_dir = os.path.join(iter_output_dir_for_file, original_file_name)
            patcher_output_path = os.path.join(file_specific_output_base_dir, f"patcher_output.yaml")

            patcher_output_data = read_yaml(patcher_output_path)

            if patcher_output_data.get('patcher_status') not in ['all_success', 'partial_success'] or not patcher_output_data.get('patched_variants_results'):
                print(f"    Patcher did not write files successfully or produced no results. Skipping variant profiling.")
                continue
            
            if patcher_output_data.get('patcher_status') == 'all_success':
                for var in patcher_output_data.get('patched_variants_results', []):
                    all_variant_profiler_inputs[var.get('variant_id')] = {
                        'variant_patched_path': os.path.dirname(var.get('patched_file_path'))
                    }

        for variant_id in all_variant_profiler_inputs.keys():
            # --- Step 3.1: Profiling Patched Variants --- 
            print(f"\n  --- Step 3.1: Profiling Patched Variants for variant: {variant_id} (Iteration {iteration}) ---")
            patched_variant_disk_path = all_variant_profiler_inputs[variant_id]['variant_patched_path']
            sanitized_variant_id_for_paths = utility_patcher_instance._sanitize_filename(variant_id).lower()

            print(f"\n    --- Profiling Variant: {variant_id} (Iter: {iteration}) ---")

            variant_profiler_temp_base_dir = os.path.join(iter_output_dir_for_file, f"{sanitized_variant_id_for_paths}")

            variant_profiler_input_data = {'source_dir': patched_variant_disk_path}
            variant_profiler_input_yaml_path = os.path.join(variant_profiler_temp_base_dir, f"profiler_input.yaml")
            variant_profiler_output_yaml_path = os.path.join(variant_profiler_temp_base_dir, f"profiler_output.yaml")
            write_yaml(variant_profiler_input_data, variant_profiler_input_yaml_path)

            try:
                variant_profiler_agent = Profiler()
                variant_profiler_agent.set_io(variant_profiler_input_yaml_path, variant_profiler_output_yaml_path)
                variant_profiler_agent.setup()
                variant_profiler_run_output_data = variant_profiler_agent.run(variant_profiler_input_data)
                
                if variant_profiler_run_output_data.get('profiler_error'):
                    print(f"      Error during Profiler run for variant {variant_id}: {variant_profiler_run_output_data['profiler_error']}")
                else:
                    print(f"      Profiler run for variant {variant_id} completed.")
                write_yaml(variant_profiler_run_output_data, variant_profiler_output_yaml_path)
                print(f"      Profiler output for variant {variant_id} saved to: {variant_profiler_output_yaml_path}")
            except Exception as e_var_prof:
                print(f"      Exception during Profiler setup/run for variant {variant_id}: {e_var_prof}")
                continue 
            
            # --- Step 3.2: Evaluate Patched Variants --- 
            print(f"\n  --- Step 3.2: Evaluating Patched Variants for variant: {variant_id} (Iteration {iteration}) ---")

            sanitized_variant_id_for_paths = utility_patcher_instance._sanitize_filename(variant_id).lower()
            evaluator_run_base_dir = os.path.join(iter_output_dir_for_file, f"{sanitized_variant_id_for_paths}")
            os.makedirs(evaluator_run_base_dir, exist_ok=True)
            
            evaluator_input_data = {
                'original_profiler_output_path': global_profiler_output_yaml_path,
                'variant_profiler_output_path': variant_profiler_output_yaml_path
            }
            evaluator_input_yaml_path = os.path.join(evaluator_run_base_dir, f"evaluator_input.yaml")
            evaluator_output_yaml_path = os.path.join(evaluator_run_base_dir, f"evaluator_output.yaml")
            write_yaml(evaluator_input_data, evaluator_input_yaml_path)

            try:
                evaluator = Evaluator()
                evaluator.set_io(evaluator_input_yaml_path, evaluator_output_yaml_path)
                evaluator.setup()
                evaluator_output_data = evaluator.run()
                write_yaml(evaluator_output_data, evaluator_output_yaml_path)
                print(f"      Evaluator run for variant {variant_id} completed. Output: {evaluator_output_yaml_path}")
                
                if evaluator_output_data.get('evaluator_error'):
                    print(f"      Error during Evaluator run for variant {variant_id}: {evaluator_output_data['evaluator_error']}")
                elif evaluator_output_data.get('evaluation_results', {}).get('improvement_summary', {}).get('overall_assessment') == "Significant Improvement":
                    print(f"      Variant {variant_id} shows 'Significant Improvement'. Selecting as new potential champion.")
            except Exception as e_eval:
                print(f"      Exception during Evaluator for variant {variant_id}: {e_eval}")

            # --- Collect improvement info for summary ---
            is_improvement = False
            improvement_percentage = None
            try:
                eval_results = evaluator_output_data.get('evaluation_results', {})
                is_improvement = eval_results.get('is_improvement', False)
                improvement_percentage = eval_results.get('improvement_percentage', None)
            except Exception:
                pass

            variant_results.append({
                'variant_id': variant_id,
                'is_improvement': is_improvement,
                'improvement_percentage': improvement_percentage,
                'iteration': iteration
            })

        # --- Print iteration summary and find best variant in this iteration ---
        print(f"\n=== Iteration {iteration} Summary ===")
        if variant_results:
            print(f"{'Variant':<15} {'Improvement?':<15} {'% Improvement':<15}")
            print('-' * 45)
            for v in variant_results:
                print(f"{v['variant_id']:<15} {str(v['is_improvement']):<15} {str(v['improvement_percentage']):<15}")
            # Find best variant in this iteration
            improved_variants = [v for v in variant_results if v['is_improvement'] and v['improvement_percentage'] is not None]
            if improved_variants:
                best_variant = max(improved_variants, key=lambda x: x['improvement_percentage'])
                print(f"\nBest variant in iteration {iteration}: {best_variant['variant_id']} with {best_variant['improvement_percentage']}% improvement.")
                # Update overall best if needed
                if best_variant['improvement_percentage'] > overall_best['improvement_percentage']:
                    overall_best.update({
                        'iteration': iteration,
                        'variant_id': best_variant['variant_id'],
                        'improvement_percentage': best_variant['improvement_percentage']
                    })
            else:
                print("No improved variants found in this iteration.")
        else:
            print("No variants evaluated in this iteration.")

        # Store for overall summary
        iteration_summaries.append({
            'iteration': iteration,
            'variants': variant_results
        })

    # --- After all iterations, print overall summary ---
    print("\n=== Overall Optimization Summary ===")
    for summary in iteration_summaries:
        print(f"\nIteration {summary['iteration']}:")
        for v in summary['variants']:
            print(f"  Variant: {v['variant_id']}, Improvement: {v['is_improvement']}, % Improvement: {v['improvement_percentage']}")

    if overall_best['variant_id'] is not None:
        print(f"\nBest overall variant: {overall_best['variant_id']} from iteration {overall_best['iteration']} with {overall_best['improvement_percentage']}% improvement.")
    else:
        print("\nNo significant improvements found in any iteration.")

    # End of loop for all cpp_files_to_process
    pipeline_overall_end_time = time.time()
    print(f"\nOptimizer Pipeline finished processing all discovered C++ files in {(pipeline_overall_end_time - pipeline_overall_start_time):.2f}s. Outputs in: {args.output_dir}")

if __name__ == "__main__":
    main()