#!/usr/bin/env python3
# See LICENSE for details

import os
import sys
import time
import re # For parsing LLM output
from core.step import Step
from core.llm_template import LLM_template # Required for setup strategy
from core.llm_wrap import LLM_wrap


class Replicator(Step):
    """
    Reads C++ source code and an identified bottleneck, then proposes and generates 
    multiple code modifications (variants) to address the performance issue.

    Input data keys expected:
      - 'source_code': str (The C++ source code)
      - 'bottleneck_location': str (e.g., function name, file:line)
      - 'bottleneck_type': str (e.g., "High CPU usage in loop")
      - 'analysis_hypothesis': str (Hypothesis from Performance Analysis Agent)
    
    Output data keys produced:
      - 'proposed_fix_strategy': str
      - 'modified_code_variants': list[dict] (Each dict: {'variant_id': str, 'explanation': str, 'code': str})
    """

    def setup(self):
        super().setup()
        self.prompt_yaml_file = os.path.join(os.path.dirname(__file__),
                                             'prompts/code_replication_prompt.yaml')
        
        # Load the full prompt configuration file
        full_config_loader = LLM_template(self.prompt_yaml_file)
        if not full_config_loader.template_dict:
            raise ValueError(f"Could not load or parse {self.prompt_yaml_file}")

        # Define the expected top-level key in the YAML for this agent's configurations
        config_key = 'code_replication_prompt' 
        replication_configs = full_config_loader.template_dict.get(config_key, {})
        if not replication_configs:
            raise ValueError(f"'{self.prompt_yaml_file}' is missing '{config_key}' top-level key.")

        # Extract LLM settings from within the agent-specific config block
        actual_llm_settings = replication_configs.get('llm', {})
        if not actual_llm_settings:
            raise ValueError(f"Missing 'llm' section under '{config_key}' in {self.prompt_yaml_file}")

        # Define the main prompt name and extract its messages from within the agent-specific config block
        self.main_prompt_name = 'generate_variants_prompt' # This should match a key under `config_key` in the YAML
        prompt_messages = replication_configs.get(self.main_prompt_name, [])
        if not prompt_messages:
            raise ValueError(f"Missing '{self.main_prompt_name}' section under '{config_key}' in {self.prompt_yaml_file}")

        # Prepare the configuration for LLM_wrap, with 'llm' and the prompt at the top level of this dict
        llm_wrap_config = {
            'llm': actual_llm_settings,
            self.main_prompt_name: prompt_messages
        }
        
        if not hasattr(self, 'lw') or self.lw is None:
            self.lw = LLM_wrap(
                name='replicator',
                log_file='replicator.log',
                conf_file=self.prompt_yaml_file, # LLM_wrap might use this for relative paths if needed
                overwrite_conf=llm_wrap_config   # This provides the primary llm and prompt configuration
            )
            if self.lw.last_error:
                raise ValueError(self.lw.last_error)
        
        self.setup_called = True

    def _parse_llm_output(self, llm_response_text: str) -> tuple[str, list[dict]]:
        strategy = ""
        variants = []

        # Extract strategy
        strategy_match = re.search(r"Proposed Fix Strategy:(.*?)(?=### Variant 1|$)", llm_response_text, re.DOTALL | re.IGNORECASE)
        if strategy_match:
            strategy = strategy_match.group(1).strip()
        else:
            # Fallback or error if strategy is crucial and not found
            strategy = "Strategy not clearly parsed from LLM output."

        # Extract variants
        # Regex to find "### Variant X" and the C++ code block that follows
        # It also tries to capture an optional explanation before the code block.
        variant_pattern = re.compile(
            r"###\s*Variant\s*(\d+)(.*?)(?:```cpp\s*(.*?)\s*```)", 
            re.DOTALL | re.IGNORECASE
        )
        
        for match in variant_pattern.finditer(llm_response_text):
            variant_id = f"Variant {match.group(1)}"
            explanation_text = match.group(2).strip()
            # Clean up explanation: remove potential lead-in like "Rationale:" or C++ comments if LLM includes them outside code block
            explanation_text = re.sub(r'^(Rationale:|Explanation:)','', explanation_text, flags=re.IGNORECASE).strip()
            # Remove common C++ style comments if they are explanations before the code block
            explanation_text = re.sub(r'^//.*?', '', explanation_text, flags=re.MULTILINE).strip()

            code_block = match.group(3).strip()
            variants.append({
                'variant_id': variant_id,
                'explanation': explanation_text if explanation_text else "No explicit explanation provided.",
                'code': code_block
            })
            
        if not variants and not strategy_match:
             # If nothing was parsed, maybe the LLM output format was unexpected
             # Return the raw output as strategy and empty variants to signal a parsing issue
             return llm_response_text, []

        return strategy, variants

    def run(self, data):
        source_code = data.get('source_code')
        bottleneck_location = data.get('bottleneck_location')
        bottleneck_type = data.get('bottleneck_type')
        analysis_hypothesis = data.get('analysis_hypothesis')

        # If specific fields are missing, try to parse from 'performance_analysis'
        if not all([bottleneck_location, bottleneck_type, analysis_hypothesis]):
            performance_analysis_text = data.get('performance_analysis')
            if performance_analysis_text and isinstance(performance_analysis_text, str):
                print("Attempting to parse 'performance_analysis' for Replicator inputs.")
                
                # Try to parse Location
                if not bottleneck_location:
                    loc_match = re.search(r"\*\*\s*Location:\s*\*\*(.*?)(?:\n\s*-\s*\*\*|$)", performance_analysis_text, re.DOTALL | re.IGNORECASE)
                    if loc_match:
                        bottleneck_location = loc_match.group(1).strip()
                        print(f"  Parsed bottleneck_location: {bottleneck_location}")

                # Try to parse Metric/Impact for Bottleneck Type
                if not bottleneck_type:
                    type_match = re.search(r"\*\*\s*Metric/Impact:\s*\*\*(.*?)(?:\n\s*-\s*\*\*|$)", performance_analysis_text, re.DOTALL | re.IGNORECASE)
                    if type_match:
                        bottleneck_type = type_match.group(1).strip()
                        print(f"  Parsed bottleneck_type (from Metric/Impact): {bottleneck_type}")

                # Try to parse Likely Cause for Analysis Hypothesis
                if not analysis_hypothesis:
                    hyp_match = re.search(r"\*\*\s*Likely Cause:\s*\*\*(.*?)(?:\n\s*```cpp|$)", performance_analysis_text, re.DOTALL | re.IGNORECASE)
                    if hyp_match:
                        analysis_hypothesis = hyp_match.group(1).strip()
                        # Remove the code block if it got included in the hypothesis by the regex
                        analysis_hypothesis = re.sub(r"\s*```cpp.*?```", "", analysis_hypothesis, flags=re.DOTALL).strip()
                        print(f"  Parsed analysis_hypothesis: {analysis_hypothesis}")
            
            # If bottleneck_type is still not set after attempting to parse, provide a default.
            if not bottleneck_type:
                bottleneck_type = "General Performance Bottleneck"
                print(f"  Set default bottleneck_type: {bottleneck_type}")
        
        if not all([source_code, bottleneck_location, bottleneck_type, analysis_hypothesis]):
            missing = []
            if not source_code: missing.append('source_code')
            if not bottleneck_location: missing.append('bottleneck_location')
            if not bottleneck_type: missing.append('bottleneck_type')
            if not analysis_hypothesis: missing.append('analysis_hypothesis')
            error_msg = f"Error: Missing required input data fields for Replicator: {', '.join(missing)}"
            print(error_msg)
            # Decide how to handle this: raise error, or return data with error message
            data['replicator_error'] = error_msg
            data['proposed_fix_strategy'] = ""
            data['modified_code_variants'] = []
            return data

        prompt_dict = {
            'source_code': source_code,
            'bottleneck_location': bottleneck_location,
            'bottleneck_type': bottleneck_type,
            'analysis_hypothesis': analysis_hypothesis
        }

        response_texts = self.lw.inference(prompt_dict, prompt_index=self.main_prompt_name, n=1)

        if not response_texts or not response_texts[0]:
            llm_error = f"Error: No response from LLM for replication. LLM last error: {self.lw.last_error if self.lw else 'N/A'}"
            print(llm_error)
            data['replicator_error'] = llm_error
            data['proposed_fix_strategy'] = ""
            data['modified_code_variants'] = []
        else:
            # Assuming n=1, so we take the first response
            proposed_strategy, modified_variants = self._parse_llm_output(response_texts[0])
            data['proposed_fix_strategy'] = proposed_strategy
            data['modified_code_variants'] = modified_variants
            if not modified_variants and proposed_strategy == response_texts[0]: # Parsing failed
                 data['replicator_warning'] = "Could not parse LLM output into strategy and variants. Raw output in strategy."

        return data


