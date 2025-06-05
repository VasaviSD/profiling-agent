#!/usr/bin/env python3
# See LICENSE for details

import argparse
import os
import sys
import time
import glob
import shutil
import json # For structured printing if needed

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
    """Finds C++ implementation files (.cpp, .cc, .cxx) in the given directory (non-recursive)."""
    patterns = ['*.cpp', '*.cc', '*.cxx']
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
    global_profiler_input_yaml_path = os.path.join(args.output_dir, "initial_global_profiler_input.yaml")
    global_profiler_output_yaml_path = os.path.join(args.output_dir, "initial_global_profiler_output.yaml")
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

    # --- Step 2: Discover C++ source files to process individually --- 
    cpp_files_to_process = find_cpp_source_files(args.source_dir)
    if not cpp_files_to_process:
        print(f"No C++ files (.cpp, .cc, .cxx) found directly in {args.source_dir} to process.")
        sys.exit(0)
    print(f"\nFound {len(cpp_files_to_process)} C++ files in {args.source_dir} to process individually: {cpp_files_to_process}")

    # --- Step 3: Loop through each discovered C++ source file --- 
    for current_source_file_abs_path in cpp_files_to_process:
        original_file_name = os.path.basename(current_source_file_abs_path)
        sanitized_original_file_name_for_dir = utility_patcher_instance._sanitize_filename(os.path.splitext(original_file_name)[0])
        
        file_specific_output_base_dir = os.path.join(args.output_dir, sanitized_original_file_name_for_dir)
        if not os.path.exists(file_specific_output_base_dir):
            os.makedirs(file_specific_output_base_dir)
        
        print(f"\n>>> Processing C++ source file: {current_source_file_abs_path} >>>")
        print(f"Outputs for this file will be in: {file_specific_output_base_dir}")

        try:
            # current_file_initial_source_code = read_file_content(current_source_file_abs_path)
            with open(current_source_file_abs_path, 'r', encoding='utf-8') as f:
                current_file_initial_source_code = f.read()
        except Exception as e:
            print(f"Error reading content of {current_source_file_abs_path}: {e}. Skipping this file.")
            continue

        # This dictionary holds information about the current "champion" version of THIS specific C++ file.
        # It's updated if a better variant is found and successfully profiled.
        current_champion_info_for_file = {
            "identity_name": f"original_{original_file_name}",
            "source_code_content": current_file_initial_source_code,
            # The performance data for the original version of this file is from the global executable profile.
            "associated_profiler_output_path": global_profiler_output_yaml_path, 
            "iteration_established": 0,
            "evaluation_summary_at_selection": None # Original has no prior eval that led to it
        }
        # Keep a record of the very first state for final comparison for this file.
        true_initial_champion_info_for_file = current_champion_info_for_file.copy()

        for i in range(args.iterations):
            iteration = i + 1
            print(f"\n  === Starting Optimizer Iteration: {iteration}/{args.iterations} for file: {original_file_name} ===")

            iter_output_dir_for_file = os.path.join(file_specific_output_base_dir, f"iter_{iteration}")
            if not os.path.exists(iter_output_dir_for_file):
                os.makedirs(iter_output_dir_for_file)
            
            analyzer_input_yaml_path = os.path.join(iter_output_dir_for_file, "analyzer_input.yaml")
            analyzer_output_path = os.path.join(iter_output_dir_for_file, f"analyzer_output.yaml")
            replicator_output_path = os.path.join(iter_output_dir_for_file, f"replicator_output.yaml")
            patcher_output_path = os.path.join(iter_output_dir_for_file, f"patcher_output.yaml")

            try:
                # --- Step 3.{iteration}.1: Prepare Analyzer Input & Run Analyzer --- 
                print(f"\n  --- Step {iteration}.1: Running Analyzer for {original_file_name} (Iteration {iteration}) ---")
                champion_perf_data = read_yaml(current_champion_info_for_file["associated_profiler_output_path"])
                if not champion_perf_data:
                    print(f"    Error: Could not read champion profiler data from {current_champion_info_for_file['associated_profiler_output_path']}. Skipping iteration.")
                    break
                
                analyzer_input_data_for_run = {
                    'source_code': current_champion_info_for_file["source_code_content"],
                    'perf_command': champion_perf_data.get('perf_command', 'N/A'), # From champion's profile run
                    'perf_report_output': champion_perf_data.get('perf_report_output', ''), # From champion's profile run
                    'profiling_details': champion_perf_data.get('profiling_details') # Carry over details if any
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
                
                # Check 3: No actionable hotspots identified (THE KEY CHECK)
                identified_hotspots = analyzer_output_data.get('identified_hotspots')
                if not identified_hotspots: # This covers None or an empty list
                    print(f"    Analyzer found no actionable hotspots in {original_file_name} (iter {iteration}). Skipping further optimization attempts for this file.")
                    break # Break from iterations for this file, move to next C++ file

                # --- Step 3.{iteration}.2: Run Replicator --- 
                print(f"\n  --- Step {iteration}.2: Running Replicator for {original_file_name} (Iteration {iteration}) ---")
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

                # --- Step 3.{iteration}.3: Run Patcher --- 
                print(f"\n  --- Step {iteration}.3: Running Patcher for {original_file_name} (Iteration {iteration}) ---")
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
                
                # --- Step 3.{iteration}.4: Profile Patched Variants --- 
                print(f"\n  --- Step {iteration}.4: Profiling Patched Variants for {original_file_name} (Iteration {iteration}) ---")
                all_variant_evaluator_inputs = [] # To store info for Evaluator, will remain empty

                # TODO: Future - Implement/Re-enable variant profiling logic here.
                # The following block is commented out to disable automatic profiling of variants.
                # Patcher output (patched files) are still generated if variants were created.
                """
                if patcher_output_data.get('patcher_status') not in ['all_success', 'partial_success'] or not patcher_output_data.get('patched_variants_results'):
                    print(f"    Patcher did not write files successfully or produced no results. Skipping variant profiling.")
                else:
                    successful_written_variants_info = []
                    for variant_res in patcher_output_data.get('patched_variants_results', []):
                        if variant_res.get('status') == 'success' and variant_res.get('patched_file_path'): 
                            variant_source_code_content = "N/A"
                            patched_file_path_for_variant = variant_res.get('patched_file_path')
                            try:
                                with open(patched_file_path_for_variant, 'r', encoding='utf-8') as f_var_src:
                                    variant_source_code_content = f_var_src.read()
                            except Exception as e_read_var:
                                print(f"    Warning: Could not read source content of patched variant {variant_res.get('variant_id')} from {patched_file_path_for_variant}: {e_read_var}")
                            
                            successful_written_variants_info.append({
                                'variant_id': variant_res.get('variant_id'),
                                'patched_file_disk_path': patched_file_path_for_variant, 
                                'variant_source_code': variant_source_code_content
                            })

                    if not successful_written_variants_info:
                        print(f"    No successfully written variant source files to profile.")
                    else:
                        print(f"    Found {len(successful_written_variants_info)} successfully written variant source files to profile.")
                        
                        for var_info in successful_written_variants_info:
                            variant_id = var_info['variant_id']
                            patched_variant_disk_path = var_info['patched_file_disk_path']
                            sanitized_variant_id_for_paths = utility_patcher_instance._sanitize_filename(variant_id).lower()

                            print(f"\n    --- Profiling Variant: {variant_id} (File: {original_file_name}, Iter: {iteration}) ---")

                            variant_profiler_temp_base_dir = os.path.join(iter_output_dir_for_file, f"profiler_run_variant_{sanitized_variant_id_for_paths}")
                            variant_profiler_src_dir_for_compile = os.path.join(variant_profiler_temp_base_dir, "src_for_variant_compile")
                            
                            if os.path.exists(variant_profiler_src_dir_for_compile):
                                shutil.rmtree(variant_profiler_src_dir_for_compile)
                            shutil.copytree(args.source_dir, variant_profiler_src_dir_for_compile)
                            print(f"      Copied original project from {args.source_dir} to {variant_profiler_src_dir_for_compile}")
                            
                            target_file_in_temp_project = os.path.join(variant_profiler_src_dir_for_compile, original_file_name)
                            shutil.copy(patched_variant_disk_path, target_file_in_temp_project)
                            print(f"      Copied patched variant {patched_variant_disk_path} to {target_file_in_temp_project}")

                            variant_profiler_input_data = {'source_dir': variant_profiler_src_dir_for_compile}
                            variant_profiler_input_yaml_path = os.path.join(variant_profiler_temp_base_dir, f"profiler_input_variant_{sanitized_variant_id_for_paths}.yaml")
                            variant_profiler_output_yaml_path = os.path.join(variant_profiler_temp_base_dir, f"profiler_output_variant_{sanitized_variant_id_for_paths}.yaml")
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
                                    all_variant_evaluator_inputs.append({
                                        'variant_id': variant_id,
                                        'variant_source_code_content': var_info['variant_source_code'],
                                        'variant_patched_file_disk_path': patched_variant_disk_path, 
                                        'variant_profiler_output_yaml_path': variant_profiler_output_yaml_path 
                                    })
                                write_yaml(variant_profiler_run_output_data, variant_profiler_output_yaml_path)
                                print(f"      Profiler output for variant {variant_id} saved to: {variant_profiler_output_yaml_path}")
                            except Exception as e_var_prof:
                                print(f"      Exception during Profiler setup/run for variant {variant_id}: {e_var_prof}")
                                continue 
                """
                # Since variant profiling is commented out, all_variant_evaluator_inputs will be empty.
                # The following message will reflect this if not already indicating no variants from Patcher.
                if not all_variant_evaluator_inputs and (patcher_output_data.get('patcher_status') in ['all_success', 'partial_success'] and patcher_output_data.get('patched_variants_results')):
                     print(f"    Variant profiling step is currently disabled. No variants were profiled.")
                elif not patcher_output_data.get('patched_variants_results'):
                     print(f"    No variants were produced by Patcher to profile.")

                # --- Step 3.{iteration}.5: Evaluate Patched Variants (Effectively Skipped) --- 
                print(f"\n  --- Step {iteration}.5: Evaluating Patched Variants for {original_file_name} (Iteration {iteration}) ---")
                best_variant_for_this_iteration = None # Will remain None as Evaluator is skipped

                # TODO: Future - Implement Evaluator call and best variant selection logic here.
                # The following block is commented out to disable automatic evaluation.
                # Variant profiling outputs are still generated and can be reviewed manually.
                """
                if not all_variant_evaluator_inputs:
                    print(f"    No variants were successfully profiled to evaluate.")
                else:
                    print(f"    Evaluating {len(all_variant_evaluator_inputs)} profiled variants.")
                    for eval_candidate in all_variant_evaluator_inputs:
                        variant_id = eval_candidate['variant_id']
                        sanitized_variant_id_for_paths = utility_patcher_instance._sanitize_filename(variant_id).lower()
                        evaluator_run_base_dir = os.path.join(iter_output_dir_for_file, f"evaluator_run_variant_{sanitized_variant_id_for_paths}")
                        os.makedirs(evaluator_run_base_dir, exist_ok=True)
                        
                        evaluator_input_data = {
                            'original_profiler_output_path': current_champion_info_for_file["associated_profiler_output_path"],
                            'variant_profiler_output_path': eval_candidate['variant_profiler_output_yaml_path']
                        }
                        evaluator_input_yaml_path = os.path.join(evaluator_run_base_dir, f"evaluator_input_{sanitized_variant_id_for_paths}.yaml")
                        evaluator_output_yaml_path = os.path.join(evaluator_run_base_dir, f"evaluator_output_{sanitized_variant_id_for_paths}.yaml")
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
                                if best_variant_for_this_iteration is None: 
                                    best_variant_for_this_iteration = {
                                        "identity_name": f"{variant_id}_{original_file_name}",
                                        "source_code_content": eval_candidate['variant_source_code_content'], 
                                        "associated_profiler_output_path": eval_candidate['variant_profiler_output_yaml_path"],
                                        "iteration_established": iteration,
                                        "evaluation_summary_at_selection": evaluator_output_data.get('evaluation_results',{}).get('improvement_summary')
                                    }
                        except Exception as e_eval:
                            print(f"      Exception during Evaluator for variant {variant_id}: {e_eval}")
                """

                if best_variant_for_this_iteration:
                    # This block will not be reached as best_variant_for_this_iteration is always None
                    print(f"    Iteration {iteration} new champion for {original_file_name}: {best_variant_for_this_iteration['identity_name']}")
                    current_champion_info_for_file = best_variant_for_this_iteration
                else:
                    # This will always be printed since Evaluator is skipped
                    print(f"    Evaluator step skipped. No variant selected as champion in iteration {iteration} for {original_file_name}. Champion remains: {current_champion_info_for_file['identity_name']}")
            
            except Exception as e_iter:
                print(f"  Error during Optimizer iteration {iteration} for file {original_file_name}: {e_iter}")
                import traceback
                traceback.print_exc()
                break # Break from iterations loop for this specific file

            if iteration == args.iterations:
                print(f"\n  --- Optimizer Summary for file: {original_file_name} after {args.iterations} iterations ---")
                print(f"    Initial Champion: '{true_initial_champion_info_for_file['identity_name']}' (Perf context: {true_initial_champion_info_for_file['associated_profiler_output_path']})")
                if current_champion_info_for_file["identity_name"] != true_initial_champion_info_for_file["identity_name"]:
                    print(f"    Final Champion:   '{current_champion_info_for_file['identity_name']}' (Perf context: {current_champion_info_for_file['associated_profiler_output_path']})")
                    print(f"      - Established in Iteration: {current_champion_info_for_file['iteration_established']}")
                    if current_champion_info_for_file["evaluation_summary_at_selection"]:
                        summary = current_champion_info_for_file["evaluation_summary_at_selection"]
                        print(f"      - Evaluation when selected: {summary.get('overall_assessment', 'N/A')}")
                        if 'performance_change_percentage' in summary:
                             print(f"        Performance Change vs. its baseline (%): {summary['performance_change_percentage']}")
                else:
                    print(f"    No improvement over the initial version was selected as the final champion for this file.")
                print(f"  --- End Summary for {original_file_name} ---")

        # End of iterations for current_source_file_abs_path
        print(f"<<< Completed all {args.iterations} iterations for C++ source file: {current_source_file_abs_path} <<<")
    
    # End of loop for all cpp_files_to_process
    pipeline_overall_end_time = time.time()
    print(f"\nOptimizer Pipeline finished processing all discovered C++ files in {(pipeline_overall_end_time - pipeline_overall_start_time):.2f}s. Outputs in: {args.output_dir}")

if __name__ == "__main__":
    main() 