#!/usr/bin/env python3
# See LICENSE for details

import os
import sys
import time
import glob       # To find source files
import re         # For parsing perf report
from core.step import Step

# --- Import Actual Tool Wrappers ---
try:
    from tool.compile.cpp_compiler import CppCompiler
    CPP_COMPILER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import CppCompiler from tool.compile.cpp_compiler: {e}")
    CPP_COMPILER_AVAILABLE = False
    class CppCompiler: # Minimal placeholder to avoid crashing setup
        PRESET_FLAGS = {"debug_opt": ["-g", "-O3"], "opt_only": ["-O3"], "debug_only": ["-g", "-O0"]}
        def __init__(self, *args, **kwargs): self._error = "CppCompiler tool not found"; print(f"WARN: {self._error}")
        def setup(self, *args, **kwargs): print(f"WARN: {self._error}"); return False
        def compile(self, *args, **kwargs): print(f"WARN: {self._error}"); return False, "", self._error
        def get_error(self): return self._error

try:
    from tool.perf.perf_tool import PerfTool
    PERF_TOOL_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import PerfTool from tool.perf.perf_tool: {e}")
    PERF_TOOL_AVAILABLE = False
    class PerfTool: # Minimal placeholder
        def __init__(self, *args, **kwargs): self._error = "PerfTool tool not found"; print(f"WARN: {self._error}")
        def setup(self, *args, **kwargs): print(f"WARN: {self._error}"); return False
        def record(self, *args, **kwargs): print(f"WARN: {self._error}"); return False, "", self._error
        def get_error(self): return self._error
        def is_ready(self): return False
# --- End Tool Imports ---

def extract_function_snippet(function_name: str, file_content: str, file_name_for_header: str, overhead: float) -> str | None:
    # Regex to find function definition. This is a heuristic and might need refinement.
    # It looks for common patterns of function signatures.
    # It tries to match: return_type (optional), function_name, (arguments), optional 'const', opening brace '{'
    # Note: This regex is complex and might not cover all C++ syntax edge cases (e.g. templates, macros, complex return types)
    # We escape the function_name in case it contains special regex characters (unlikely for simple names, but good practice)
    pattern_str = r"(?:[\w\s*&:<>,~\[\]]+\s+)?(?:[\w:]+::)*" + re.escape(function_name) + r"\s*\([^)]*\)\s*(const)?\s*(noexcept)?\s*\{"
    
    try:
        signature_match = re.search(pattern_str, file_content, re.MULTILINE)
    except re.error as e:
        print(f"Regex error for function {function_name} in {file_name_for_header}: {e}")
        return None # Skip this function if regex fails

    if not signature_match:
        # Try a simpler pattern if the function_name might be part of a larger symbol (e.g. mangled names)
        # This is less precise about finding the *start* of a C++ function.
        pattern_str_simple = r"\b" + re.escape(function_name) + r"\b"
        try:
            simple_match_iter = re.finditer(pattern_str_simple, file_content, re.MULTILINE)
            for simple_match in simple_match_iter:
                # Check if this match is followed by an opening brace on the same or next few lines
                # This is a heuristic to see if it's part of a function definition
                search_region_start = simple_match.end()
                search_region_end = min(len(file_content), search_region_start + 200) # Search few lines down for '{'
                region_after_match = file_content[search_region_start:search_region_end]
                brace_match = re.search(r"\{", region_after_match)
                if brace_match:
                    # Found a plausible function start, now need to find the *actual* signature start line
                    # Go upwards from simple_match.start() to find the line that likely contains the return type / start of signature
                    start_pos = simple_match.start()
                    line_start_pos = file_content.rfind('\\n', 0, start_pos) + 1
                    
                    # Heuristic: Assume the function signature starts within a few lines above the name match
                    # This is tricky. Let's try to find the opening brace related to this.
                    # The initial signature_match failed, so this path is more of a fallback.
                    # For now, if signature_match fails, we report not found.
                    # A more advanced approach would be needed here.
                    pass # Fall through, will return None if signature_match was None
        except re.error: # Regex error on fallback
            pass # Fall through

    if not signature_match:
        return None

    start_index = signature_match.start()
    
    # Find the line containing the start_index to include the full signature line
    func_start_line_pos = file_content.rfind('\\n', 0, start_index) + 1
    
    # Find the matching closing brace
    open_braces = 0
    current_pos = signature_match.end() # Start searching for braces right after the matched signature's opening brace
    
    # First, ensure we are past the initial opening brace from the signature
    if file_content[current_pos -1] == '{':
        open_braces = 1
    else: # signature regex might not have ended exactly on '{', search for it
        temp_pos = file_content.find('{', signature_match.start())
        if temp_pos != -1:
            current_pos = temp_pos + 1
            open_braces = 1
        else:
            return None # No opening brace found after signature match

    end_index = -1
    while current_pos < len(file_content):
        char = file_content[current_pos]
        if char == '{':
            open_braces += 1
        elif char == '}':
            open_braces -= 1
            if open_braces == 0:
                end_index = current_pos + 1
                break
        current_pos += 1

    if end_index == -1:
        return None # Matching brace not found

    snippet = file_content[func_start_line_pos:end_index]
    header = f"// --- Hotspot: {function_name} (from {file_name_for_header}, Overhead: {overhead:.2f}%) ---\\n"
    return header + snippet.strip() + "\\n\\n"


