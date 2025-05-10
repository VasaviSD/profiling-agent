import logging
import os
from typing import List, Optional, Tuple
import argparse # Added for command-line arguments

from tool.tool import Tool

logger = logging.getLogger(__name__)

# Try to import CppCompiler for on-the-fly compilation in main
try:
    from tool.compile.cpp_compiler import CppCompiler
    CPP_COMPILER_AVAILABLE = True
except ImportError:
    CPP_COMPILER_AVAILABLE = False
    # We won't log an error here yet, only if CppCompiler is actually needed by CLI args

class PerfTool(Tool):
    """
    Tool to interact with the Linux 'perf' command-line utility for performance profiling.
    """

    def __init__(self, perf_executable: str = 'perf'):
        """
        Initialize the PerfTool.

        Args:
            perf_executable: The 'perf' command. Defaults to 'perf'.
        """
        super().__init__()
        self.perf_executable = perf_executable
        self.target_executable: Optional[str] = None
        self.target_args: List[str] = []
        self.perf_data_file: str = 'perf.data' # Default perf data file name

    def setup(
        self,
        target_executable: str,
        target_args: Optional[List[str]] = None,
        perf_path: Optional[str] = None, # Specific path to perf if not in system PATH
        perf_data_file: Optional[str] = None,
    ) -> bool:
        """
        Setup the PerfTool with the target executable and arguments.

        Args:
            target_executable: Path to the executable to be profiled.
            target_args: Optional list of arguments to pass to the target executable.
            perf_path: Optional specific path to the 'perf' executable.
            perf_data_file: Optional name for the perf data output file (e.g., 'my_perf.data').

        Returns:
            True if setup is successful (perf and target executable found), False otherwise.
        """
        self._is_ready = False
        perf_to_check = os.path.join(perf_path, self.perf_executable) if perf_path else self.perf_executable

        if not self.check_executable(perf_to_check):
            logger.error(f"Perf executable '{perf_to_check}' not found. Error: {self.get_error()}")
            return False
        if perf_path: # If a specific path was provided and checked
            self.perf_executable = perf_to_check

        if not os.path.exists(target_executable) or not os.access(target_executable, os.X_OK):
            self.set_error(f"Target executable '{target_executable}' not found or not executable.")
            logger.error(self.get_error())
            return False

        self.target_executable = target_executable
        self.target_args = target_args if target_args else []
        if perf_data_file:
            self.perf_data_file = perf_data_file

        self._is_ready = True
        logger.info(
            f"PerfTool setup successful for target: {self.target_executable} with args: {self.target_args} using {self.perf_executable}"
        )
        return True

    def record(self, record_args: Optional[List[str]] = None) -> Tuple[bool, str, str]:
        """
        Run 'perf record' on the target executable.

        Args:
            record_args: Optional list of arguments for 'perf record' (e.g., ["-g", "-F", "99"]).
                         Defaults to ["-g"] for call graph information.

        Returns:
            A tuple (success: bool, stdout: str, stderr: str).
            Success is True if 'perf record' returns exit code 0.
        """
        if not self.is_ready() or not self.target_executable:
            logger.error("PerfTool not ready or target executable not set. Call setup() first.")
            return False, "", self.get_error() if self.get_error() else "Tool not ready."

        # Ensure old perf.data is removed if it exists, as perf record might append or error out.
        if os.path.exists(self.perf_data_file):
            try:
                os.remove(self.perf_data_file)
                logger.info(f"Removed existing perf data file: {self.perf_data_file}")
            except OSError as e:
                self.set_error(f"Could not remove existing {self.perf_data_file}: {e}")
                logger.error(self.get_error())
                return False, "", self.get_error()

        effective_record_args = record_args if record_args is not None else ["-g"]

        cmd = [
            self.perf_executable, \
            'record',
            *effective_record_args, \
            '-o', self.perf_data_file, # Specify output file
            '--', \
            self.target_executable, \
            *self.target_args
        ]

        logger.info(f"Executing perf record command: {' '.join(cmd)}")
        # Perf record can run for a while, might not produce much stdout/stderr unless there is an error.
        result = self.run_command(cmd, capture_output=True, text=True, timeout=300) # Increased timeout for profiling

        if result is None:
            logger.error(f"Perf record command failed to run. Error: {self.get_error()}")
            return False, "", self.get_error()

        if result.returncode == 0:
            if not os.path.exists(self.perf_data_file):
                self.set_error(f"Perf record ran but {self.perf_data_file} was not created. Stderr: {result.stderr}")
                logger.error(self.get_error())
                return False, result.stdout, result.stderr
            logger.info(f"Perf record successful. Data in {self.perf_data_file}")
            return True, result.stdout, result.stderr
        else:
            self.set_error(f"Perf record failed with return code {result.returncode}.\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}")
            logger.error(f"Perf record failed. RC: {result.returncode}, Stdout: {result.stdout}, Stderr: {result.stderr}")
            return False, result.stdout, result.stderr

    def report(
        self, 
        report_args: Optional[List[str]] = None,
        use_script_mode: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Run 'perf report' or 'perf script' to get readable output from perf.data.

        Args:
            report_args: Optional list of arguments for 'perf report/script' (e.g., ["--stdio"] for report, or specific fields for script).
                         For report, defaults to ["--stdio", "--no-children", "--sort=dso,symbol"] for a standard text report.
                         For script, defaults to an empty list (raw script output).
            use_script_mode: If True, runs 'perf script'. Otherwise, runs 'perf report'.

        Returns:
            A tuple (success: bool, output_data: str, stderr: str).
            output_data contains stdout from the perf command.
        """
        if not self.is_ready():
            logger.error("PerfTool not ready. Call setup() first.")
            return False, "", self.get_error() if self.get_error() else "Tool not ready."

        if not os.path.exists(self.perf_data_file):
            self.set_error(f"Perf data file '{self.perf_data_file}' not found. Run record() first.")
            logger.error(self.get_error())
            return False, "", self.get_error()

        command_type = 'script' if use_script_mode else 'report'
        
        if use_script_mode:
            effective_report_args = report_args if report_args is not None else []
        else: # report mode
            effective_report_args = report_args if report_args is not None else ["--stdio", "--no-children", "--sort=dso,symbol"]

        cmd = [self.perf_executable, command_type, '-i', self.perf_data_file, *effective_report_args]

        logger.info(f"Executing perf {command_type} command: {' '.join(cmd)}")
        result = self.run_command(cmd, capture_output=True, text=True)

        if result is None:
            logger.error(f"Perf {command_type} command failed to run. Error: {self.get_error()}")
            return False, "", self.get_error()

        if result.returncode == 0:
            logger.info(f"Perf {command_type} successful.")
            return True, result.stdout, result.stderr
        else:
            self.set_error(f"Perf {command_type} failed with return code {result.returncode}.\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}")
            logger.error(f"Perf {command_type} failed. RC: {result.returncode}, Stdout: {result.stdout}, Stderr: {result.stderr}")
            return False, result.stdout, result.stderr

    def stat(self, stat_args: Optional[List[str]] = None) -> Tuple[bool, str, str]:
        """
        Run 'perf stat' on the target executable to get event counter statistics.

        Args:
            stat_args: Optional list of arguments for 'perf stat' 
                       (e.g., ["-e", "cycles,instructions,cache-misses", "-r", "3"] for specific events and 3 repeats).
                       Defaults to basic stat if None.

        Returns:
            A tuple (success: bool, stat_output: str, error_output: str).
            stat_output contains stderr from the perf stat command (where it typically prints results).
            error_output contains stdout (which is usually empty for perf stat unless errors occur in specific ways).
        """
        if not self.is_ready() or not self.target_executable:
            logger.error("PerfTool not ready or target executable not set. Call setup() first.")
            return False, "", self.get_error() if self.get_error() else "Tool not ready."

        effective_stat_args = stat_args if stat_args is not None else []

        cmd = [
            self.perf_executable, \
            'stat',
            *effective_stat_args, \
            '--', \
            self.target_executable, \
            *self.target_args
        ]

        logger.info(f"Executing perf stat command: {' '.join(cmd)}")
        # perf stat usually prints its report to stderr.
        result = self.run_command(cmd, capture_output=True, text=True, timeout=300) 

        if result is None:
            logger.error(f"Perf stat command failed to run. Error: {self.get_error()}")
            # Pass stderr as error_output as that is where perf stat would report issues too
            return False, "", self.get_error()

        if result.returncode == 0:
            logger.info(f"Perf stat successful. Output is typically in stderr.")
            # For perf stat, the main output is often on stderr.
            # stdout might contain other messages or be empty.
            return True, result.stderr, result.stdout 
        else:
            # If perf stat itself fails (e.g., invalid event), it might print to both stdout and stderr
            error_message = f"Perf stat failed with return code {result.returncode}.\n"
            if result.stdout:
                error_message += f"Stdout:\n{result.stdout}\n"
            if result.stderr:
                error_message += f"Stderr:\n{result.stderr}"
            self.set_error(error_message)
            logger.error(f"Perf stat failed. RC: {result.returncode}")
            if result.stdout: logger.error(f"Stdout: {result.stdout}")
            if result.stderr: logger.error(f"Stderr: {result.stderr}")
            return False, result.stderr, result.stdout

# Example Usage:
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

    parser = argparse.ArgumentParser(description="Linux 'perf' Tool Wrapper.")
    
    # Arguments for specifying the target application
    parser.add_argument(
        "-t", "--target-executable",
        help="Path to the executable to profile."
    )
    parser.add_argument(
        "-cs", "--compile-source",
        help="C++ source file to compile and then profile. If used, --target-executable is ignored."
    )
    parser.add_argument(
        "--compiler-opt-preset",
        choices=CppCompiler.PRESET_FLAGS.keys() if CPP_COMPILER_AVAILABLE else ["debug_only"],
        default="debug_only",
        help="Optimization preset for on-the-fly compilation (if --compile-source is used). Default: debug_only."
    )
    parser.add_argument(
        "--compiler-flags",
        nargs='*'
        ,default=[],
        help="Additional flags for on-the-fly C++ compilation."
    )
    parser.add_argument(
        "--output-compiled-name",
        default="perf_target_compiled",
        help="Output name for the executable if --compile-source is used. Default: perf_target_compiled."
    )
    parser.add_argument(
        "--target-args",
        nargs='*'
        ,default=[],
        help="Arguments to pass to the target executable."
    )

    # Arguments for controlling PerfTool actions
    parser.add_argument(
        "--run-record", action="store_true", help="Run perf record, report, and script."
    )
    parser.add_argument(
        "--run-stat", action="store_true", help="Run perf stat."
    )
    # If neither --run-record nor --run-stat is specified, default_run_all will be true
    # This allows running script with no args to perform all actions on the dummy app.

    parser.add_argument(
        "--perf-data-file", default="perf.data", help="Output file for perf record data. Default: perf.data"
    )
    parser.add_argument(
        "--record-args", nargs='*'
        ,default=["-g", "-F", "99"], help="Arguments for perf record. Default: -g -F 99"
    )
    parser.add_argument(
        "--report-args", nargs='*'
        ,default=[], help="Arguments for perf report."
    )
    parser.add_argument(
        "--stat-args", nargs='*'
        ,default=[], help="Arguments for perf stat."
    )
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Do not cleanup generated dummy/compiled files after execution."
    )

    args = parser.parse_args()

    # Determine if we should run all actions if no specific one is chosen by the user
    # This is true if a target is specified (or will be compiled/dummied) but no specific action like --run-record or --run-stat
    # and a target (either pre-compiled, to-be-compiled, or dummy) is available.
    should_run_all_actions = not (args.run_record or args.run_stat)

    target_executable_for_perf = args.target_executable
    created_dummy_source = False
    compiled_on_the_fly = False
    dummy_cpp_file_name = "perf_tool_dummy_app.cpp"
    
    # 1. Determine the target executable for perf
    if args.compile_source:
        if not CPP_COMPILER_AVAILABLE:
            logger.error("Error: --compile-source specified, but CppCompiler could not be imported from tool.compile.cpp_compiler.")
            exit(1)
        logger.info(f"Compiling source file: {args.compile_source} -> {args.output_compiled_name}")
        compiler = CppCompiler()
        # Ensure output_compiled_name is an absolute path if it's relative to current dir
        compiled_exe_path = os.path.abspath(args.output_compiled_name)

        setup_ok = compiler.setup(
            source_files=[args.compile_source],
            output_executable=compiled_exe_path, # Use absolute path
            optimization_preset=args.compiler_opt_preset,
            compile_flags=args.compiler_flags
        )
        if not setup_ok:
            logger.error(f"CppCompiler setup failed for {args.compile_source}: {compiler.get_error()}")
            exit(1)
        
        compile_success, _, comp_stderr = compiler.compile()
        if not compile_success:
            logger.error(f"Failed to compile {args.compile_source}. Stderr:\\n{comp_stderr}")
            exit(1)
        target_executable_for_perf = compiled_exe_path # Use absolute path
        compiled_on_the_fly = True
        logger.info(f"Successfully compiled {args.compile_source} to {target_executable_for_perf}")
    elif not args.target_executable:
        # No target specified, and no source to compile, so use internal dummy app
        if not CPP_COMPILER_AVAILABLE:
            logger.error("Error: No target or source specified, and CppCompiler (needed for dummy app) could not be imported.")
            exit(1)
        logger.info("No target or source specified. Using internal dummy C++ app.")
        cpp_content = """
        #include <iostream>
        #include <vector>
        #include <string>
        void intensive_task_cli() {
            volatile int c = 0;
            for (long i = 0; i < 200000000; ++i) { c++; }
        }
        int main() {
            std::cout << "PerfTool CLI Dummy App: Starting intensive task..." << std::endl;
            intensive_task_cli();
            std::cout << "PerfTool CLI Dummy App: Finished intensive task." << std::endl;
            return 0;
        }
        """
        with open(dummy_cpp_file_name, "w") as f:
            f.write(cpp_content)
        created_dummy_source = True
        
        compiler = CppCompiler()
        dummy_exe_name_rel = "perf_tool_dummy_app_compiled" # Relative name for compilation output
        dummy_exe_path_abs = os.path.abspath(dummy_exe_name_rel)

        setup_ok = compiler.setup(
            source_files=[dummy_cpp_file_name],
            output_executable=dummy_exe_path_abs, # Compile to an absolute path
            optimization_preset="debug_only" # Essential for perf
        )
        if not setup_ok:
            logger.error(f"CppCompiler setup failed for dummy app: {compiler.get_error()}")
            if created_dummy_source and not args.no_cleanup: os.remove(dummy_cpp_file_name)
            exit(1)
        compile_success, _, comp_stderr = compiler.compile()
        if not compile_success:
            logger.error(f"Failed to compile dummy app. Stderr:\\n{comp_stderr}")
            if created_dummy_source and not args.no_cleanup: os.remove(dummy_cpp_file_name)
            exit(1)
        target_executable_for_perf = dummy_exe_path_abs # Use absolute path
        compiled_on_the_fly = True # Treat as on-the-fly for cleanup purposes
        logger.info(f"Successfully compiled dummy app to {target_executable_for_perf}")
    elif args.target_executable:
        # User provided a target, make it absolute if it's relative to CWD
        # This helps if PerfTool internals or subprocess calls have a different CWD later
        target_executable_for_perf = os.path.abspath(args.target_executable)
        logger.info(f"Using provided target executable (made absolute): {target_executable_for_perf}")

    if not target_executable_for_perf:
        logger.error("No target executable specified or compilable for perf. Use -t or -cs, or run without these for dummy app.")
        parser.print_help()
        exit(1)

    # 2. Initialize and Setup PerfTool
    perf_tool = PerfTool()
    setup_ok = perf_tool.setup(
        target_executable=target_executable_for_perf,
        target_args=args.target_args,
        perf_data_file=args.perf_data_file
    )

    if not setup_ok:
        logger.error(f"PerfTool setup FAILED: {perf_tool.get_error()}")
        # Potential cleanup for files created if PerfTool setup fails right after compilation
        if compiled_on_the_fly and os.path.exists(target_executable_for_perf) and not args.no_cleanup:
            os.remove(target_executable_for_perf)
        if created_dummy_source and os.path.exists(dummy_cpp_file_name) and not args.no_cleanup:
            os.remove(dummy_cpp_file_name)
        exit(1)

    logger.info(f"PerfTool setup OK for target: {target_executable_for_perf}")

    # 3. Perform perf actions
    if args.run_record or should_run_all_actions:
        logger.info("\n--- Running Perf Record, Report, Script ---")
        record_success, rec_stdout, rec_stderr = perf_tool.record(record_args=args.record_args)
        if record_success:
            logger.info("Perf record SUCCEEDED.")
            if rec_stdout: logger.debug(f"Record stdout:\n{rec_stdout}") # Usually empty
            if rec_stderr: logger.debug(f"Record stderr:\n{rec_stderr}") # Might contain info

            report_success, rep_stdout, rep_stderr = perf_tool.report(report_args=args.report_args)
            if report_success:
                logger.info("Perf report SUCCEEDED. Output:\n" + rep_stdout)
                if rep_stderr: logger.debug(f"Report stderr:\n{rep_stderr}")
            else:
                logger.error(f"Perf report FAILED. Stderr:\n{rep_stderr}")
                if rep_stdout: logger.error(f"Report stdout:\n{rep_stdout}")

            # Script mode (often verbose, consider making it more optional or summarizing)
            script_success, script_stdout, script_stderr = perf_tool.report(use_script_mode=True, report_args=args.report_args) # use same report_args for script if any
            if script_success:
                logger.info("Perf script SUCCEEDED. Output (first 1000 chars):\n" + script_stdout[:1000] + ("..." if len(script_stdout) > 1000 else ""))
                if script_stderr: logger.debug(f"Script stderr:\n{script_stderr}")
            else:
                logger.error(f"Perf script FAILED. Stderr:\n{script_stderr}")
                if script_stdout: logger.error(f"Script stdout:\n{script_stdout}")
        else:
            logger.error(f"Perf record FAILED.")
            if rec_stdout: logger.error(f"Record stdout:\n{rec_stdout}")
            if rec_stderr: logger.error(f"Record stderr:\n{rec_stderr}")

    if args.run_stat or should_run_all_actions:
        logger.info("\n--- Running Perf Stat ---")
        stat_success, stat_stderr_output, stat_stdout_output = perf_tool.stat(stat_args=args.stat_args)
        if stat_success:
            logger.info("Perf stat SUCCEEDED. Output (from stderr):\n" + stat_stderr_output)
            if stat_stdout_output: logger.debug(f"Perf stat stdout (if any):\n{stat_stdout_output}")
        else:
            logger.error("Perf stat FAILED.")
            if stat_stderr_output: logger.error(f"Perf stat Stderr Output:\n{stat_stderr_output}")
            if stat_stdout_output: logger.error(f"Perf stat Stdout Output:\n{stat_stdout_output}")

    # 4. Cleanup
    if not args.no_cleanup:
        if compiled_on_the_fly and os.path.exists(target_executable_for_perf):
            logger.info(f"Cleaning up compiled executable: {target_executable_for_perf}")
            os.remove(target_executable_for_perf)
        if created_dummy_source and os.path.exists(dummy_cpp_file_name):
            logger.info(f"Cleaning up dummy source file: {dummy_cpp_file_name}")
            os.remove(dummy_cpp_file_name)
        if os.path.exists(args.perf_data_file): # Default is perf.data or user-specified
            logger.info(f"Cleaning up perf data file: {args.perf_data_file}")
            os.remove(args.perf_data_file)
    else:
        logger.info("Skipping cleanup of generated files due to --no-cleanup.")

    logger.info("PerfTool script finished.") 