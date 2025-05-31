#!/usr/bin/env python3
# See LICENSE for details

import os
import time
from core.step import Step
from core.utils import read_yaml, write_yaml
from core.llm_template import LLM_template # For loading prompt config
from core.llm_wrap import LLM_wrap       # For interacting with LLM
import yaml # Add this import for string parsing

# Define the template for source code context separately, used in Python code
SOURCE_CODE_CONTEXT_TEMPLATE_STR = """
For additional context, here is the source code for the ORIGINAL version:
```cpp
{original_source_code}
```

And here is the source code for the VARIANT version:
```cpp
{variant_source_code}
```
"""

class Evaluator(Step):
    """
    Compares 'perf report' outputs from two profiler runs (original vs. variant)
    to evaluate if the variant provides a performance improvement using an LLM.

    Input (Primary YAML - specified via CLI):
      A YAML file containing:
      - `original_profiler_output_path`: str (Path to the Profiler's output YAML for the original code)
      - `variant_profiler_output_path`: str (Path to the Profiler's output YAML for the variant code)
      - `evaluator_specific_options` (optional): dict
          - `threshold` (optional): int (Override default threshold, e.g., 5 for 5%)
          - `context` (optional): int (Override default context lines)

    The referenced profiler output YAMLs must contain:
      - `perf_report_output`: str
      - `source_code`: str (Optional)

    Output (output YAML):
      - `evaluator_input_config_path`: str (Path to the primary input YAML for the Evaluator)
      - `actual_original_profiler_output_path`: str
      - `actual_variant_profiler_output_path`: str
      - `evaluation_results`: dict (The structured analysis from the LLM)
      - `evaluator_error`: str (Optional)
    """
    PROMPT_KEY_IN_YAML = "generate_evaluation_prompt"
    LLM_CONFIG_KEY_IN_YAML = "evaluator_llm_config"
    DEFAULT_THRESHOLD = 5
    DEFAULT_CONTEXT_LINES = 3

    def __init__(self, input_file=None, output_file=None, config_file=None):
        super().__init__()
        if config_file is not None: self.config_file = config_file
        if input_file is not None: self.input_file = input_file # Primary input YAML for Evaluator
        if output_file is not None: self.output_file = output_file
        
        self.path_to_original_profiler_yaml = None
        self.path_to_variant_profiler_yaml = None
        self.lw = None
        self.prompt_yaml_file = os.path.join(os.path.dirname(__file__), 'prompts', 'evaluator_prompt.yaml')
        self.threshold = self.DEFAULT_THRESHOLD
        self.context_lines = self.DEFAULT_CONTEXT_LINES
        self.setup_called = False

    def _add_specific_args(self, parser):
        # The base Step class adds --input-file, --output-file, --config by default.
        # We just use those defaults for the Evaluator's primary input YAML.
        pass # Rely on base Step class for standard arguments

    def setup(self):
        super().setup() # Handles self.input_file, self.output_file, self.config_file from CLI/constructor

        if not self.input_file:
            raise ValueError("Primary input YAML file for Evaluator must be specified.")
        if not os.path.exists(self.input_file):
            raise FileNotFoundError(f"Primary input YAML for Evaluator not found: {self.input_file}")
        if not self.output_file:
            raise ValueError("Output file must be specified.")

        evaluator_input_config = read_yaml(self.input_file)
        if not evaluator_input_config:
            raise ValueError(f"Could not read or parse Evaluator input YAML: {self.input_file}")

        self.path_to_original_profiler_yaml = evaluator_input_config.get('original_profiler_output_path')
        self.path_to_variant_profiler_yaml = evaluator_input_config.get('variant_profiler_output_path')

        if not self.path_to_original_profiler_yaml or not self.path_to_variant_profiler_yaml:
            raise ValueError("'original_profiler_output_path' and 'variant_profiler_output_path' must be specified in the Evaluator input YAML.")
        if not os.path.exists(self.path_to_original_profiler_yaml):
            raise FileNotFoundError(f"Original profiler output YAML not found: {self.path_to_original_profiler_yaml}")
        if not os.path.exists(self.path_to_variant_profiler_yaml):
            raise FileNotFoundError(f"Variant profiler output YAML not found: {self.path_to_variant_profiler_yaml}")

        # Load LLM prompt configuration
        if not os.path.exists(self.prompt_yaml_file):
            raise FileNotFoundError(f"Evaluator prompt YAML not found: {self.prompt_yaml_file}")
        full_prompt_config_loader = LLM_template(self.prompt_yaml_file)
        if not full_prompt_config_loader.template_dict:
            raise ValueError(f"Could not load or parse Evaluator prompt YAML: {self.prompt_yaml_file}")
        agent_specific_llm_configs = full_prompt_config_loader.template_dict.get(self.LLM_CONFIG_KEY_IN_YAML, {})
        if not agent_specific_llm_configs:
            raise ValueError(f"'{self.prompt_yaml_file}' is missing '{self.LLM_CONFIG_KEY_IN_YAML}' key.")

        # Override threshold/context from primary input YAML if provided there
        evaluator_options = evaluator_input_config.get('evaluator_specific_options', {})
        self.threshold = evaluator_options.get('threshold', agent_specific_llm_configs.get('threshold', self.DEFAULT_THRESHOLD))
        self.context_lines = evaluator_options.get('context', agent_specific_llm_configs.get('context', self.DEFAULT_CONTEXT_LINES))
        print(f"Evaluator using threshold: {self.threshold}%, context lines: {self.context_lines}")

        # LLM_wrap setup
        actual_llm_settings_for_agent = agent_specific_llm_configs.get('llm', {})
        prompt_messages = agent_specific_llm_configs.get(self.PROMPT_KEY_IN_YAML, [])
        if not prompt_messages: raise ValueError(f"Missing '{self.PROMPT_KEY_IN_YAML}' in {self.prompt_yaml_file}")
        
        llm_wrap_config_overrides = {
            'llm': actual_llm_settings_for_agent, 
            self.PROMPT_KEY_IN_YAML: prompt_messages
        }
        
        if not self.lw:
            # Ensure self.log_file is set, defaulting if not present from Step class
            current_log_file = self.log_file if hasattr(self, 'log_file') and self.log_file else 'evaluator.log'
            self.lw = LLM_wrap(
                name='evaluator',
                log_file=current_log_file,
                conf_file=self.prompt_yaml_file, # Agent's own prompt file acts as a base config for LLM_wrap
                overwrite_conf=llm_wrap_config_overrides # Specific prompts and agent LLM settings
            )
            if self.lw.last_error: 
                raise ValueError(f"LLM_wrap init failed: {self.lw.last_error}")

        self.setup_called = True

    def _parse_llm_yaml_output(self, yaml_string: str) -> dict | None:
        """Safely parses a YAML string, potentially stripping Markdown fences, and returns a dictionary."""
        cleaned_yaml_string = yaml_string.strip()
        
        # Check for and remove Markdown code block fences
        if cleaned_yaml_string.startswith("```yaml"):
            cleaned_yaml_string = cleaned_yaml_string[len("```yaml"):].lstrip() # Remove fence and leading whitespace/newlines
        elif cleaned_yaml_string.startswith("```"):
            cleaned_yaml_string = cleaned_yaml_string[len("```"):].lstrip()
            
        if cleaned_yaml_string.endswith("```"):
            cleaned_yaml_string = cleaned_yaml_string[:-len("```")]
        
        cleaned_yaml_string = cleaned_yaml_string.strip() # Remove any trailing whitespace/newlines

        if not cleaned_yaml_string:
            print("Warning: LLM output was empty after stripping potential Markdown fences.")
            return None
            
        try:
            data = yaml.safe_load(cleaned_yaml_string)
            if not isinstance(data, dict):
                print(f"Warning: LLM output was valid YAML but not a dictionary. Output after cleaning: {cleaned_yaml_string[:100]}...")
                return None
            return data
        except yaml.YAMLError as e:
            print(f"Error parsing YAML string from LLM: {e}. String after cleaning was: {cleaned_yaml_string[:200]}...")
            return None
        except Exception as e:
            print(f"An unexpected error occurred while parsing LLM YAML string: {e}")
            return None

    def run(self, data=None): # data parameter (from primary input YAML) is processed in setup
        if not self.setup_called: self.setup()

        output_data = {
            'evaluator_input_config_path': self.input_file, # Store as provided
            'actual_original_profiler_output_path': self.path_to_original_profiler_yaml, # Store as provided
            'actual_variant_profiler_output_path': self.path_to_variant_profiler_yaml, # Store as provided
            'evaluation_results': None,
            'evaluator_error': None
        }

        try:
            original_profiler_data = read_yaml(self.path_to_original_profiler_yaml)
            variant_profiler_data = read_yaml(self.path_to_variant_profiler_yaml)
            if not original_profiler_data: raise FileNotFoundError(f"Original data not found: {self.path_to_original_profiler_yaml}")
            if not variant_profiler_data: raise FileNotFoundError(f"Variant data not found: {self.path_to_variant_profiler_yaml}")

            original_perf = original_profiler_data.get('perf_report_output')
            variant_perf = variant_profiler_data.get('perf_report_output')
            if not original_perf: raise ValueError(f"'perf_report_output' missing in {self.path_to_original_profiler_yaml}")
            if not variant_perf: raise ValueError(f"'perf_report_output' missing in {self.path_to_variant_profiler_yaml}")

            original_source = original_profiler_data.get('source_code')
            variant_source = variant_profiler_data.get('source_code')
            source_code_context_section_str = ""
            if original_source and variant_source:
                source_code_context_section_str = SOURCE_CODE_CONTEXT_TEMPLATE_STR.format(original_source_code=original_source, variant_source_code=variant_source)
            elif original_source: source_code_context_section_str = f"For additional context, here is the source code for the ORIGINAL version:\n```cpp\n{original_source}\n```"
            elif variant_source: source_code_context_section_str = f"For additional context, here is the source code for the VARIANT version:\n```cpp\n{variant_source}\n```"

            prompt_dict = {
                'original_perf_report': original_perf, 'variant_perf_report': variant_perf,
                'source_code_context_section': source_code_context_section_str, 'threshold': self.threshold,
            }

            active_llm_wrapper = self.llm if hasattr(self, 'llm') and self.llm and hasattr(self.llm, 'inference') else self.lw
            if not active_llm_wrapper: raise EnvironmentError("LLM wrapper not initialized.")
            llm_response_str_list = active_llm_wrapper.inference(prompt_dict, prompt_index=self.PROMPT_KEY_IN_YAML, n=1)
            if not llm_response_str_list or not llm_response_str_list[0]:
                err_msg = "LLM returned empty response."
                if hasattr(active_llm_wrapper, 'last_error') and active_llm_wrapper.last_error: err_msg += f" LLM_wrap error: {active_llm_wrapper.last_error}"
                raise ValueError(err_msg)
            llm_response_str = llm_response_str_list[0]

            parsed_llm_yaml = self._parse_llm_yaml_output(llm_response_str)
            if not parsed_llm_yaml or 'evaluation' not in parsed_llm_yaml:
                output_data['evaluator_error'] = "Failed to parse YAML from LLM or 'evaluation' key missing."
                output_data['evaluation_results'] = {"raw_llm_response": llm_response_str}
            else:
                output_data['evaluation_results'] = parsed_llm_yaml['evaluation']
                expected_keys = ['comparison_summary', 'is_improvement', 'improvement_details', 'confidence_score', 'detailed_analysis', 'original_hotspots', 'variant_hotspots']
                missing_keys = [k for k in expected_keys if k not in output_data['evaluation_results']]
                if missing_keys: print(f"Warning: LLM output missing keys: {missing_keys}")
        except Exception as e:
            error_msg = f"Error during Evaluator execution: {e}"; print(error_msg)
            import traceback; traceback.print_exc()
            output_data['evaluator_error'] = error_msg
        return output_data

    # set_io is inherited from Step, used for programmatic IO setting if not using CLI
    # For this agent, self.input_file should be the path to the primary config YAML.

if __name__ == '__main__': # pragma: no cover
    evaluator = Evaluator()
    try:
        evaluator.parse_arguments() # Populates self.input_file, self.output_file etc. from CLI
        
        # Setup will read self.input_file (primary YAML) and then the two profiler YAMLs specified within it.
        # It also handles LLM setup.
        setup_start_time = time.time()
        evaluator.setup()
        setup_end_time = time.time()
        print(f"TIME: setup duration: {(setup_end_time - setup_start_time):.4f} seconds")
        
        # File existence for the *actual* profiler outputs is checked within setup()
        # No need for explicit checks here in __main__ if setup() is robust.

        step_start_time = time.time()
        evaluator.step() # Calls run() and writes output based on self.output_file
        step_end_time = time.time()
        print(f"TIME: step duration: {(step_end_time - step_start_time):.4f} seconds")

    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"ERROR during Evaluator CLI execution (Config/File/Input Error): {e}")
    except SystemExit:
        pass # Allow clean exit on input errors handled by argparse or initial checks
    except Exception as e:
        print(f"ERROR during Evaluator CLI execution (Unexpected Error): {e}")
        import traceback
        traceback.print_exc()
