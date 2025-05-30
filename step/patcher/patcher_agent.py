#!/usr/bin/env python3
# See LICENSE for details

import os
from core.step import Step
# Assuming core.utils has write_yaml, read_yaml if this agent needs to process YAMLs directly
# For this simple version, it mainly writes source code files.

class Patcher(Step):
    """
    Applies a selected code variant to an original source file, saving it as a new file.

    This agent assumes the provided 'selected_variant_code' is the complete, 
    modified content for the new source file.

    Reads from (input YAML):
      - original_source_code: str (Content of the original C++ source file)
      - original_file_name: str (e.g., "main.cpp", used for naming the output file)
      - selected_variant_code: str (The full C++ code of the chosen variant)
      - variant_id: str (e.g., "Variant_1", for naming the output file)
      - output_base_dir: str (Base directory to save the patched file, e.g., "data/sources/patched_variants")
      # Optional, for context, but not directly used if variant code is full content:
      # - proposed_fix_strategy: str (Textual description of the fix strategy)

    Emits (output YAML):
      - patched_file_path: str (Full path to the newly created patched source file)
      - patcher_status: str ('success' or 'failed')
      - patcher_error (optional): str (Error message if patching failed)
    """

    def setup(self):
        super().setup() # Handles basic Step setup like I/O files if used via CLI
        # No LLM or specific prompt setup needed for this simple file-writing patcher.
        self.setup_called = True
        print("Patcher setup complete.")

    def run(self, data):
        output_data = {
            'patched_file_path': None,
            'patcher_status': 'pending',
            'patcher_error': None
        }

        try:
            original_source_code = data.get('original_source_code') # Not directly used if variant is full new code, but good for context
            original_file_name = data.get('original_file_name')
            selected_variant_code = data.get('selected_variant_code')
            variant_id = data.get('variant_id')
            output_base_dir = data.get('output_base_dir')

            if not all([original_file_name, selected_variant_code, variant_id, output_base_dir]):
                missing = []
                if not original_file_name: missing.append('original_file_name')
                if not selected_variant_code: missing.append('selected_variant_code')
                if not variant_id: missing.append('variant_id')
                if not output_base_dir: missing.append('output_base_dir')
                output_data['patcher_error'] = f"Missing required input fields: {', '.join(missing)}"
                output_data['patcher_status'] = 'failed'
                # self.error(output_data['patcher_error']) # If used via Step CLI
                return output_data

            # Construct the output filename
            name_part, ext_part = os.path.splitext(original_file_name)
            new_filename = f"{name_part}_{variant_id}{ext_part}"
            patched_file_path = os.path.join(output_base_dir, new_filename)

            # Ensure output directory exists
            if not os.path.exists(output_base_dir):
                os.makedirs(output_base_dir)
                print(f"Created output directory: {output_base_dir}")
            
            # Write the selected variant code to the new file
            with open(patched_file_path, 'w') as f:
                f.write(selected_variant_code)
            
            output_data['patched_file_path'] = os.path.abspath(patched_file_path)
            output_data['patcher_status'] = 'success'
            print(f"Successfully wrote patched file: {output_data['patched_file_path']}")

        except Exception as e:
            error_msg = f"Error during Patcher execution: {e}"
            print(error_msg)
            import traceback
            traceback.print_exc()            
            output_data['patcher_error'] = error_msg
            output_data['patcher_status'] = 'failed'
            # self.error(error_msg) # If used via Step CLI
        
        return output_data

if __name__ == '__main__': # pragma: no cover
    # This agent is typically orchestrated. For direct testing:
    patcher = Patcher()
    
    # For the direct run test below, we need to satisfy Step's setup requirements.
    # We are not using parse_arguments() here, so set_io() is needed.
    # Since we are testing run() directly and not the full step() output mechanism,
    # the specific output file for this set_io call is mostly a placeholder.
    dummy_input_for_set_io = './dummy_patcher_input.yaml' # Could be non-existent for this test type
    dummy_output_for_set_io = './dummy_patcher_output.yaml' 
    patcher.set_io(dummy_input_for_set_io, dummy_output_for_set_io)
    # patcher.parse_arguments() # Or patcher.set_io(...) for programmatic CLI-like use
    patcher.setup() # Call setup for completeness, and to satisfy Step base class
    # output = patcher.step()
    # print("Patcher output from step():", output)

    # 2. Direct run test
    print("--- Direct Patcher Run Test ---")
    test_input_data = {
        'original_source_code': '#include <iostream>\nint main() { std::cout << "Hello, Original World!" << std::endl; return 0; }',
        'original_file_name': 'original_main.cpp',
        'selected_variant_code': '#include <iostream>\nint main() { std::cout << "Hello, Patched World! Variant Alpha!" << std::endl; return 0; }',
        'variant_id': 'Alpha',
        'output_base_dir': './data/test_patched_output'
    }
    # patcher.setup() # Setup is now called above after set_io
    result = patcher.run(test_input_data)
    print("Patcher run() result:", result)

    if result.get('patcher_status') == 'success' and result.get('patched_file_path'):
        print(f"Patched file created at: {result['patched_file_path']}")
        # You can verify the content of the file here
        # os.remove(result['patched_file_path']) # Clean up if desired
        # if os.path.exists(test_input_data['output_base_dir']) and not os.listdir(test_input_data['output_base_dir']):
        #     os.rmdir(test_input_data['output_base_dir'])
    elif result.get('patcher_error'):
        print(f"Patcher test failed with error: {result['patcher_error']}") 