if __name__ == '__main__':  # pragma: no cover
    start_time = time.time()
    # Ensure class name matches what's defined: Replicator
    rep_step = Replicator() 

    # Basic argument parsing (assuming Step class has it or it's added)
    # This part needs to be adapted to your actual Step class and how it handles I/O.
    # For testing, you might manually create 'input_data' or load it from a YAML.
    if hasattr(rep_step, 'parse_arguments'):
        rep_step.parse_arguments() 
    else:
        print("Warning: 'parse_arguments' not found on Replicator instance. Skipping.")
        # As a fallback for testing, you might set dummy input/output files:
        # rep_step.input_file = 'path/to/replicator_input.yaml' 
        # rep_step.output_file = 'replicator_output.yaml'

    end_time = time.time()
    print(f"\nTIME: parse duration: {(end_time-start_time):.4f} seconds\n")

    try:
        start_time = time.time()
        rep_step.setup()
        end_time = time.time()
        print(f"\nTIME: setup duration: {(end_time-start_time):.4f} seconds\n")

        # Example of creating dummy input data for run() method test:
        # This should ideally come from rep_step.input_data if loaded by parse_arguments/set_io
        if not hasattr(rep_step, 'input_data') or not rep_step.input_data:
            print("Warning: rep_step.input_data not populated. Using dummy data for run().")
            dummy_run_data = {
                'source_code': 'void old_function() { for(int i=0; i<100000; ++i) { volatile int x = i*i; } }',
                'bottleneck_location': 'old_function()',
                'bottleneck_type': 'High CPU usage in loop',
                'analysis_hypothesis': 'The loop in old_function is computationally intensive and has no dependencies, suitable for optimization.'
            }
            # If your Step class expects input_data to be an attribute:
            rep_step.input_data = dummy_run_data 
        
        # The step() method usually handles reading input_data and writing output_data.
        # It typically calls self.run(self.input_data).
        start_time = time.time()
        result_data = rep_step.step() # This should call run() internally
        end_time = time.time()
        print(f"\nTIME: step duration: {(end_time-start_time):.4f} seconds\n")

    except ValueError as e:
        print(f"ERROR during Replicator execution (ValueError): {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"ERROR during Replicator execution (Exception): {e}")
        import traceback
        traceback.print_exc()



