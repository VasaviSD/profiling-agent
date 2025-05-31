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
    from step.evaluator.evaluator_agent import Evaluator
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

        # This will store the path to the profiler output YAML that should be considered "baseline" for the next iteration's Analyzer.
        # Initially, it's the profiler output of the original, unmodified code.
        # After each iteration, if a variant performs better, this will be updated to that variant's profiler output.
        baseline_profiler_output_for_next_iteration = None

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
                print(f"\n--- Step {iteration}.1: Running Initial/Baseline Profiler (Iteration {iteration}) for {original_file_name} ---")
                profiler_input_disk_data = read_yaml(current_profiler_input_yaml_for_iteration)
                if not profiler_input_disk_data:
                    print(f"Error: Could not read/parse Profiler input YAML: {current_profiler_input_yaml_for_iteration}")
                    break 
                
                profiler = Profiler()
                profiler.set_io(current_profiler_input_yaml_for_iteration, profiler_output_path)
                profiler.setup()
                profiler_output_data = profiler.run(profiler_input_disk_data)
                
                if profiler_output_data.get('profiler_error'):
                    print(f"Error in Initial/Baseline Profiler (Step {iteration}.1, iter {iteration}, file {original_file_name}): {profiler_output_data['profiler_error']}")
                    break 
                write_yaml(profiler_output_data, profiler_output_path)
                print(f"Initial/Baseline Profiler (Step {iteration}.1, iter {iteration}, file {original_file_name}) completed. Output: {profiler_output_path}")

                # Set the first baseline profiler output
                if iteration == 1:
                    baseline_profiler_output_for_next_iteration = profiler_output_path
                
                # The Analyzer will now use the baseline_profiler_output_for_next_iteration as its input
                # instead of directly using the profiler_output_path from the *current* initial profiling run
                # This is important for multi-iteration runs.
                analyzer_input_yaml_path = baseline_profiler_output_for_next_iteration
                analyzer_input_data_for_run = read_yaml(analyzer_input_yaml_path)
                if not analyzer_input_data_for_run:
                    print(f"Error: Could not read/parse Analyzer input YAML: {analyzer_input_yaml_path} for iter {iteration}")
                    break

                print(f"\n--- Step {iteration}.2: Running Analyzer (Iteration {iteration}) for {original_file_name} using {analyzer_input_yaml_path} ---")
                analyzer = Analyzer()
                analyzer.set_io(analyzer_input_yaml_path, analyzer_output_path)
                analyzer.setup()
                analyzer_output_data = analyzer.run(analyzer_input_data_for_run) # Pass the read data
                if not analyzer_output_data.get('performance_analysis'):
                    print(f"Error: Analyzer (Step {iteration}.2, iter {iteration}, file {original_file_name}) produced no 'performance_analysis'.")
                    break 
                write_yaml(analyzer_output_data, analyzer_output_path)
                print(f"Analyzer (Step {iteration}.2, iter {iteration}, file {original_file_name}) completed. Output: {analyzer_output_path}")

                print(f"\n--- Step {iteration}.3: Running Replicator (Iteration {iteration}) for {original_file_name} ---")
                replicator = Replicator()
                replicator.set_io(analyzer_output_path, replicator_output_path)
                replicator.setup()
                replicator_output_data = replicator.run(analyzer_output_data)
                if replicator_output_data.get('replication_error'):
                    print(f"Error in Replicator (Step {iteration}.3, iter {iteration}, file {original_file_name}): {replicator_output_data['replication_error']}")
                    break
                elif not replicator_output_data.get('modified_code_variants'):
                    print(f"Warning: Replicator (Step {iteration}.3, iter {iteration}, file {original_file_name}) produced no 'modified_code_variants'.")
                write_yaml(replicator_output_data, replicator_output_path)
                print(f"Replicator (Step {iteration}.3, iter {iteration}, file {original_file_name}) completed. Output: {replicator_output_path}")

                print(f"\n--- Step {iteration}.4: Running Patcher (Iteration {iteration}) for {original_file_name} ---")
                actual_patcher_instance = Patcher() # Instance for this specific Patcher run
                if not replicator_output_data.get('modified_code_variants'):
                    print(f"Skipping Patcher (Step {iteration}.4) for iter {iteration}, file {original_file_name} as Replicator produced no 'modified_code_variants'.")
                    patcher_output_data = replicator_output_data.copy() 
                    patcher_output_data['patcher_status'] = 'skipped_no_variants'
                else:
                    patcher_input_data_for_run = replicator_output_data.copy()
                    patcher_input_data_for_run['original_file_name'] = original_file_name
                    
                    actual_patcher_instance.set_io(replicator_output_path, patcher_output_path) 
                    actual_patcher_instance.setup()
                    patcher_output_data = actual_patcher_instance.run(patcher_input_data_for_run)
                    
                    write_yaml(patcher_output_data, patcher_output_path)
                    print(f"Patcher (Step {iteration}.4, iter {iteration}, file {original_file_name}) completed. Output YAML: {patcher_output_path}")
                    if patcher_output_data.get('patcher_overall_error') or patcher_output_data.get('patcher_status') == 'all_failed':
                        print(f"Warning/Error in Patcher (Step {iteration}.4, iter {iteration}, file {original_file_name}): {patcher_output_data.get('patcher_overall_error', 'Patcher status was all_failed.')}")
                
                print(f"\n--- Step {iteration}.5: Profiling Patched Variants (Iteration {iteration}, File {original_file_name}) ---")
                if patcher_output_data.get('patcher_status') not in ['all_success', 'partial_success'] or not patcher_output_data.get('patched_variants_results'):
                    print(f"Patcher (Step {iteration}.4) did not write files successfully or produced no results for iter {iteration}, file {original_file_name}. Skipping Step {iteration}.5.")
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
                        
                        # Store evaluator results for this iteration to find the best variant
                        all_variant_evaluator_outputs = []

                        for var_info in successful_written_variants_sources:
                            variant_id = var_info['variant_id']
                            patched_variant_source_path = var_info['source_path']
                            # Use the utility_patcher_instance for _sanitize_filename
                            sanitized_variant_id = utility_patcher_instance._sanitize_filename(variant_id).lower()

                            print(f"\n  --- Step {iteration}.5.1 ({variant_id}): Profiling Patched Variant Source (File: {original_file_name}, Iter: {iteration}) ---")

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
                                    print(f"    Error during Profiler run for variant {variant_id} (Step {iteration}.5.1): {variant_profiler_output['profiler_error']}")
                                else:
                                    print(f"    Profiler run for variant {variant_id} (Step {iteration}.5.1) completed.")
                                write_yaml(variant_profiler_output, variant_profiler_output_yaml_path)
                                print(f"    Profiler output for variant {variant_id} (Step {iteration}.5.1) saved to: {variant_profiler_output_yaml_path}")

                                # --- Add Evaluator Step for this variant ---
                                if not variant_profiler_output.get('profiler_error'):
                                    print(f"\n  --- Step {iteration}.5.2 ({variant_id}): Running Evaluator for Variant (File: {original_file_name}, Iter: {iteration}) ---")
                                    evaluator_input_data = {
                                        'original_profiler_output_path': baseline_profiler_output_for_next_iteration, # Compare against current baseline
                                        'variant_profiler_output_path': variant_profiler_output_yaml_path
                                    }
                                    evaluator_input_yaml_path = os.path.join(variant_profiler_run_base_dir, f"evaluator_input_{sanitized_variant_id}.yaml")
                                    write_yaml(evaluator_input_data, evaluator_input_yaml_path)

                                    evaluator_output_yaml_path = os.path.join(variant_profiler_run_base_dir, f"evaluator_output_{sanitized_variant_id}.yaml")

                                    try:
                                        evaluator = Evaluator()
                                        evaluator.set_io(evaluator_input_yaml_path, evaluator_output_yaml_path)
                                        evaluator.setup() # Evaluator reads its input config in setup
                                        evaluator_output_data = evaluator.run() # No need to pass data, it reads from self.input_file in setup

                                        write_yaml(evaluator_output_data, evaluator_output_yaml_path)
                                        print(f"    Evaluator run for variant {variant_id} (Step {iteration}.5.2) completed. Output: {evaluator_output_yaml_path}")
                                        if evaluator_output_data.get('evaluator_error'):
                                            print(f"    Error during Evaluator run for variant {variant_id} (Step {iteration}.5.2): {evaluator_output_data['evaluator_error']}")
                                        else:
                                            # Store for later comparison
                                            all_variant_evaluator_outputs.append({
                                                'variant_id': variant_id,
                                                'evaluator_output_path': evaluator_output_yaml_path,
                                                'profiler_output_path': variant_profiler_output_yaml_path, # Keep track of this variant's profiler output
                                                'evaluation_results': evaluator_output_data.get('evaluation_results')
                                            })
                                    except Exception as e_eval:
                                        print(f"    Error during Evaluator setup/run for variant {variant_id} (Step {iteration}.5.2): {e_eval}")
                                        import traceback
                                        traceback.print_exc()
                                else:
                                    print(f"    Skipping Evaluator for variant {variant_id} (Step {iteration}.5.2) due to Profiler error (Step {iteration}.5.1).")
                                # --- End of Evaluator Step ---

                            except Exception as e_var_prof:
                                print(f"    Error during profiling setup/run for variant {variant_id} (Step {iteration}.5.1): {e_var_prof}")
                                import traceback
                                traceback.print_exc()
                                continue 

                        # --- After evaluating all variants for this iteration ---
                        if all_variant_evaluator_outputs:
                            print(f"\n--- Step {iteration}.6: Determining Best Variant for Iteration {iteration}, File {original_file_name} ---")
                            # TODO: Implement logic to parse evaluation_results and pick the best one.
                            # For now, let's assume the first one that didn't error and has results is "best" for testing flow.
                            # A more sophisticated selection based on 'improvement_rating' or similar is needed.
                            best_variant_for_this_iteration = None
                            for eval_output in all_variant_evaluator_outputs:
                                if eval_output['evaluation_results'] and not eval_output['evaluation_results'].get('error'):
                                    # This is a placeholder for actual improvement check
                                    # We need to look into evaluation_results structure.
                                    # Example: if eval_output['evaluation_results'].get('is_improvement', False):
                                    print(f"  Found a candidate variant: {eval_output['variant_id']}")
                                    # For now, just pick the first one that seems okay.
                                    # This needs to be replaced with logic that checks `improvement_summary.overall_assessment == "Significant Improvement"`
                                    # or `improvement_summary.performance_change_percentage > threshold` etc.
                                    if eval_output['evaluation_results'].get('improvement_summary', {}).get('overall_assessment') == "Significant Improvement":
                                        print(f"  Variant {eval_output['variant_id']} shows 'Significant Improvement'. Selecting as new baseline.")
                                        best_variant_for_this_iteration = eval_output
                                        break # Found a significantly improved one
                                    elif not best_variant_for_this_iteration and eval_output['evaluation_results'].get('improvement_summary', {}).get('overall_assessment') == "Marginal Improvement":
                                         # Keep track of marginal ones if no significant ones are found
                                        best_variant_for_this_iteration = eval_output
                                        print(f"  Variant {eval_output['variant_id']} shows 'Marginal Improvement'. Tentatively selecting.")
                                    elif not best_variant_for_this_iteration : # Fallback to any valid result
                                        best_variant_for_this_iteration = eval_output
                                        print(f"  Variant {eval_output['variant_id']} has evaluation results. Tentatively selecting as fallback.")


                            if best_variant_for_this_iteration:
                                print(f"  Best variant for iteration {iteration} (Step {iteration}.6) is {best_variant_for_this_iteration['variant_id']}.")
                                print(f"  Its profiler output: {best_variant_for_this_iteration['profiler_output_path']}")
                                # Update the baseline for the *next* iteration's Analyzer
                                baseline_profiler_output_for_next_iteration = best_variant_for_this_iteration['profiler_output_path']
                            else:
                                print(f"  No clearly improved variant found in iteration {iteration} (Step {iteration}.6). The baseline for the next iteration will remain: {baseline_profiler_output_for_next_iteration}")
                        else:
                            print(f"No variants were successfully evaluated in iteration {iteration} (Step {iteration}.5). Baseline remains: {baseline_profiler_output_for_next_iteration}")
                        # --- End of best variant determination ---

                if iteration < args.iterations:
                    print(f"Iteration {iteration} for file {original_file_name} finished. Baseline for next iteration ({iteration + 1}) is: {baseline_profiler_output_for_next_iteration}")
                else: # Last iteration
                    print(f"All {args.iterations} iterations completed for file {original_file_name}.")
                    if baseline_profiler_output_for_next_iteration != profiler_output_path: # profiler_output_path is the initial one for the file
                        print(f"Final selected baseline profile after {args.iterations} iterations: {baseline_profiler_output_for_next_iteration}")
                    else:
                        print(f"No improvement over the initial profile was identified as a new baseline after {args.iterations} iterations. Original profile: {profiler_output_path}")

            except Exception as e:
                print(f"Pipeline error (during iteration {iteration}, file {original_file_name}): {e}")
                import traceback
                traceback.print_exc()
                break 
        
        print(f"Completed all iterations for file: {current_source_file_abs_path}")
    
    pipeline_overall_end_time = time.time()
    print(f"\nOptimizer Pipeline finished processing all files in {(pipeline_overall_end_time - pipeline_overall_start_time):.2f}s. Outputs in: {args.output_dir}")

if __name__ == "__main__":
    main() 