#!/usr/bin/env python3
# See LICENSE for details

import os
import sys
import time
import re # For parsing LLM output
from core.step import Step
from core.llm_template import LLM_template
from core.llm_wrap import LLM_wrap


class Analyzer(Step):
    """
    Step to analyze C++ performance data using an LLM.

    Reads from:
      - source_code: str (The C++ source code of the project)
      - perf_command: str (The Linux perf command used to generate the data)
      - perf_report_output: str (The textual output from perf report)
      - threshold (optional): int (Override the threshold for significant bottlenecks, e.g., 5 for 5%)
      - context (optional): int (Override the number of context lines for code snippets, e.g., 3)
    Emits:
      - performance_analysis: str (The LLM's analysis of performance bottlenecks)
    """

    def setup(self):
        super().setup()
        self.prompt_yaml_file = os.path.join(os.path.dirname(__file__),
                                             'prompts/performance_analysis_prompt.yaml')
        
        # Load the full prompt configuration file
        full_config_loader = LLM_template(self.prompt_yaml_file)
        if not full_config_loader.template_dict:
            raise ValueError(f"Could not load or parse {self.prompt_yaml_file}")

        performance_analysis_configs = full_config_loader.template_dict.get('performance_analysis_prompt', {})
        if not performance_analysis_configs:
            raise ValueError(f"'{self.prompt_yaml_file}' is missing 'performance_analysis_prompt' top-level key.")

        # Extract LLM settings
        actual_llm_settings = performance_analysis_configs.get('llm', {})
        if not actual_llm_settings:
            raise ValueError(f"Missing 'llm' section under 'performance_analysis_prompt' in {self.prompt_yaml_file}")

        # Extract prompt1 messages using the new descriptive name
        prompt_key_in_yaml = 'generate_performance_analysis_prompt' # Updated key name
        prompt_messages = performance_analysis_configs.get(prompt_key_in_yaml, [])
        if not prompt_messages:
            raise ValueError(f"Missing '{prompt_key_in_yaml}' section under 'performance_analysis_prompt' in {self.prompt_yaml_file}")

        llm_wrap_config = {
            'llm': actual_llm_settings,
            prompt_key_in_yaml: prompt_messages # Use the new key name here
            # If there were other prompts like 'prompt2', they would be added here too.
        }

        if not hasattr(self, 'lw') or self.lw is None:
            self.lw = LLM_wrap(
                name='analyzer',
                log_file='analyzer.log',
                conf_file=self.prompt_yaml_file,  
                overwrite_conf=llm_wrap_config
            )
            if self.lw.last_error:
                raise ValueError(self.lw.last_error)

        # Store default threshold and context from the YAML (still useful for the run method's logic)
        self.default_threshold = performance_analysis_configs.get('threshold', 5)
        self.default_context_lines = performance_analysis_configs.get('context', 3)

        self.setup_called = True

    def _parse_performance_analysis(self, analysis_text: str) -> tuple[str, str, str]:
        """Parses the LLM's performance analysis text to extract structured fields."""
        location = "Not parsed"
        metric_impact_type = "Not parsed"
        hypothesis = "Not parsed"

        # Parse Location
        loc_match = re.search(r"\*\*\s*Location:\s*\*\*(.*?)(?:\n\s*-\s*\*\*|$)", analysis_text, re.DOTALL | re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()

        # Parse Metric/Impact (used as bottleneck_type)
        type_match = re.search(r"\*\*\s*Metric/Impact:\s*\*\*(.*?)(?:\n\s*-\s*\*\*|$)", analysis_text, re.DOTALL | re.IGNORECASE)
        if type_match:
            metric_impact_type = type_match.group(1).strip()

        # Parse Likely Cause (used as analysis_hypothesis)
        # Adjusted to stop before the code block if present, or end of section
        hyp_match = re.search(r"\*\*\s*Likely Cause:\s*\*\*(.*?)(?:\n\s*```cpp|\n\s*-\s*\*\*|$)", analysis_text, re.DOTALL | re.IGNORECASE)
        if hyp_match:
            hypothesis = hyp_match.group(1).strip()
            # Clean up: remove any trailing code block captured if the stop condition wasn't precise enough
            hypothesis = re.sub(r"\s*```cpp.*?```", "", hypothesis, flags=re.DOTALL).strip()
        
        return location, metric_impact_type, hypothesis

    def run(self, data):
        source_code = data.get('source_code', '')
        perf_command = data.get('perf_command', '')
        perf_report_output = data.get('perf_report_output', '')

        threshold = data.get('threshold', self.default_threshold)
        context_lines = data.get('context', self.default_context_lines)

        # This is the key that LLM_wrap will look for in its configuration
        # (which was constructed from llm_wrap_config in setup)
        prompt_key_for_inference = 'generate_performance_analysis_prompt' # Updated key name

        prompt_dict = {
            'source_code': source_code,
            'perf_command': perf_command,
            'perf_report_output': perf_report_output,
            'threshold': threshold,
            'context': context_lines
        }

        # LLM_wrap will use prompt_key_for_inference to find the prompt.
        response = self.lw.inference(prompt_dict, prompt_index=prompt_key_for_inference, n=1)

        if not response or not response[0]:
            analysis_result = "Error: No response from LLM or empty response."
            # Optionally, log or include self.lw.last_error if available and informative
            if self.lw and hasattr(self.lw, 'last_error') and self.lw.last_error:
                 analysis_result += f" LLM Error: {self.lw.last_error}"
        else:
            analysis_result = response[0]
            # Parse the analysis result to extract structured fields
            parsed_location, parsed_type, parsed_hypothesis = self._parse_performance_analysis(analysis_result)
            data['bottleneck_location'] = parsed_location
            data['bottleneck_type'] = parsed_type # This comes from Metric/Impact
            data['analysis_hypothesis'] = parsed_hypothesis

        data['performance_analysis'] = analysis_result
        return data


if __name__ == '__main__':  # pragma: no cover

    start_time = time.time()
    rep_step = Analyzer()
    # rep_step.parse_arguments()  # or rep_step.set_io(...)
    # For testing, manually set input and output if parse_arguments is not used
    # Example:
    # rep_step.set_io(input_file='path/to/your/analyzer_input_sample.yaml', output_file='output.yaml')
    
    # --- The following is a basic way to test the setup/run, assuming set_io or parse_arguments handles I/O ---
    # This part might need adjustment based on how your Step class loads input_data for setup/run
    
    # If your Step class loads input_data from input_file in parse_arguments or set_io,
    # ensure that's called before setup() and step() if they depend on self.input_data.
    # For this example, assuming `setup` does not depend on `self.input_data` from a file being pre-loaded
    # for its core LLM_wrap configuration logic, as it reads 'performance_analysis_prompt.yaml' directly.
    # The `run` method will depend on data passed to `rep_step.step(data_for_run)`.

    try:
        rep_step.parse_arguments() # Assuming this sets self.input_file and self.output_file
        end_time = time.time()
        print(f"\nTIME: parse duration: {(end_time-start_time):.4f} seconds\n")
        
        start_time = time.time()
        rep_step.setup()
        end_time = time.time()
        print(f"\nTIME: setup duration: {(end_time-start_time):.4f} seconds\n")
        
        # To test run, you'd need to load data similar to analyzer_input_sample.yaml
        # For example, if Step.step() calls self.run(self.input_data):
        # rep_step.input_data would need to be populated by parse_arguments or set_io
        # For a direct test of run, you might do:
        # from core.utils import read_yaml
        # test_run_data = read_yaml('step/analyzer/analyzer_input_sample.yaml') # Path to your input
        # result_data = rep_step.run(test_run_data)
        # print("Run method result:", result_data.get('performance_analysis'))
        
        start_time = time.time()
        result =rep_step.step() # This typically calls self.run(self.input_data) after loading it
        end_time = time.time()
        print(f"\nTIME: step duration: {(end_time-start_time):.4f} seconds\n")

    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()




