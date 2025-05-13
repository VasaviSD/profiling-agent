#!/usr/bin/env python3
# See LICENSE for details

import os
import sys
import time
import glob       # To find source files
from core.step import Step

# --- Import Actual Tool Wrappers ---
try:
    from tool.compile.cpp_compiler import CppCompiler
    CPP_COMPILER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import CppCompiler from tool.compile.cpp_compiler: {e}")
    CPP_COMPILER_AVAILABLE = False
    class CppCompiler: # Minimal placeholder to avoid crashing setup
        PRESET_FLAGS = {"debug_opt": ["-g", "-O3"], "opt_only": ["-O3"], "debug_only": ["-g"]}
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

class Profiler(Step):
    """
    Compiles C++ source files, runs perf record/report, and prepares output for Analyzer.

    Takes C++ source files from a directory, compiles them using multiple optimization
    presets (via CppCompiler tool), runs 'perf record' on each resulting executable 
    (via PerfTool), generates a 'perf report --stdio' for each, selects the report 
    from a preferred preset, and outputs data structured for the Analyzer agent.

    Reads from (input YAML):
      - source_dir: str (Path to the directory containing .cpp source files)
      - perf_record_args (optional): list[str] (Base arguments for 'perf record')
      - target_args (optional): list[str] (Arguments for the compiled executable)
      - base_executable_name (optional): str (Base name for executables, defaults to 'a.out')
      - base_perf_data_name (optional): str (Base name for perf data, defaults to 'perf')
      - compile_output_dir (optional): str (Directory for executables, defaults './data/compile')
      - perf_output_dir (optional): str (Directory for perf.data files, defaults './data/perf')
      - preferred_preset (optional): str (Preset to prioritize for output, defaults 'opt_only')

    Emits (output YAML for Analyzer):
      - source_code: str (Content of the C++ source files)
      - perf_command: str (The specific perf record command used for the selected report)
      - perf_report_output: str (The textual output from perf report for the selected run)
      - profiler_error (optional): str (Error message if profiling failed critically)
      - profiling_details (optional): dict (Detailed results for all presets, for debugging)
    """
    def setup(self):
        super().setup() 

        # Default configuration
        self.default_perf_record_args = ["-g", "-F", "99", "--call-graph", "dwarf"]
        self.default_preferred_preset = 'opt_only'
        
        # Check tool availability early
        if not CPP_COMPILER_AVAILABLE:
            raise RuntimeError("CppCompiler tool not found, cannot proceed.")
        if not PERF_TOOL_AVAILABLE:
            raise RuntimeError("PerfTool tool not found, cannot proceed.")

        # Instantiate tools
        self.compiler = CppCompiler()
        self.perf_tool = PerfTool() # PerfTool itself knows 'perf' executable path
        
        self.setup_called = True
        print("Profiler setup complete.")

    def run(self, data):
        output_data = {
            'source_code': '',
            'perf_command': '',
            'perf_report_output': '',
            'profiler_error': None,
            'profiling_details': {} # Store detailed results per preset
        }

        source_dir = data.get('source_dir')
        if not source_dir or not os.path.isdir(source_dir):
            output_data['profiler_error'] = f"Error: 'source_dir' ({source_dir}) not found or is not a directory."
            return output_data

        # Read C++ source code content
        source_files = sorted(glob.glob(os.path.join(source_dir, '*.cpp'))) # Sort for consistency
        if not source_files:
            output_data['profiler_error'] = f"Error: No *.cpp files found in source_dir: {source_dir}"
            return output_data
        
        source_code_content = ""
        try:
            for sf in source_files:
                with open(sf, 'r') as f:
                    source_code_content += f"// --- Source: {os.path.basename(sf)} ---"
                    source_code_content += f.read()
                    source_code_content += "\n\n"
            output_data['source_code'] = source_code_content.strip()
            if not output_data['source_code']:
                 print("Warning: Source directory contains *.cpp files, but reading them resulted in empty content.")
        except Exception as e:
            output_data['profiler_error'] = f"Error reading source files from {source_dir}: {e}"
            return output_data
        print(f"Read source code from: {source_files}")


        # Get configuration with defaults
        base_perf_record_args = data.get('perf_record_args', self.default_perf_record_args)
        target_args = data.get('target_args', [])
        base_executable_name = data.get('base_executable_name', 'a.out')
        base_perf_data_name = data.get('base_perf_data_name', 'perf')
        compile_output_dir = os.path.abspath(data.get('compile_output_dir', './data/compile'))
        perf_output_dir = os.path.abspath(data.get('perf_output_dir', './data/perf'))
        preferred_preset = data.get('preferred_preset', self.default_preferred_preset)


        os.makedirs(compile_output_dir, exist_ok=True)
        os.makedirs(perf_output_dir, exist_ok=True)
        
        results = {} # Store detailed results for each preset
        overall_success = True # Tracks if *any* preset fully succeeded

        optimization_presets = getattr(self.compiler, 'PRESET_FLAGS', {})
        if not optimization_presets:
             output_data['profiler_error'] = "Error: Could not retrieve PRESET_FLAGS from CppCompiler."
             return output_data

        for preset_name, preset_flags in optimization_presets.items():
            print(f"--- Processing Preset: {preset_name} ---")
            preset_result = {
                'status': 'pending',
                'compile': {'command': '', 'executable_path': '', 'stderr': '', 'error': ''},
                'perf_record': {'command': '', 'data_path': '', 'stderr': '', 'error': ''},
                'perf_report': {'stdout': '', 'stderr': '', 'error': ''}
            }
            results[preset_name] = preset_result # Store early for tracking
            
            # 1. Compile
            executable_name = f"{base_executable_name}_{preset_name}"
            executable_path = os.path.join(compile_output_dir, executable_name)
            preset_result['compile']['executable_path'] = executable_path

            compile_setup_ok = self.compiler.setup(
                source_files=source_files,
                output_executable=executable_path,
                optimization_preset=None,
                compile_flags=preset_flags
            )
            
            if not compile_setup_ok:
                compile_error = self.compiler.get_error() if hasattr(self.compiler, 'get_error') else "Compiler setup failed"
                preset_result['status'] = 'compile_setup_failed'
                preset_result['compile']['error'] = compile_error
                print(f"ERROR: Compile setup failed for preset {preset_name}: {compile_error}")
                overall_success = False # Mark this preset as failed
                continue 

            compile_ok, compile_stdout, compile_stderr = self.compiler.compile()
            compile_cmd = self.compiler.get_command() if hasattr(self.compiler, 'get_command') else "N/A"
            preset_result['compile']['command'] = compile_cmd
            preset_result['compile']['stderr'] = compile_stderr

            if not compile_ok:
                preset_result['status'] = 'compile_failed'
                preset_result['compile']['error'] = compile_stderr
                print(f"ERROR: Compilation failed for preset {preset_name}. Stderr:{compile_stderr}")
                overall_success = False
                continue
                
            print(f"Compilation successful: {executable_path}")
            
            # 2. Perf Record
            perf_data_name = f"{base_perf_data_name}_{preset_name}.data"
            perf_data_path = os.path.join(perf_output_dir, perf_data_name)
            preset_result['perf_record']['data_path'] = perf_data_path

            # Construct full perf command line for logging/output
            # PerfTool's record method now handles -o internally based on its setup,
            # so we pass base_perf_record_args directly. PerfTool.setup configures perf_data_file.
            final_perf_record_args = list(base_perf_record_args) # Copy, can be modified if needed by PerfTool assumptions

            # PerfTool's setup needs the perf_data_file to be configured for the instance
            # The record method will then use self.perf_data_file
            perf_setup_ok = self.perf_tool.setup(
                target_executable=executable_path,
                target_args=target_args,
                perf_data_file=perf_data_path # This tells PerfTool instance where to expect/write data
            )
            
            if not perf_setup_ok:
                perf_error = self.perf_tool.get_error() if hasattr(self.perf_tool, 'get_error') else "PerfTool setup failed"
                preset_result['status'] = 'perf_setup_failed'
                preset_result['perf_record']['error'] = perf_error
                print(f"ERROR: PerfTool setup failed for preset {preset_name}: {perf_error}")
                overall_success = False
                continue

            # record_args in perf_tool.record are supplemental to what's configured in setup (like -o)
            record_ok, rec_stdout, rec_stderr = self.perf_tool.record(record_args=final_perf_record_args)
            
            # For logging the command, we can approximate or try to get it from the tool if available
            # For now, let's construct a representative command. PerfTool itself handles -o.
            perf_cmd_logged = f"{self.perf_tool.perf_executable} record {' '.join(final_perf_record_args)} -o {perf_data_path} -- {executable_path} {' '.join(target_args)}"
            preset_result['perf_record']['command'] = perf_cmd_logged
            preset_result['perf_record']['stderr'] = rec_stderr

            if not record_ok:
                preset_result['status'] = 'perf_record_failed'
                preset_result['perf_record']['error'] = rec_stderr
                print(f"ERROR: Perf record failed for preset {preset_name}. Stderr:{rec_stderr}")
                overall_success = False
                continue

            print(f"Perf record successful: {perf_data_path}")
            
            # 3. Perf Report using PerfTool.report()
            # PerfTool.report() uses the self.perf_data_file set during its setup
            report_ok, report_stdout, report_stderr_from_report = self.perf_tool.report(report_args=["--stdio"]) # Request standard text output
            
            preset_result['perf_report']['stderr'] = report_stderr_from_report
            preset_result['perf_report']['error'] = report_stderr_from_report if not report_ok else ""

            if not report_ok:
                preset_result['status'] = 'perf_report_failed'
                # Use the actual error from PerfTool.report's stderr or its internal get_error()
                error_msg_report = self.perf_tool.get_error() if hasattr(self.perf_tool, 'get_error') and self.perf_tool.get_error() else report_stderr_from_report
                print(f"ERROR: Perf report failed for preset {preset_name}. Error: {error_msg_report}")
                overall_success = False
                # Still continue, maybe another preset worked fully
                continue 
            else:
                # Truncate the report output to top ~30% of lines
                report_lines = report_stdout.strip().split('\n')
                num_lines_total = len(report_lines)
                num_lines_to_keep = max(10, int(num_lines_total * 0.30)) # Keep at least 10 lines, or 30%
                truncated_report = '\n'.join(report_lines[:num_lines_to_keep])
                preset_result['perf_report']['stdout'] = truncated_report
                print(f"Perf report generated successfully for preset {preset_name}. Stored top {num_lines_to_keep}/{num_lines_total} lines.")

            preset_result['status'] = 'success' # Mark preset as fully successful


        output_data['profiling_details'] = results

        # Select the result to output based on preference and success
        selected_preset_result = None
        selected_preset_name = None

        # Try preferred preset first
        if preferred_preset in results and results[preferred_preset]['status'] == 'success':
            selected_preset_name = preferred_preset
            selected_preset_result = results[preferred_preset]
            print(f"Selected preferred preset '{preferred_preset}' for output.")
        else:
            # Fallback: Find the first successful preset (maybe iterate in a defined order?)
            fallback_order = ['opt_only', 'debug_opt', 'debug_only'] # Example priority
            for name in fallback_order:
                 if name in results and results[name]['status'] == 'success':
                     selected_preset_name = name
                     selected_preset_result = results[name]
                     print(f"Selected fallback preset '{name}' for output as preferred preset '{preferred_preset}' failed or was unavailable.")
                     break
        
        if selected_preset_result:
            output_data['perf_command'] = selected_preset_result['perf_record']['command']
            output_data['perf_report_output'] = selected_preset_result['perf_report']['stdout']
        else:
            output_data['profiler_error'] = "Profiler Error: No preset completed successfully (compile, record, and report)."
            print(f"ERROR: {output_data['profiler_error']}")
            # Keep source code in output even if profiling failed
        
        # Clean up intermediate files? Maybe not, keep them in data/ for debugging
        # print("Profiler run finished.")
        return output_data


if __name__ == '__main__':  # pragma: no cover
    # Use the Step class's standard argument parsing
    profiler_step = Profiler()
    try:
        profiler_step.parse_arguments()
        setup_start_time = time.time()
        profiler_step.setup() # Call setup after parse_arguments
        setup_end_time = time.time()
        print(f"TIME: setup duration: {(setup_end_time-setup_start_time):.4f} seconds")
        
        step_start_time = time.time()
        # step() method should internally call run(self.input_data) and write the result to self.output_file
        profiler_step.step() 
        step_end_time = time.time()
        print(f"TIME: step duration: {(step_end_time-step_start_time):.4f} seconds")


    except (ValueError, RuntimeError, FileNotFoundError) as e: # Catch setup/config/file errors
        print(f"ERROR during Profiler execution (Setup/Config/File Error): {e}")
        import traceback
        traceback.print_exc()
    except Exception as e: # Catch unexpected errors during run/step
        print(f"ERROR during Profiler execution (Unexpected Error): {e}")
        import traceback
        traceback.print_exc() 