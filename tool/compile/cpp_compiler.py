import logging
import os
from typing import List, Optional, Tuple
import argparse # Added for command-line arguments

from tool.tool import Tool

logger = logging.getLogger(__name__)


class CppCompiler(Tool):
    """
    Tool to compile C++ source files using a specified compiler (e.g., g++, clang++).
    """

    # Define presets as class attributes for clarity
    PRESET_FLAGS = {
        "debug_opt": ["-g", "-O3"],
        "opt_only": ["-O3"],
        "debug_only": ["-g"],
    }

    def __init__(self, compiler: str = 'g++'):
        """
        Initialize the CppCompiler.

        Args:
            compiler: The C++ compiler command (e.g., 'g++', 'clang++').
        """
        super().__init__()
        self.compiler = compiler
        self.source_files: List[str] = []
        self.output_executable: str = 'a.out'
        self.compile_flags: List[str] = []
        self.include_dirs: List[str] = []
        self.library_dirs: List[str] = []
        self.libraries: List[str] = []

    def setup(
        self,
        source_files: List[str],
        output_executable: str,
        compiler_executable: Optional[str] = None,
        compile_flags: Optional[List[str]] = None,
        include_dirs: Optional[List[str]] = None,
        library_dirs: Optional[List[str]] = None,
        libraries: Optional[List[str]] = None,
        optimization_preset: Optional[str] = None,
    ) -> bool:
        """
        Setup the compiler tool with necessary parameters.

        Args:
            source_files: List of C++ source file paths.
            output_executable: Desired name for the output executable.
            compiler_executable: Specific path to the compiler, if not in PATH. Defaults to self.compiler.
            compile_flags: List of additional compilation flags. These are appended to any preset flags.
            include_dirs: List of include directories (e.g., ["-I/path/to/include"]).
            library_dirs: List of library directories (e.g., ["-L/path/to/lib"]).
            libraries: List of libraries to link (e.g., ["-lmylib"]).
            optimization_preset: Optional preset for compilation flags.
                                 Accepted values: "debug_opt" (-g -O3),
                                                  "opt_only" (-O3),
                                                  "debug_only" (-g).

        Returns:
            True if setup is successful (compiler found), False otherwise.
        """
        self._is_ready = False
        compiler_to_check = compiler_executable if compiler_executable else self.compiler

        if not self.check_executable(compiler_to_check):
            logger.error(f"Compiler {compiler_to_check} not found or not executable. Error: {self.get_error()}")
            return False

        if not source_files:
            self.set_error("No source files provided for compilation.")
            logger.error(self.get_error())
            return False

        self.source_files = source_files
        self.output_executable = output_executable
        if compiler_executable: # If a specific path was provided and checked
            self.compiler = compiler_executable
        
        current_compile_flags = []
        if optimization_preset:
            if optimization_preset not in self.PRESET_FLAGS:
                self.set_error(f"Unknown optimization_preset: {optimization_preset}. "
                               f"Available presets: {list(self.PRESET_FLAGS.keys())}")
                logger.error(self.get_error())
                return False
            current_compile_flags.extend(self.PRESET_FLAGS[optimization_preset])
            logger.info(f"Applied optimization preset '{optimization_preset}': {' '.join(current_compile_flags)}")

        if compile_flags: # Add any explicitly provided flags
            current_compile_flags.extend(compile_flags)
            logger.info(f"Extended with explicit compile flags: {' '.join(compile_flags)}")

        self.compile_flags = current_compile_flags
        self.include_dirs = include_dirs if include_dirs else []
        self.library_dirs = library_dirs if library_dirs else []
        self.libraries = libraries if libraries else []

        self._is_ready = True
        logger.info(
            f"CppCompiler setup successful for sources: {self.source_files} -> {self.output_executable} using {self.compiler} "
            f"with flags: {' '.join(self.compile_flags) if self.compile_flags else 'None'}"
        )
        return True

    def compile(self) -> Tuple[bool, str, str]:
        """
        Executes the compilation command.

        Returns:
            A tuple (success: bool, stdout: str, stderr: str).
            Success is True if compilation returns exit code 0, False otherwise.
        """
        if not self.is_ready():
            logger.error("Compiler tool not ready. Call setup() first.")
            return False, "", self.get_error()

        cmd = [self.compiler]
        cmd.extend(self.compile_flags)
        cmd.extend([f"-I{d}" for d in self.include_dirs])
        cmd.extend([f"-L{d}" for d in self.library_dirs])
        cmd.extend(self.source_files)
        cmd.extend([f"-l{lib}" for lib in self.libraries]) # Common practice to put libraries last
        cmd.extend(['-o', self.output_executable])


        logger.info(f"Executing compilation command: {' '.join(cmd)}")
        result = self.run_command(cmd, capture_output=True, text=True)

        if result is None: # Error handled by run_command
            logger.error(f"Compilation command failed to run. Error: {self.get_error()}")
            return False, "", self.get_error()

        if result.returncode == 0:
            logger.info(f"Compilation successful: {self.output_executable}")
            return True, result.stdout, result.stderr
        else:
            self.set_error(f"Compilation failed with return code {result.returncode}.\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}")
            logger.error(
                f"Compilation failed for {' '.join(cmd)}.\nReturn code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
            )
            return False, result.stdout, result.stderr

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

    parser = argparse.ArgumentParser(description="C++ Compiler Tool using CppCompiler class.")
    parser.add_argument(
        "-s", "--source-files",
        nargs='+',
        help="One or more C++ source files to compile."
    )
    parser.add_argument(
        "-o", "--output-executable",
        default=None, # Default will be handled based on whether source_files are provided
        help="Name for the output executable. Defaults to 'a.out' or a test-specific name."
    )
    parser.add_argument(
        "-c", "--compiler",
        default='g++',
        help="The C++ compiler command (e.g., 'g++'). Default: 'g++'."
    )
    parser.add_argument(
        "-p", "--optimization-preset",
        choices=list(CppCompiler.PRESET_FLAGS.keys()),
        default=None,
        help=f"Optimization preset. Choices: {', '.join(CppCompiler.PRESET_FLAGS.keys())}."
    )
    parser.add_argument(
        "-f", "--compile-flags",
        nargs='*',
        default=[],
        help="Additional compile flags (e.g., -Wall -DDEBUG)."
    )
    parser.add_argument(
        "-I", "--include-dirs",
        nargs='*',
        default=[],
        help="Include directories."
    )
    parser.add_argument(
        "-L", "--library-dirs",
        nargs='*',
        default=[],
        help="Library directories."
    )
    parser.add_argument(
        "-l", "--libraries",
        nargs='*',
        default=[],
        help="Libraries to link (e.g., m pthread)."
    )
    args = parser.parse_args()

    source_files_to_compile = args.source_files
    output_exe_name = args.output_executable
    created_dummy_file = False
    dummy_cpp_file_name = "hello_compiler_cli.cpp"

    if not source_files_to_compile:
        logger.info("No source files provided via command line, using internal dummy C++ file.")
        cpp_content = """
        #include <iostream>
        #include <vector>
        #include <string>

        void print_message(const std::string& msg) {
            std::cout << msg << std::endl;
        }

        int main(int argc, char* argv[]) {
            std::vector<std::string> args_vec(argv, argv + argc);
            #ifdef DEBUG
            print_message("Debug mode is ON (CLI Test).");
            for(size_t i = 0; i < args_vec.size(); ++i) {
                 std::cout << "Arg[" << i << "]: " << args_vec[i] << std::endl;
            }
            #else
            print_message("Debug mode is OFF (CLI Test).");
            #endif
            print_message("Hello, C++ World from CppCompiler CLI!");
            return 0;
        }
        """
        with open(dummy_cpp_file_name, "w") as f:
            f.write(cpp_content)
        source_files_to_compile = [dummy_cpp_file_name]
        created_dummy_file = True
        if output_exe_name is None: # Default output for dummy
            output_exe_name = "hello_compiler_cli_app"
    elif output_exe_name is None: # Default output for user-provided files
        output_exe_name = "a.out"


    compiler_tool_instance = CppCompiler(compiler=args.compiler)

    setup_ok = compiler_tool_instance.setup(
        source_files=source_files_to_compile,
        output_executable=output_exe_name,
        # compiler_executable=args.compiler, # Redundant as it's passed in constructor
        optimization_preset=args.optimization_preset,
        compile_flags=args.compile_flags,
        include_dirs=args.include_dirs,
        library_dirs=args.library_dirs,
        libraries=args.libraries
    )

    if setup_ok:
        logger.info(f"Final compile flags: {' '.join(compiler_tool_instance.compile_flags)}")
        success, stdout, stderr = compiler_tool_instance.compile()
        if success:
            logger.info(f"Compilation SUCCEEDED. Executable: {output_exe_name}")
            logger.info("To run the compiled executable (example):")
            logger.info(f"  ./{output_exe_name} my_arg1 my_arg2")
            if stdout: print(f"STDOUT:\n{stdout}") # usually empty for successful compilation
            if stderr: print(f"STDERR:\n{stderr}") # may contain warnings
        else:
            logger.error(f"Compilation FAILED for {output_exe_name}.")
            # Error message is already set and logged by the compile method.
            # Additional context if needed:
            if stdout: logger.error(f"STDOUT:\n{stdout}")
            if stderr: logger.error(f"STDERR:\n{stderr}")
    else:
        logger.error(f"CppCompiler setup FAILED: {compiler_tool_instance.get_error()}")

    if created_dummy_file and os.path.exists(dummy_cpp_file_name):
        os.remove(dummy_cpp_file_name)
        logger.info(f"Cleaned up dummy source file: {dummy_cpp_file_name}")
    # Note: We are not cleaning up the compiled executable here, 
    # as the user might want to run it if compiled from command line. 