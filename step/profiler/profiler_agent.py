# See LICENSE for details

import os
import json
import tempfile
import subprocess
from typing import Optional, List, Dict, Any, Union
import openai
import sys
import logging
import argparse
import shutil

# --- Path Setup for Importing Tools ---
# This ensures that when 'profiler_agent.py' is run, the 'profiling-agent' directory is in sys.path
# so that 'tool' can be imported as a top-level package.
agent_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(agent_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Tool Imports ---
from tool.tool import Tool
from tool.compile.cpp_compiler import CppCompiler
from tool.perf.perf_tool import PerfTool

logger = logging.getLogger(__name__)

class ProfilingAgent(Tool):
    """
    ProfilingAgent: A tool that automates the profiling and optimization of compiled binaries.
    
    This tool uses system profiling tools (perf via perf_tool.py, redspy, zerospy, loadspy) 
    and a compiler tool (cpp_compiler.py) to identify performance bottlenecks, 
    converts the profiling data to a structured format,
    and uses OpenAI's API to generate optimization suggestions.
    """

    def __init__(self, openai_model: str = 'gpt-4'):
        """
        Initialize the ProfilingAgent tool.
        """
        super().__init__()
        self.perf_tool = PerfTool()
        self.cpp_compiler = CppCompiler()
        self._openai_key = None
        self._openai_model = openai_model
        
        # Directory setup based on project structure (e.g., data/compile, data/perf)
        # Paths are relative to the project root.
        self.PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # parent of agent/
        self.BASE_DATA_DIR = os.path.join(self.PROJECT_ROOT, "data")
        self.COMPILE_DIR = os.path.join(self.BASE_DATA_DIR, "compile")
        self.PERF_DATA_DIR = os.path.join(self.BASE_DATA_DIR, "perf")
        self.SOURCES_DIR = os.path.join(self.BASE_DATA_DIR, "sources") 

        # Ensure these directories exist
        os.makedirs(self.COMPILE_DIR, exist_ok=True)
        os.makedirs(self.PERF_DATA_DIR, exist_ok=True)
        os.makedirs(self.SOURCES_DIR, exist_ok=True)

        # Create a session-specific temporary directory within self.PERF_DATA_DIR
        # The TemporaryDirectory object will handle cleanup of this session directory.
        self._temp_dir_obj = tempfile.TemporaryDirectory(prefix='profagent_session_', dir=self.PERF_DATA_DIR)
        self._temp_dir = self._temp_dir_obj.name
        logger.debug(f"ProfilingAgent session temporary directory created at: {self._temp_dir}")

        # Placeholder for the name of the main C++ source file to be compiled after modifications
        # This might need to be passed in or inferred.
        self._main_cpp_file_name_for_recompile = "sample.cpp" # Example, adjust as needed
        
    def setup(self, 
              openai_api_key: Optional[str] = None, 
              openai_model: Optional[str] = None) -> bool:
        """
        Set up the ProfilingAgent tool with OpenAI credentials.
        
        Args:
            openai_api_key: The OpenAI API key. If None, uses OPENAI_API_KEY env var.
            openai_model: The OpenAI model to use. If None, uses the model set at init.
            
        Returns:
            True if setup was successful, False otherwise.
        """
        self._is_ready = False
        self.error_message = ''
        
        self._openai_key = openai_api_key or os.environ.get('OPENAI_API_KEY')
        if not self._openai_key:
            self.set_error('OpenAI API key not provided and OPENAI_API_KEY environment variable not set.')
            logger.error(self.error_message)
            return False
            
        if openai_model:
            self._openai_model = openai_model
        
        # PerfTool and CppCompiler are instantiated in __init__.
        # Their own setup methods will be called when they are used with specific arguments.
        # This agent's setup is primarily for ensuring OpenAI access is configured.
        
        self._is_ready = True
        logger.info(f"ProfilingAgent setup successful with OpenAI model: {self._openai_model}.")
        return True
    

    def profile_binary(self, 
                      binary_path: str, 
                      source_dir: str, # Used for _extract_source_context
                      args: Optional[List[str]] = None, 
                      tools: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Profile a binary using available profiling tools (currently focused on perf).
        
        Args:
            binary_path: Path to the compiled binary to profile
            source_dir: Path to the source code directory (for context extraction)
            args: Optional list of arguments to pass to the binary
            tools: Optional list of profiling tools to use. Defaults to ['perf'].
            
        Returns:
            A dictionary containing the profiling results.
        """
        if not self._is_ready:
            self.set_error('ProfilingAgent tool is not set up. Please run setup first.')
            logger.error(self.error_message)
            return {}
            
        if not os.path.exists(binary_path) or not os.access(binary_path, os.X_OK):
            self.set_error(f'Binary not found or not executable: {binary_path}')
            logger.error(self.error_message)
            return {}
            
        if not os.path.isdir(source_dir):
            self.set_error(f'Source directory not found: {source_dir}')
            logger.error(self.error_message)
            return {}
            
        active_tools = tools if tools is not None else ['perf'] # Default to perf
        profile_results = {}

        # Ensure binary is compiled with debug symbols (important for perf and source mapping)
        if not self._check_debug_symbols(binary_path):
            logger.warning(f'Binary {binary_path} may not have debug symbols. Compile with -g for best results.')
            # Perf can still run, so this is a warning, not an error.

        if 'perf' in active_tools:
            # _run_perf now uses self.perf_tool and needs the output directory for perf.data
            # For profile_binary, perf data can be considered temporary for this specific run.
            # Let's use the agent's temp directory for this.
            # The PERF_DATA_DIR is more for long-term storage if PerfTool is used directly.
            # However, _run_perf expects output_perf_data_dir argument.
            # We can use a sub-directory within self._temp_dir for isolation of perf data files.
            temp_perf_output_dir = os.path.join(self._temp_dir, "perf_data_for_profile_binary")
            os.makedirs(temp_perf_output_dir, exist_ok=True)
            
            logger.info(f"Running perf via _run_perf for binary: {binary_path}")
            # _run_perf itself will place perf.data into a path derived from temp_perf_output_dir
            perf_result = self._run_perf(binary_path, output_perf_data_dir=temp_perf_output_dir, args=args) 
            if perf_result:
                profile_results['perf'] = perf_result
            elif self.error_message: # If _run_perf set an error
                logger.error(f"Perf profiling failed: {self.error_message}")
                # Potentially return {} or let _extract_source_context handle empty perf_result

        # Future: Add calls to other tools like redspy, zerospy, loadspy if they are in active_tools
        # and if their respective _run_* methods and status checks are implemented.
        # Example structure if redspy were to be re-enabled:
        # if 'redspy' in active_tools and self._profiling_tools_status.get('redspy'): 
        #     profile_results['redspy'] = self._run_redspy(binary_path, args)
                
        # Extract source code for hotspots using the original source_dir if perf data exists
        if profile_results.get('perf'):
            logger.info(f"Extracting source context from perf results for sources in {source_dir}")
            profile_results = self._extract_source_context(profile_results, source_dir)
        else:
            logger.info("No perf data in profile_results to extract source context from.")
                
        return profile_results
    
    def get_optimization_suggestions(self, 
                                    profile_results: Dict[str, Any],
                                    source_context: Dict[str, str]) -> Dict[str, Any]:
        """
        Use OpenAI API to get optimization suggestions based on profiling results.
        
        Args:
            profile_results: Dictionary of profiling results from profile_binary
            source_context: Dictionary mapping file paths to source code
            
        Returns:
            Dictionary containing optimization suggestions
        """
        if not self._is_ready:
            self.set_error('ProfilingAgent tool is not set up. Please run setup first.')
            logger.error(self.error_message)
            return {}
            
        # Check if we have any hotspots to analyze
        if not profile_results or not any(
            tool_results.get('raw_report', '') 
            for tool_name, tool_results in profile_results.items()
        ):
            self.set_error('No performance hotspots found in the profiling results')
            return {}
            
        # If we don't have any source context, there's nothing to optimize
        if not source_context:
            self.set_error('No source code context available for optimization')
            return {}
            
        # Construct the prompt for OpenAI
        prompt = self._construct_optimization_prompt(profile_results, source_context)
        
        # Call OpenAI API
        try:
            # Ensure we have a valid key
            openai.api_key = self._openai_key
            
            completion = openai.chat.completions.create(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": (
                        "You are an expert compiler and performance optimization assistant. "
                        "Analyze the profiling data and source code to suggest specific, "
                        "actionable optimizations. Format your response as JSON with both "
                        "natural language explanations and code snippets where appropriate."
                    )},
                    {"role": "user", "content": prompt}
                ]
            )
            response = completion.choices[0].message.content
            suggestions = json.loads(response)
            return suggestions
        except Exception as e:
            self.set_error(f'Error calling OpenAI API: {str(e)}')
            return {}
            
    def optimize_binary(self, 
                       initial_source_dir: str, 
                       main_source_file: str, # e.g., "sample.cpp" within initial_source_dir
                       output_dir_name_prefix: str = "optimized_run",
                       args: Optional[List[str]] = None,
                       max_iterations: int = 3) -> Dict[str, Any]:
        """
        Full pipeline: compile, profile, get suggestions, apply, recompile, and iterate.
        
        Args:
            initial_source_dir: Path to the original source code directory.
            main_source_file: Name of the main C++ file to compile (relative to source_dir).
            output_dir_name_prefix: Prefix for the iteration's output directory within self.SOURCES_DIR.
            args: Optional arguments to pass to the binary during profiling.
            max_iterations: Maximum optimization iterations to attempt.
            
        Returns:
            Dictionary with optimization results and file paths.
        """
        if not self._is_ready:
            self.set_error('ProfilingAgent tool is not set up. Please run setup first.')
            logger.error(self.error_message)
            return {}

        results = {
            "iterations": [],
            "final_optimized_source_dir": None,
            "final_binary_path": None,
            "success": False,
            "error": None
        }
        
        current_iteration_source_dir = initial_source_dir
        
        # Initial compilation
        iteration_executable_name = f"{os.path.splitext(main_source_file)[0]}_iter0_initial"
        initial_compile_output_path = os.path.join(self.COMPILE_DIR, iteration_executable_name)
        
        logger.info(f"Attempting initial compilation of: {os.path.join(current_iteration_source_dir, main_source_file)}")
        compile_setup_ok = self.cpp_compiler.setup(
            source_files=[os.path.join(current_iteration_source_dir, main_source_file)],
            output_executable=initial_compile_output_path,
            optimization_preset="debug_opt" # Compile with debug symbols and optimization
        )

        if not compile_setup_ok:
            err_msg = f"Failed to setup CppCompiler for initial source: {self.cpp_compiler.get_error()}"
            self.set_error(err_msg)
            logger.error(err_msg)
            results["iterations"].append({"iteration": 0, "status": "initial_compile_setup_failed", "error": err_msg})
            results["error"] = err_msg
            return results

        compile_success, stdout, stderr = self.cpp_compiler.compile()
        current_binary_path = self.cpp_compiler.output_executable if compile_success else None

        if not current_binary_path:
            err_msg = f"Failed to compile initial source: {os.path.join(current_iteration_source_dir, main_source_file)}. Compiler Stderr: {stderr}"
            self.set_error(err_msg)
            logger.error(err_msg)
            results["iterations"].append({"iteration": 0, "status": "initial_compile_failed", "error": self.error_message})
            results["error"] = self.error_message
            return results

        logger.info(f"Initial compilation successful: {current_binary_path}")

        for i in range(max_iterations):
            iteration_num = i + 1
            logger.info(f"--- Starting Optimization Iteration {iteration_num} ---")
            iteration_results = {"iteration": iteration_num, "status": "pending"}

            iter_source_output_dir = os.path.join(self.SOURCES_DIR, f"{output_dir_name_prefix}_iter{iteration_num}_base")
            if os.path.exists(iter_source_output_dir):
                shutil.rmtree(iter_source_output_dir) 
            os.makedirs(iter_source_output_dir)

            # Determine if we need to ignore prefixes for this copy operation
            # Only ignore if the source is the initial_source_dir provided by the user
            ignore_prefixes_for_copy = [output_dir_name_prefix] if current_iteration_source_dir == initial_source_dir else None
            
            self._copy_source_files(
                current_iteration_source_dir, 
                iter_source_output_dir,
                top_level_dirs_to_ignore_prefixes=ignore_prefixes_for_copy
            )
            working_source_dir = iter_source_output_dir 

            # 1. Profile the current binary (which was compiled from working_source_dir or initial_source_dir)
            logger.info(f"Profiling binary: {current_binary_path} for sources in {working_source_dir}")
            # The source_dir for profile_binary should be where the *currently compiled* binary's sources are
            profile_data = self.profile_binary(current_binary_path, working_source_dir, args) 
            if not profile_data and self.error_message:
                iteration_results.update({"status": "profile_failed", "error": self.error_message})
                results["iterations"].append(iteration_results)
                logger.error(f"Profiling failed in iteration {iteration_num}: {self.error_message}")
                results["error"] = self.error_message
                break 
            iteration_results["profile_results"] = profile_data
            
            # Check for hotspots before proceeding
            if not profile_data.get('perf', {}).get('raw_report'):
                logger.info("No raw report found in profiling data. Ending optimization iterations.")
                iteration_results.update({"status": "no_raw_report_found"})
                results["iterations"].append(iteration_results)
                # Consider this a success if it ran through, just nothing to optimize
                if not results["final_binary_path"]: # If this is the first iteration and no hotspots
                    results["final_optimized_source_dir"] = current_iteration_source_dir
                    results["final_binary_path"] = current_binary_path
                results["success"] = True 
                break

            source_context_for_llm = {}
            if profile_data.get('perf', {}).get('raw_report'):
                for root, dirs, files in os.walk(working_source_dir):
                    for file in files:
                        if file.endswith(('.cpp', '.c', '.h', '.hpp', '.rs')):
                            file_path = os.path.join(root, file)
                            with open(file_path, 'r') as f:
                                source_context_for_llm[os.path.relpath(file_path, working_source_dir)] = f.read()
            
            if not source_context_for_llm:
                 logger.warning("No source context extracted from profiling, cannot get suggestions.")
                 iteration_results.update({"status": "no_source_context_for_llm", "error": "No source context for LLM suggestions."})
                 results["iterations"].append(iteration_results)
                 # Don't mark as overall failure yet, existing binary is still the best
                 if not results["final_binary_path"]:
                     results["final_optimized_source_dir"] = current_iteration_source_dir
                     results["final_binary_path"] = current_binary_path
                 results["success"] = True
                 break

            logger.info("Getting optimization suggestions...")
            # suggestions_response will contain 'analysis' and 'optimization_variants'
            suggestions_response = self.get_optimization_suggestions(profile_data, source_context_for_llm)
            if not suggestions_response or 'optimization_variants' not in suggestions_response:
                err_msg = f"Failed to get valid suggestions or no optimization variants provided: {self.error_message or 'No variants in response'}"
                iteration_results.update({"status": "suggestions_failed", "error": err_msg})
                results["iterations"].append(iteration_results)
                logger.error(err_msg)
                results["error"] = err_msg
                break
            
            optimization_variants = suggestions_response.get('optimization_variants', [])
            iteration_results["suggestions_analysis"] = suggestions_response.get('analysis')
            iteration_results["suggested_variants_count"] = len(optimization_variants)

            if not optimization_variants:
                logger.info("No optimization variants suggested by the LLM. Ending iterations.")
                iteration_results["status"] = "no_variants_suggested"
                results["iterations"].append(iteration_results)
                if not results["final_binary_path"]:
                    results["final_optimized_source_dir"] = current_iteration_source_dir
                    results["final_binary_path"] = current_binary_path
                results["success"] = True
                break

            best_variant_perf_data = None
            best_variant_binary_path = None
            best_variant_source_dir = None
            
            # To compare with baseline (current binary before applying variants)
            # We need to measure current_binary_path's performance properly
            # For simplicity, we'll assume lower perf script "overhead" percentage or similar simple metric from parsed data.
            # A more robust way would be to run a benchmark function and get execution time.
            # For now, let's assume profile_data of current_binary_path is the baseline.

            variants_tried_details = []

            for variant_idx, opt_variant in enumerate(optimization_variants):
                variant_name = f"variant{variant_idx + 1}"
                logger.info(f"Processing {variant_name} for iteration {iteration_num}...")
                
                variant_source_dir = os.path.join(self.SOURCES_DIR, f"{output_dir_name_prefix}_iter{iteration_num}_{variant_name}")
                self._copy_source_files(working_source_dir, variant_source_dir) # Copy base of this iteration

                logger.info(f"Applying optimization for {variant_name} to: {variant_source_dir}")
                # _apply_optimizations now takes a single variant
                optimization_applied = self._apply_optimizations_to_variant(opt_variant, variant_source_dir)
                
                if not optimization_applied:
                    logger.warning(f"No changes applied for {variant_name}. Skipping this variant.")
                    variants_tried_details.append({
                        "variant_name": variant_name, "status": "no_changes_applied", 
                        "source_dir": variant_source_dir, "binary_path": None, "perf_results": None
                    })
                    continue

                logger.info(f"Recompiling modified code for {variant_name} from: {variant_source_dir}")
                variant_executable_name = f"{os.path.splitext(main_source_file)[0]}_iter{iteration_num}_{variant_name}"
                variant_compile_output_path = os.path.join(self.COMPILE_DIR, variant_executable_name)

                compile_setup_ok = self.cpp_compiler.setup(
                    source_files=[os.path.join(variant_source_dir, main_source_file)],
                    output_executable=variant_compile_output_path,
                    optimization_preset="debug_opt"
                )
                if not compile_setup_ok:
                    logger.error(f"CppCompiler setup failed for {variant_name}: {self.cpp_compiler.get_error()}")
                    variants_tried_details.append({
                        "variant_name": variant_name, "status": "recompile_setup_failed", "source_dir": variant_source_dir, 
                        "error": self.cpp_compiler.get_error()
                    })
                    continue
                
                variant_compile_success, _, comp_stderr = self.cpp_compiler.compile()
                new_variant_binary_path = self.cpp_compiler.output_executable if variant_compile_success else None

                if not new_variant_binary_path:
                    logger.error(f"Recompilation failed for {variant_name}. Stderr: {comp_stderr}")
                    variants_tried_details.append({
                        "variant_name": variant_name, "status": "recompile_failed", "source_dir": variant_source_dir,
                        "error": f"Compilation failed. Stderr: {comp_stderr}"
                    })
                    continue
                
                logger.info(f"Recompilation successful for {variant_name}: {new_variant_binary_path}")
                logger.info(f"Profiling {variant_name} binary: {new_variant_binary_path}")
                variant_perf_data = self.profile_binary(new_variant_binary_path, variant_source_dir, args)
                variants_tried_details.append({
                    "variant_name": variant_name, "status": "profiled", "source_dir": variant_source_dir,
                    "binary_path": new_variant_binary_path, "perf_results": variant_perf_data
                })

                # TODO: Implement robust performance comparison logic
                # For now, let's say the first one that compiles and profiles is "better"
                # Or, if we have perf data, the one with fewer/less costly hotspots
                if variant_perf_data: # Simplified comparison
                    if best_variant_binary_path is None or self._is_perf_better(variant_perf_data, best_variant_perf_data):
                        logger.info(f"{variant_name} ({new_variant_binary_path}) is currently the best in this iteration.")
                        # Clean up previous best variant's binary if it exists and is different
                        if best_variant_binary_path and os.path.exists(best_variant_binary_path) and best_variant_binary_path != new_variant_binary_path:
                            try: os.remove(best_variant_binary_path)
                            except OSError as e: logger.warning(f"Could not remove old best variant binary {best_variant_binary_path}: {e}")
                        
                        best_variant_perf_data = variant_perf_data
                        best_variant_binary_path = new_variant_binary_path
                        best_variant_source_dir = variant_source_dir
                    else: # Not better, clean up this variant's binary
                        logger.info(f"{variant_name} ({new_variant_binary_path}) is not better than current best. Cleaning it up.")
                        if os.path.exists(new_variant_binary_path):
                            try: os.remove(new_variant_binary_path)
                            except OSError as e: logger.warning(f"Could not remove non-best variant binary {new_variant_binary_path}: {e}")
                else: # Profiling failed for this variant, clean up its binary
                    logger.warning(f"Profiling failed for {variant_name} ({new_variant_binary_path}). Cleaning it up.")
                    if os.path.exists(new_variant_binary_path):
                            try: os.remove(new_variant_binary_path)
                            except OSError as e: logger.warning(f"Could not remove failed-profile variant binary {new_variant_binary_path}: {e}")


            iteration_results["variants_tried"] = variants_tried_details

            if best_variant_binary_path:
                logger.info(f"Best variant in iteration {iteration_num} is from: {best_variant_source_dir}, binary: {best_variant_binary_path}")
                # Clean up the binary that was the input to this iteration if it's different from the new best
                if current_binary_path and os.path.exists(current_binary_path) and current_binary_path != best_variant_binary_path:
                    try:
                        os.remove(current_binary_path)
                        logger.info(f"Cleaned up old binary from previous step/iteration: {current_binary_path}")
                    except OSError as e:
                        logger.warning(f"Could not remove old binary {current_binary_path}: {e}")
                
                current_binary_path = best_variant_binary_path
                current_iteration_source_dir = best_variant_source_dir # This becomes input for next iter or final output

                iteration_results["status"] = "success"
                iteration_results["selected_variant_source_dir"] = best_variant_source_dir
                iteration_results["selected_variant_binary_path"] = best_variant_binary_path
                iteration_results["selected_variant_perf_data"] = best_variant_perf_data
                results["iterations"].append(iteration_results)
                
                results["success"] = True # At least one iteration was successful
                results["final_optimized_source_dir"] = current_iteration_source_dir
                results["final_binary_path"] = current_binary_path
            else:
                logger.warning(f"No viable optimization variant found or improved performance in iteration {iteration_num}.")
                iteration_results["status"] = "no_improvement_or_all_variants_failed"
                results["iterations"].append(iteration_results)
                # Keep current_binary_path and current_iteration_source_dir as they were
                # The overall success might still be true if previous iterations yielded something
                if not results["final_binary_path"]: # If this was the first iteration and it failed to improve
                    results["final_optimized_source_dir"] = initial_source_dir # Or the working_source_dir before variants
                    results["final_binary_path"] = current_binary_path # The one profiled at start of iter
                break # End iterations if no improvement

            if iteration_num == max_iterations:
                logger.info("Max iterations reached.")
                break
        
        if not results["success"] and not results["error"]:
            results["error"] = "Optimization pipeline completed but did not yield a successful outcome or improvement."
            logger.info(results["error"])
        elif results["success"] and results["final_binary_path"]:
             logger.info(f"Optimization finished. Final best binary: {results['final_binary_path']}, from sources: {results['final_optimized_source_dir']}")
        elif not results["final_binary_path"] and current_binary_path: # e.g. initial compile ok, but no improvements
            logger.info(f"Optimization finished. No improvements over initial. Final binary: {current_binary_path}")
            results["final_optimized_source_dir"] = initial_source_dir # Or the source dir for current_binary_path
            results["final_binary_path"] = current_binary_path
            results["success"] = True


        return results
    
    def _is_perf_better(self, new_perf_data: Dict[str, Any], old_perf_data: Optional[Dict[str, Any]]) -> bool:
        """
        Basic comparison of perf data.
        TODO: Implement a more robust comparison.
        For now, returns True if new_perf_data has hotspots and old_perf_data is None,
        or if new_perf_data has fewer hotspots or primary hotspot has lower percentage.
        """
        if not new_perf_data or not new_perf_data.get('perf', {}).get('hotspots'):
            return False # New data is bad or no hotspots
        if old_perf_data is None or not old_perf_data.get('perf', {}).get('hotspots'):
            return True # Old data was non-existent or had no hotspots, so new is better if it has some

        new_hotspots = new_perf_data['perf']['hotspots']
        old_hotspots = old_perf_data['perf']['hotspots']

        if not new_hotspots: return False # No new hotspots means something might be wrong or too good to be true without benchmark
        if not old_hotspots: return True # New has hotspots, old didn't, this is an improvement in profiling terms

        # Compare primary hotspot CPU time if available
        try:
            new_primary_cpu = float(new_hotspots[0].get("cpu_time", "101%").rstrip('%'))
            old_primary_cpu = float(old_hotspots[0].get("cpu_time", "100%").rstrip('%'))
            if new_primary_cpu < old_primary_cpu:
                return True
            # If primary is same, check number of hotspots as a rough tie-breaker
            # if new_primary_cpu == old_primary_cpu and len(new_hotspots) < len(old_hotspots):
            #     return True
        except (ValueError, IndexError):
            pass # Could not parse CPU times, fallback

        # Fallback: less hotspots is better (very rough)
        # return len(new_hotspots) < len(old_hotspots)
        return False # Default to not better if primary hotspot isn't clearly better

    def _check_debug_symbols(self, binary_path: str) -> bool:
        """Check if binary has debug symbols using readelf."""
        try:
            # Use self.run_command from base Tool class
            result = self.run_command(['readelf', '-S', binary_path], capture_output=True, text=True)
            if result and result.stdout:
                return '.debug_info' in result.stdout or '.symtab' in result.stdout
            elif result and result.returncode != 0:
                logger.warning(f"readelf check for debug symbols failed for {binary_path}. Stderr: {result.stderr}")
        except Exception as e:
            logger.warning(f"Exception checking debug symbols for {binary_path}: {e}")
        # Default to True if check fails, to allow proceeding. Perf might still work partially.
        logger.info(f"Could not definitively confirm debug symbols for {binary_path}, assuming present or proceeding anyway.")
        return True
            
    def _run_perf(self, binary_path: str, output_perf_data_dir:str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run perf profiling using PerfTool instance and parse results."""
        
        base_name = os.path.basename(binary_path)
        # Generate a unique name for the perf.data file within the iteration/variant
        # The tempfile part is a bit obscure, let's simplify.
        # A timestamp or a counter within the run could also work.
        unique_suffix = tempfile.NamedTemporaryFile(prefix='', delete=True).name.split('/')[-1]
        perf_data_filename = f"perf_{base_name}_{unique_suffix}.data"
        full_perf_data_path = os.path.join(output_perf_data_dir, perf_data_filename)

        logger.info(f"Running perf record. Output data file: {full_perf_data_path}, Binary: {binary_path}")
        
        setup_ok = self.perf_tool.setup(
            target_executable=binary_path,
            target_args=args,
            perf_data_file=full_perf_data_path # PerfTool will use this path
        )
        if not setup_ok:
            self.set_error(f"PerfTool setup failed for {binary_path}: {self.perf_tool.get_error()}")
            logger.error(self.error_message)
            return {}

        # Default record_args: -g for call graphs. Can be configured.
        record_success, rec_stdout, rec_stderr = self.perf_tool.record(record_args=["-g"])

        if not record_success:
            self.set_error(f"PerfTool record command failed for {binary_path}. Error: {self.perf_tool.get_error()}."
                           f"Stdout: {rec_stdout}, Stderr: {rec_stderr}")
            logger.error(self.error_message)
            # No perf.data file to clean up if record itself failed before creating it,
            # or if PerfTool's record handles its own data file on failure.
            return {}

        logger.info(f"Perf data collected: {full_perf_data_path}")
        
        # Generate report string using PerfTool's report (in script mode for parsing)
        logger.info(f"Generating perf report (script mode) from: {full_perf_data_path}")
        report_success, report_string, rep_stderr = self.perf_tool.report(use_script_mode=False) # Gets perf script output

        if not report_success:
            self.set_error(f"PerfTool report generation failed for {full_perf_data_path}. Error: {self.perf_tool.get_error()}."
                           f"Stderr: {rep_stderr}")
            logger.error(self.error_message)
            # Clean up the perf.data file if report generation failed
            if os.path.exists(full_perf_data_path):
                try: os.remove(full_perf_data_path)
                except OSError: pass 
            return {}

        # Clean up the specific perf.data file after successful report generation and parsing
        if os.path.exists(full_perf_data_path):
            try:
                os.remove(full_perf_data_path)
                logger.info(f"Cleaned up perf data file: {full_perf_data_path}")
            except OSError as e:
                logger.warning(f"Could not remove perf data file {full_perf_data_path}: {e}")

        return {"tool": "perf", "raw_report": report_string}
            
    def _run_redspy(self, binary_path: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Placeholder for RedSpy tool integration."""
        # In a real implementation, this would run RedSpy tool
        return {"tool": "redspy", "status": "not_implemented"}
            
    def _run_zerospy(self, binary_path: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Placeholder for ZeroSpy tool integration."""
        # In a real implementation, this would run ZeroSpy tool
        return {"tool": "zerospy", "status": "not_implemented"}
            
    def _run_loadspy(self, binary_path: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Placeholder for LoadSpy tool integration."""
        # In a real implementation, this would run LoadSpy tool
        return {"tool": "loadspy", "status": "not_implemented"}
            
    def _extract_source_context(self, profile_results: Dict[str, Any], source_dir: str) -> Dict[str, Any]:
        """Extract source code context for each hotspot."""
        # Don't reset the is_ready state during extraction
        error_state = self.error_message
        ready_state = self._is_ready
        
        for tool_name, tool_results in profile_results.items():
            if tool_name == 'perf' and 'hotspots' in tool_results:
                for hotspot in tool_results['hotspots']:
                    if 'file' in hotspot and 'line' in hotspot:
                        file_path = hotspot['file']
                        line_number = hotspot['line']
                        
                        # Skip unknown source locations
                        if file_path == "unknown":
                            continue
                        
                        # If the file path is absolute, use it directly
                        if not os.path.isabs(file_path):
                            file_path = os.path.join(source_dir, file_path)
                            
                        try:
                            if os.path.exists(file_path):
                                with open(file_path, 'r') as f:
                                    lines = f.readlines()
                                    
                                # Extract context (10 lines before and after)
                                start = max(0, line_number - 10)
                                end = min(len(lines), line_number + 10)
                                context = ''.join(lines[start:end])
                                hotspot['source_context'] = context
                                hotspot['source_start_line'] = start + 1
                        except Exception as e:
                            print(f'Warning: Error extracting source context: {str(e)}')
                            # Don't set error_message to avoid resetting is_ready state
        
        # Restore error state only if it wasn't already set
        if not self.error_message:
            self.error_message = error_state
        
        # Restore ready state
        self._is_ready = ready_state
                            
        return profile_results
        
    def _construct_optimization_prompt(self, profile_results: Dict[str, Any], source_context: Dict[str, str]) -> str:
        """Construct prompt for OpenAI API with profiling results and source context."""
        prompt = "Based on the following profiling data:\n"
        prompt += json.dumps(profile_results, indent=2)
        
        prompt += "\n\nAnd the source code context:\n"
        for file_path, source in source_context.items():
            prompt += f"\nFile: {file_path}\n```\n{source}\n```\n"
            
        prompt += "\nPlease analyze the performance bottlenecks and suggest optimizations. "
        prompt += "Your response should be a JSON object. This JSON object should contain a key 'optimization_variants', "
        prompt += "which is a list of up to 3 distinct approaches to optimize the code. "
        prompt += "Each item in the list should represent a complete, self-contained optimization variant."
        prompt += "\nFor each optimization variant, provide:"
        prompt += "\n1. A brief 'variant_description' of the optimization strategy used."
        prompt += "\n2. The 'file' path (relative to the source directory) that is modified."
        prompt += "\n3. The 'original_code' snippet that is targeted for optimization."
        prompt += "\n4. The 'optimized_code' snippet representing the complete optimized version of that section or function."
        prompt += "\n5. An 'expected_improvement' note (e.g., 'reduces CPU cycles by X%', 'improves memory access patterns')."
        
        prompt += "\n\nFormat your response as a JSON object with the following structure:\n"
        prompt += "{\n"
        prompt += '  "analysis": "Overall analysis of the performance issues based on profiling data.",\n'
        prompt += '  "optimization_variants": [\n'
        prompt += '    {\n'
        prompt += '      "variant_description": "Description of optimization strategy for variant 1",\n'
        prompt += '      "file": "path/to/file.cpp",\n'
        prompt += '      "original_code": "The problematic code snippet for variant 1",\n'
        prompt += '      "optimized_code": "The improved code snippet for variant 1",\n'
        prompt += '      "expected_improvement": "Estimated performance gain for variant 1"\n'
        prompt += '    },\n'
        prompt += '    {\n'
        prompt += '      "variant_description": "Description of optimization strategy for variant 2",\n'
        prompt += '      "file": "path/to/file.cpp",\n'
        prompt += '      "original_code": "The problematic code snippet for variant 2 (can be same or different from variant 1)",\n'
        prompt += '      "optimized_code": "The improved code snippet for variant 2",\n'
        prompt += '      "expected_improvement": "Estimated performance gain for variant 2"\n'
        prompt += '    },\n'
        prompt += '    // ... up to 3 variants ...\n'
        prompt += '  ]\n'
        prompt += '}'
        
        return prompt
        
    def _get_source_context(self, profile_results: Dict[str, Any], source_dir: str) -> Dict[str, str]:
        """Extract source code context from profiling results."""
        source_context = {}
        
        # Save the current state
        error_state = self.error_message
        ready_state = self._is_ready
        
        for tool_name, tool_results in profile_results.items():
            if tool_name == 'perf' and 'hotspots' in tool_results:
                for hotspot in tool_results['hotspots']:
                    if 'file' in hotspot:
                        file_path = hotspot['file']
                        
                        # Skip unknown files
                        if file_path == "unknown":
                            continue
                        
                        # If we haven't loaded this file yet
                        if file_path not in source_context:
                            # If the file path is absolute, use it directly
                            full_path = file_path if os.path.isabs(file_path) else os.path.join(source_dir, file_path)
                            
                            try:
                                if os.path.exists(full_path):
                                    with open(full_path, 'r') as f:
                                        source_context[file_path] = f.read()
                            except Exception as e:
                                print(f'Warning: Error reading source file {full_path}: {str(e)}')
                                # Don't set error_message to avoid resetting is_ready state
        
        # If we found no source context but have the sample.cpp file, use it as a fallback
        if not source_context:
            sample_path = os.path.join(source_dir, "sample.cpp")
            if os.path.exists(sample_path):
                try:
                    with open(sample_path, 'r') as f:
                        source_context["sample.cpp"] = f.read()
                except Exception:
                    pass
        
        # Restore error state only if it wasn't already set
        if not self.error_message:
            self.error_message = error_state
        
        # Restore ready state
        self._is_ready = ready_state
                                
        return source_context
        
    def _copy_source_files(self, source_dir: str, output_dir: str, top_level_dirs_to_ignore_prefixes: Optional[List[str]] = None) -> None:
        """Copy relevant source files from source_dir to output_dir, maintaining structure.
        If top_level_dirs_to_ignore_prefixes is provided, directories in the immediate top-level of source_dir
        whose names start with any of these prefixes will be ignored during the walk.
        """
        # Ensure output_dir exists; if not, create it.
        # The caller (optimize_binary) is responsible for ensuring output_dir is clean if needed.
        os.makedirs(output_dir, exist_ok=True)
        
        logger.debug(f"Copying source files from '{source_dir}' to '{output_dir}' (ignoring top-level dir prefixes: {top_level_dirs_to_ignore_prefixes})")
        copied_any = False
        for root, dirs, files in os.walk(source_dir):
            if root == source_dir and top_level_dirs_to_ignore_prefixes:
                # Filter out directories at the top level of source_dir that match any of the ignore prefixes
                # Modify dirs in-place to prevent os.walk from traversing them
                dirs[:] = [d for d in dirs if not any(d.startswith(prefix) for prefix in top_level_dirs_to_ignore_prefixes)]

            for file in files:
                # Filter for common C/C++ and Rust source/header files
                if file.endswith(('.c', '.cpp', '.cc', '.h', '.hpp', '.hxx', '.cxx', '.hh', '.rs')):
                    source_path = os.path.join(root, file)
                    
                    relative_path = os.path.relpath(source_path, source_dir)
                    dest_path = os.path.join(output_dir, relative_path)
                    
                    try:
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(source_path, dest_path)
                        logger.debug(f"Copied: {source_path} -> {dest_path}")
                        copied_any = True
                    except Exception as e:
                        logger.warning(f"Warning: Error copying file {source_path} to {dest_path}: {str(e)}")
        if not copied_any:
            logger.warning(f"No source files were copied from '{source_dir}' to '{output_dir}'. Check filters or source_dir contents.")
                    
    def _apply_optimizations_to_variant(self, optimization_variant: Dict[str, Any], source_dir_for_variant: str) -> bool:
        """Apply a single optimization variant to source files in the specified directory."""
        changes_made = False
        
        # Current state saving/restoring might not be strictly necessary here if errors are logged
        # and don't stop the entire agent, but can be kept for safety.
        # error_state = self.error_message 
        # ready_state = self._is_ready
        
        # The variant itself is the 'opt' from the previous loop
        opt = optimization_variant 
        
        if all(key in opt for key in ['file', 'original_code', 'optimized_code']):
            file_path_in_suggestion = opt['file'] # This is relative to the original source structure
            original_code = opt['original_code']
            optimized_code = opt['optimized_code']
            
            # The actual file to modify is in source_dir_for_variant
            full_path_to_modify = os.path.join(source_dir_for_variant, file_path_in_suggestion)
            
            if not os.path.exists(full_path_to_modify):
                logger.warning(f"File not found for applying optimization: {full_path_to_modify} (original suggested: {file_path_in_suggestion})")
                return False # Critical file missing for this variant
                
            try:
                with open(full_path_to_modify, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                if original_code in content:
                    new_content = content.replace(original_code, optimized_code, 1) # Replace only the first instance
                    
                    with open(full_path_to_modify, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    logger.info(f"Applied optimization to: {full_path_to_modify}")
                    changes_made = True
                else:
                    # Try a more flexible search for original_code (e.g. ignoring leading/trailing whitespace on lines)
                    original_code_lines = [line.strip() for line in original_code.strip().split('\n')]
                    content_lines = content.split('\n')
                    content_lines_stripped = [line.strip() for line in content_lines]

                    found_match = False
                    for i in range(len(content_lines_stripped) - len(original_code_lines) + 1):
                        match = True
                        for j in range(len(original_code_lines)):
                            if original_code_lines[j] != content_lines_stripped[i+j]:
                                match = False
                                break
                        if match:
                            # Reconstruct the exact original segment from content_lines
                            exact_original_from_content = '\n'.join(content_lines[i : i + len(original_code_lines)])
                            # Replace this exact segment
                            new_content = content.replace(exact_original_from_content, optimized_code, 1)
                            with open(full_path_to_modify, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                            logger.info(f"Applied optimization (flexible match) to: {full_path_to_modify} at line approx {i+1}")
                            changes_made = True
                            found_match = True
                            break
                    
                    if not found_match:
                        logger.warning(f"Original code snippet not found in {full_path_to_modify}. Optimization skipped for this part.")
                        logger.debug(f"Original code expected:\n{original_code}")

            except Exception as e:
                logger.error(f"Error applying optimization to {full_path_to_modify}: {str(e)}")
                # self.set_error(...) # Optionally set agent-level error, but usually log and continue with other variants/files
        else:
            logger.warning(f"Malformed optimization variant data: {opt}. Missing required keys.")

        # if not self.error_message: self.error_message = error_state
        # self._is_ready = ready_state
                    
        return changes_made

# Example usage (optional, for testing the class)
# This block should be at the top-level, not inside the class.
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="ProfilingAgent: C++ Performance Profiling and AI-driven Optimization Tool.")
    parser.add_argument(
        "--initial_source_dir", type=str, 
        default="data/sources", # Set default value
        help="Path to the original C++ source code directory. Defaults to 'data/sources'."
    )
    parser.add_argument(
        "--main_source_file", type=str, required=True,
        help="Name of the main C++ file to compile (relative to initial_source_dir)."
    )
    parser.add_argument(
        "--binary_args", nargs='*', default=None,
        help="Optional arguments to pass to the binary during profiling."
    )
    parser.add_argument(
        "--max_iterations", type=int, default=2,
        help="Maximum optimization iterations to attempt."
    )
    parser.add_argument(
        "--openai_api_key", type=str, default=None,
        help="OpenAI API key. If not provided, tries to use OPENAI_API_KEY environment variable."
    )
    parser.add_argument(
        "--openai_model", type=str, default="gpt-3.5-turbo", # Or your preferred default
        help="OpenAI model to use (e.g., gpt-4, gpt-3.5-turbo)."
    )
    parser.add_argument(
        "--output_prefix", type=str, default="optimized_code",
        help="Prefix for output directories created under data/sources/ for optimized versions."
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging."
    )

    cli_args = parser.parse_args()

    if cli_args.debug:
        logging.getLogger().setLevel(logging.DEBUG) # Set root logger to DEBUG

    logger.info("Starting ProfilingAgent from command line...")
    
    # Create and setup agent
    agent = ProfilingAgent(openai_model=cli_args.openai_model)
    setup_ok = agent.setup(openai_api_key=cli_args.openai_api_key)

    if not setup_ok:
        logger.error(f"Agent setup failed: {agent.error_message}")
        sys.exit(1)
    
    logger.info("Agent setup successful.")

    # Prepare a dummy C++ file if the specified one doesn't exist in the target dir
    # This is more for robust CLI testing; in a real scenario, the file should exist.
    full_initial_source_dir = os.path.abspath(cli_args.initial_source_dir)
    main_file_path = os.path.join(full_initial_source_dir, cli_args.main_source_file)

    os.makedirs(full_initial_source_dir, exist_ok=True) # Ensure dir exists

    if not os.path.exists(main_file_path):
        logger.warning(f"Main source file {main_file_path} not found. Creating a dummy 'sample.cpp'.")
        cli_args.main_source_file = "sample.cpp" # Ensure we use this name if we create it
        main_file_path = os.path.join(full_initial_source_dir, cli_args.main_source_file)
        with open(main_file_path, "w") as f:
            f.write("""#include <iostream>
#include <vector>
#include <chrono>
#include <numeric> // For std::iota

// A simple function that can be a performance hotspot
void intensive_task_cli_agent() {
    std::vector<long long> v;
    // Make it smaller for quicker CLI tests if needed, adjust for real profiling
    const long long count = 10000000LL; // Reduced from 20M for faster CLI test example
    v.reserve(count); 
    for (long long i = 0; i < count; ++i) {
        v.push_back(i * i + i); 
    }
    long long sum = 0;
    for(long long val : v) {
        if (val % 100 == 0) sum += (val / 100);
    }
    if (sum == 0) std::cout << "Sum was zero!\n";
}

int main(int argc, char** argv) {
    auto start_time = std::chrono::high_resolution_clock::now();
    intensive_task_cli_agent();
    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed_ms = end_time - start_time;
    std::cout << "Task from ProfilingAgent CLI test took " << elapsed_ms.count() << " ms.\n";
    if (argc > 1) {
        std::cout << "Received arg: " << argv[1] << std::endl;
    }
    return 0;
}
""")
            logger.info(f"Created dummy C++ file: {main_file_path}")
    
    logger.info(f"Attempting to optimize '{cli_args.main_source_file}' in '{full_initial_source_dir}'...")
    
    optimization_results = agent.optimize_binary(
        initial_source_dir=full_initial_source_dir,
        main_source_file=cli_args.main_source_file,
        output_dir_name_prefix=cli_args.output_prefix,
        args=cli_args.binary_args,
        max_iterations=cli_args.max_iterations
    )

    logger.info("\n--- ProfilingAgent Optimization Results ---")
    # Pretty print the JSON results
    print(json.dumps(optimization_results, indent=2))

    if optimization_results.get("success"):
        logger.info("Optimization process completed successfully.")
        if optimization_results.get("final_binary_path"):
            logger.info(f"Final optimized binary at: {optimization_results['final_binary_path']}")
            logger.info(f"Corresponding sources at: {optimization_results['final_optimized_source_dir']}")
        else:
            logger.info("Optimization process ran, but no improved binary was produced/selected.")
    else:
        logger.error(f"Optimization process failed or did not complete successfully. Error: {optimization_results.get('error')}")

    # The TemporaryDirectory agent._temp_dir_obj will be cleaned up automatically when agent goes out of scope.
    logger.info("ProfilingAgent CLI execution finished.")