def filter_perf_report(report_content: str, threshold: float = 50.0) -> str:
    lines = report_content.split('\n')
    filtered_lines = []
    
    overhead_regex = re.compile(r"^\s*(\d+\.\d+)%\s+.*")
    
    current_block = []
    current_block_significant = False
    
    for line in lines:
        if line.startswith("#"):
            if current_block:
                if current_block_significant:
                    filtered_lines.extend(current_block)
                current_block = [] 
                current_block_significant = False 
            filtered_lines.append(line)
            continue

        match = overhead_regex.match(line)
        if match:
            if current_block:
                if current_block_significant:
                    filtered_lines.extend(current_block)
            
            current_block = [line] 
            overhead = float(match.group(1))
            if overhead > threshold:
                current_block_significant = True
            else:
                current_block_significant = False
        else:
            if current_block:
                current_block.append(line)

    if current_block and current_block_significant:
        filtered_lines.extend(current_block)
        
    return '\n'.join(filtered_lines)


class Profiler(Step):
    """
    Compiles C++ source files, runs perf record/report, and prepares output for Analyzer.

    Takes C++ source files from a directory (if no pre-compiled executable is provided), 
    compiles them using multiple optimization presets (via CppCompiler tool), 
    runs 'perf record' on each resulting executable (or a provided one via PerfTool), 
    generates a 'perf report --stdio' for each, selects the report from a preferred preset.
    The perf report output is filtered to include only entries with overhead > 50%.

    Reads from (input YAML):
      - source_dir: str (Path to the directory containing .cpp, .hpp, .h source files. Used for compilation if 'executable' is not provided. Still required even if 'executable' is provided, for context, though not directly output by this agent.)
      - perf_record_args (optional): list[str] (Base arguments for 'perf record')
      - target_args (optional): list[str] (Arguments for the compiled executable)
      - base_executable_name (optional): str (Base name for executables, defaults to 'a.out')
      - base_perf_data_name (optional): str (Base name for perf data, defaults to 'perf')
      - compile_output_dir (optional): str (Directory for executables, defaults './data/compile')
      - perf_output_dir (optional): str (Directory for perf.data files, defaults './data/perf')
      - preferred_preset (optional): str (Preset to prioritize for output, defaults 'opt_only')
      - executable (optional): str (Path to a pre-compiled executable. If provided, compilation is skipped. `source_dir` is still required for context but its content is not output by this agent.)

    Emits (output YAML for Analyzer):
      - perf_command: str (The specific perf record command used for the selected report)
      - perf_report_output: str (The textual output from perf report for the selected run, filtered to entries with >50% overhead)
      - profiler_error (optional): str (Error message if profiling failed critically)
      - profiling_details (optional): dict (Detailed results for all presets or direct run, for debugging)
    """
    def setup(self):
        super().setup() 

        self.default_perf_record_args = ["-g", "-F", "99", "--call-graph", "dwarf"] 
        self.default_preferred_preset = 'opt_only'
        
        if not CPP_COMPILER_AVAILABLE:
            raise RuntimeError("CppCompiler tool not found, cannot proceed.")
        if not PERF_TOOL_AVAILABLE:
            raise RuntimeError("PerfTool tool not found, cannot proceed.")

        self.compiler = CppCompiler() 
        self.perf_tool = PerfTool()
        self.setup_called = True
        print("Profiler setup complete.")

    def run(self, data):
        output_data = {
            'perf_command': '',
            'perf_report_output': '',
            'profiler_error': None,
            'profiling_details': {} 
        }

        source_dir = data.get('source_dir')
        executable_path_input = data.get('executable') 

        if not source_dir or not os.path.isdir(source_dir):
            # If an executable is provided, source_dir might be less critical for THIS agent's core task,
            # but downstream tools might need it or the original design implies it should exist.
            # For now, keeping this check. If an executable is given, an empty or non-existent
            # source_dir might be okay if the Optimizer pipe ensures source_code is injected later.
            # However, for compilation, it IS critical.
            if not executable_path_input: # Critical if we need to compile
                 output_data['profiler_error'] = f"Error: 'source_dir' ({source_dir}) not found or is not a directory, and no pre-compiled 'executable' was provided."
                 return output_data
            else:
                 # If executable is provided, a missing source_dir is not immediately fatal for the Profiler's execution,
                 # as it won't attempt to compile. It might be an issue for later stages (Analyzer, Replicator)
                 # if they expect the Profiler's input YAML to always point to a valid source_dir from which
                 # they themselves would fetch the code.
                 # For now, let's just print a warning if an executable is given but source_dir is bad.
                 print(f"Warning: 'source_dir' ({source_dir}) not found or is not a directory. Proceeding with provided 'executable', but this might affect later pipeline stages.")


        if not executable_path_input:
            if not source_dir or not os.path.isdir(source_dir): # Re-check as it's critical now
                output_data['profiler_error'] = f"Error: 'source_dir' ({source_dir}) not found or is not a directory. This is required for compilation when no 'executable' is provided."
                return output_data

            source_files_paths = sorted(glob.glob(os.path.join(source_dir, '*.cpp')))
            source_files_paths.extend(sorted(glob.glob(os.path.join(source_dir, '*.hpp'))))
            source_files_paths.extend(sorted(glob.glob(os.path.join(source_dir, '*.h'))))
            source_files_paths = sorted(list(set(source_files_paths)))

            if not source_files_paths:
                output_data['profiler_error'] = f"Error: No *.cpp, *.hpp, or *.h files found in source_dir ({source_dir}) for compilation."
                return output_data
            print(f"Found {len(source_files_paths)} source files in {source_dir} for potential compilation.")
        else:
            source_files_paths = [] # Ensure it's defined if executable is provided
            print(f"Skipping source file discovery as an executable is provided: {executable_path_input}")


        base_perf_record_args = data.get('perf_record_args', self.default_perf_record_args)
        target_args = data.get('target_args', [])
        base_perf_data_name = data.get('base_perf_data_name', 'perf')
        perf_output_dir = os.path.abspath(data.get('perf_output_dir', './data/perf'))
        os.makedirs(perf_output_dir, exist_ok=True)

        final_perf_report_text = ""
        final_perf_command = ""

        if executable_path_input:
            print(f"--- Processing provided executable: {executable_path_input} ---")
            if not os.path.isfile(executable_path_input) or not os.access(executable_path_input, os.X_OK):
                output_data['profiler_error'] = f"Error: Provided 'executable' ({executable_path_input}) is not a file or is not executable."
                return output_data
            
            direct_run_result = {
                'status': 'pending',
                'executable_path': executable_path_input,
                'perf_record': {'command': '', 'data_path': '', 'stderr': '', 'error': ''},
                'perf_report': {'stdout': '', 'stderr': '', 'error': ''}
            }
            output_data['profiling_details']['direct_executable_run'] = direct_run_result

            perf_data_name = f"{base_perf_data_name}_direct.data"
            perf_data_path = os.path.join(perf_output_dir, perf_data_name)
            direct_run_result['perf_record']['data_path'] = perf_data_path

            perf_setup_ok = self.perf_tool.setup(target_executable=executable_path_input, target_args=target_args, perf_data_file=perf_data_path)
            if not perf_setup_ok:
                perf_error = self.perf_tool.get_error() if hasattr(self.perf_tool, 'get_error') else "PerfTool setup failed"
                direct_run_result['status'] = 'perf_setup_failed'; direct_run_result['perf_record']['error'] = perf_error
                output_data['profiler_error'] = f"PerfTool setup failed: {perf_error}"
                return output_data

            record_ok, _, rec_stderr = self.perf_tool.record(record_args=base_perf_record_args)
            final_perf_command = f"{self.perf_tool.perf_executable} record {' '.join(base_perf_record_args)} -o {perf_data_path} -- {executable_path_input} {' '.join(target_args)}"
            direct_run_result['perf_record']['command'] = final_perf_command
            direct_run_result['perf_record']['stderr'] = rec_stderr

            if not record_ok:
                direct_run_result['status'] = 'perf_record_failed'; direct_run_result['perf_record']['error'] = rec_stderr
                output_data['profiler_error'] = f"Perf record failed. Stderr: {rec_stderr}"
                return output_data
            print(f"Perf record successful: {perf_data_path}")

            report_ok, report_stdout_raw, report_stderr_from_report = self.perf_tool.report(report_args=["--stdio"])
            direct_run_result['perf_report']['stderr'] = report_stderr_from_report
            direct_run_result['perf_report']['error'] = report_stderr_from_report if not report_ok else ""

            if not report_ok:
                direct_run_result['status'] = 'perf_report_failed'
                error_msg_report = self.perf_tool.get_error() if hasattr(self.perf_tool, 'get_error') and self.perf_tool.get_error() else report_stderr_from_report
                output_data['profiler_error'] = f"Perf report failed. Error: {error_msg_report}"
                return output_data
            else:
                final_perf_report_text = filter_perf_report(report_stdout_raw) # Removed hint
                direct_run_result['perf_report']['stdout'] = final_perf_report_text
                print(f"Perf report (direct exec) processed. Filtered entries with overhead > 50%.")
                direct_run_result['status'] = 'success'
                output_data['perf_command'] = final_perf_command
                output_data['perf_report_output'] = final_perf_report_text
        
        else: # Compile and then profile
            base_executable_name = data.get('base_executable_name', 'a.out')
            compile_output_dir = os.path.abspath(data.get('compile_output_dir', './data/compile'))
            preferred_preset = data.get('preferred_preset', self.default_preferred_preset)
            os.makedirs(compile_output_dir, exist_ok=True)
            
            results_per_preset = {} 
            overall_success = True 
            optimization_presets = getattr(self.compiler, 'PRESET_FLAGS', {})
            if not optimization_presets:
                 output_data['profiler_error'] = "Error: Could not retrieve PRESET_FLAGS from CppCompiler."
                 return output_data

            for preset_name, preset_flags in optimization_presets.items():
                print(f"--- Processing Preset: {preset_name} ---")
                preset_result_detail = {
                    'status': 'pending',
                    'compile': {'command': '', 'executable_path': '', 'stderr': '', 'error': ''},
                    'perf_record': {'command': '', 'data_path': '', 'stderr': '', 'error': ''},
                    'perf_report': {'stdout': '', 'stderr': '', 'error': ''} # No hot_functions key
                }
                results_per_preset[preset_name] = preset_result_detail
                
                executable_name = f"{base_executable_name}_{preset_name}"
                executable_path = os.path.join(compile_output_dir, executable_name)
                preset_result_detail['compile']['executable_path'] = executable_path

                compile_setup_ok = self.compiler.setup(source_files=source_files_paths, output_executable=executable_path, optimization_preset=None, compile_flags=preset_flags)
                if not compile_setup_ok:
                    compile_error = self.compiler.get_error() if hasattr(self.compiler, 'get_error') else "Compiler setup failed"
                    preset_result_detail['status'] = 'compile_setup_failed'; preset_result_detail['compile']['error'] = compile_error; overall_success = False; continue
                
                compile_ok, _, compile_stderr = self.compiler.compile()
                compile_cmd = self.compiler.get_command() if hasattr(self.compiler, 'get_command') else "N/A" 
                preset_result_detail['compile']['command'] = compile_cmd; preset_result_detail['compile']['stderr'] = compile_stderr
                if not compile_ok:
                    preset_result_detail['status'] = 'compile_failed'; preset_result_detail['compile']['error'] = compile_stderr; overall_success = False; continue
                print(f"Compilation successful: {executable_path}")
                
                perf_data_name = f"{base_perf_data_name}_{preset_name}.data"
                perf_data_path = os.path.join(perf_output_dir, perf_data_name)
                preset_result_detail['perf_record']['data_path'] = perf_data_path

                perf_setup_ok = self.perf_tool.setup(target_executable=executable_path, target_args=target_args, perf_data_file=perf_data_path)
                if not perf_setup_ok:
                    perf_error = self.perf_tool.get_error() if hasattr(self.perf_tool, 'get_error') else "PerfTool setup failed"
                    preset_result_detail['status'] = 'perf_setup_failed'; preset_result_detail['perf_record']['error'] = perf_error; overall_success = False; continue

                record_ok, _, rec_stderr = self.perf_tool.record(record_args=base_perf_record_args)
                current_perf_command = f"{self.perf_tool.perf_executable} record {' '.join(base_perf_record_args)} -o {perf_data_path} -- {executable_path} {' '.join(target_args)}"
                preset_result_detail['perf_record']['command'] = current_perf_command
                preset_result_detail['perf_record']['stderr'] = rec_stderr
                if not record_ok:
                    preset_result_detail['status'] = 'perf_record_failed'; preset_result_detail['perf_record']['error'] = rec_stderr; overall_success = False; continue
                print(f"Perf record successful: {perf_data_path}")
                
                report_ok, report_stdout_raw, report_stderr_from_report = self.perf_tool.report(report_args=["--stdio"])
                preset_result_detail['perf_report']['stderr'] = report_stderr_from_report
                preset_result_detail['perf_report']['error'] = report_stderr_from_report if not report_ok else ""

                if not report_ok:
                    preset_result_detail['status'] = 'perf_report_failed'
                    error_msg_report = self.perf_tool.get_error() if hasattr(self.perf_tool, 'get_error') and self.perf_tool.get_error() else report_stderr_from_report # Store error from report
                    preset_result_detail['perf_report']['error'] = error_msg_report # Ensure it is stored
                    overall_success = False; continue # Continue to allow other presets to run
                else:
                    filtered_text = filter_perf_report(report_stdout_raw) # Removed hint
                    preset_result_detail['perf_report']['stdout'] = filtered_text
                    print(f"Perf report (preset {preset_name}) processed. Filtered entries with overhead > 50%.")
                preset_result_detail['status'] = 'success'

            output_data['profiling_details'] = results_per_preset
            selected_preset_result = None
            if preferred_preset in results_per_preset and results_per_preset[preferred_preset]['status'] == 'success':
                selected_preset_result = results_per_preset[preferred_preset]
                print(f"Selected preferred preset '{preferred_preset}' for output.")
            else:
                fallback_order = ['opt_only', 'debug_opt', 'debug_only'] 
                for name_fallback in fallback_order:
                     if name_fallback in results_per_preset and results_per_preset[name_fallback]['status'] == 'success':
                         selected_preset_result = results_per_preset[name_fallback]
                         print(f"Selected fallback preset '{name_fallback}' for output.")
                         break
            
            if selected_preset_result:
                final_perf_command = selected_preset_result['perf_record']['command']
                final_perf_report_text = selected_preset_result['perf_report']['stdout']
                output_data['perf_command'] = final_perf_command
                output_data['perf_report_output'] = final_perf_report_text
            else:
                if not output_data.get('profiler_error'): 
                    output_data['profiler_error'] = "Profiler Error: No preset completed successfully."
                if output_data.get('profiler_error'): print(f"ERROR: {output_data['profiler_error']}")
        
        return output_data


if __name__ == '__main__':  # pragma: no cover
    profiler_step = Profiler()
    try:
        profiler_step.parse_arguments()
        setup_start_time = time.time()
        profiler_step.setup() 
        setup_end_time = time.time()
        print(f"TIME: setup duration: {(setup_end_time-setup_start_time):.4f} seconds")
        
        step_start_time = time.time()
        profiler_step.step() 
        step_end_time = time.time()
        print(f"TIME: step duration: {(step_end_time-step_start_time):.4f} seconds")

    except (ValueError, RuntimeError, FileNotFoundError) as e: 
        print(f"ERROR during Profiler execution (Setup/Config/File Error): {e}")
        import traceback
        traceback.print_exc()
    except Exception as e: 
        print(f"ERROR during Profiler execution (Unexpected Error): {e}")
        import traceback
        traceback.print_exc() 