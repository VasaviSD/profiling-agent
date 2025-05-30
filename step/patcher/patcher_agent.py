#!/usr/bin/env python3
# See LICENSE for details

import os
import re # For sanitizing directory names
import copy # For deep copying input data
from core.step import Step
import time
# Assuming core.utils has write_yaml, read_yaml if this agent needs to process YAMLs directly
# For this simple version, it mainly writes source code files.

class Patcher(Step):
    DEFAULT_OUTPUT_BASE_DIR = "data/sources/patched_variants"
    """
    Applies all code variants found in the input to an original source file, 
    saving each variant as a new file in a dedicated subdirectory.
    All input key-value pairs are persisted in the output YAML.

    Reads from (input YAML):
      - source_code: str (Content of the original C++ source file, for context, not directly used for patching if variants are full code)
      - modified_code_variants: list 
        - A list of dictionaries, where each dictionary represents a code variant and must contain:
          - variant_id: str (e.g., "Variant_1", used for naming the output subdirectory)
          - code: str (The full C++ code of that variant)
      - original_file_name: str (e.g., "main.cpp", used as the filename for each patched variant)
      # Other fields from Replicator output (like perf_command, analysis, etc.) may be present but are ignored by Patcher.

    Emits (output YAML):
      - All key-value pairs from the input YAML are preserved.
      - patcher_status: str ('all_success', 'partial_success', or 'all_failed') (overwrites if present in input)
      - patcher_overall_error (optional): str (High-level error message if something fundamental failed) (overwrites if present in input)
      - patched_variants_results: list (overwrites if present in input)
        - A list of dictionaries, one for each attempted variant patch:
          - variant_id: str
          - patched_file_path: str (Full path to the newly created patched source file, if successful)
          - status: str ('success' or 'failed')
          - error: str (Error message if patching this specific variant failed, None if successful)
    """

    def _sanitize_filename(self, filename):
        """Sanitizes a string to be a valid filename."""
        # Replace spaces with underscores
        s = filename.replace(" ", "_")
        # Remove characters that are not alphanumeric, underscore, hyphen, or dot
        s = re.sub(r'(?u)[^\w\.\-]', '', s)
        # Remove leading/trailing underscores/hyphens/dots (dots usually not leading/trailing in filenames but good to be safe)
        s = s.strip('_-. ')
        return s if s else "default_variant_name"

    def setup(self):
        super().setup() # Handles basic Step setup like I/O files if used via CLI
        # No LLM or specific prompt setup needed for this simple file-writing patcher.
        self.setup_called = True
        print("Patcher setup complete.")

    def run(self, data):
        # Start with a deep copy of input data to preserve all original fields
        output_data = copy.deepcopy(data)

        # Initialize/overwrite Patcher-specific output fields
        output_data['patcher_status'] = 'pending'
        output_data['patcher_overall_error'] = None
        output_data['patched_variants_results'] = []

        try:
            _ = data.get('source_code') # Original source code, kept for context, not directly used in patching logic if variants are complete files.
            modified_code_variants = data.get('modified_code_variants')
            original_file_name = data.get('original_file_name')

            # Validate required top-level fields
            missing_top_level = []
            if not modified_code_variants: missing_top_level.append('modified_code_variants (list of variants)')
            if not original_file_name: missing_top_level.append('original_file_name')

            if missing_top_level:
                output_data['patcher_overall_error'] = f"Missing required top-level input fields: {', '.join(missing_top_level)}"
                output_data['patcher_status'] = 'all_failed'
                return output_data

            if not isinstance(modified_code_variants, list) or not modified_code_variants:
                output_data['patcher_overall_error'] = "'modified_code_variants' must be a non-empty list."
                output_data['patcher_status'] = 'all_failed'
                return output_data

            success_count = 0
            failure_count = 0

            for variant_data in modified_code_variants:
                variant_result = {
                    'variant_id': None,
                    'patched_file_path': None,
                    'status': 'pending',
                    'error': None
                }

                if not isinstance(variant_data, dict):
                    variant_result['error'] = "Variant data is not a dictionary."
                    variant_result['status'] = 'failed'
                    output_data['patched_variants_results'].append(variant_result)
                    failure_count += 1
                    continue

                raw_variant_id = variant_data.get('variant_id')
                selected_variant_code = variant_data.get('code')
                
                # Store the original variant_id for the results, sanitize for directory name
                variant_result['variant_id'] = raw_variant_id if raw_variant_id else "UnknownVariant"
                sanitized_variant_id_for_dir = self._sanitize_filename(raw_variant_id).lower() if raw_variant_id else "unknownvariantdir"

                if not raw_variant_id or not selected_variant_code:
                    missing_variant_fields = []
                    if not raw_variant_id: missing_variant_fields.append('variant_id')
                    if not selected_variant_code: missing_variant_fields.append('code')
                    variant_result['error'] = f"Variant '{raw_variant_id or '(missing ID)'}' missing fields: {', '.join(missing_variant_fields)}"
                    variant_result['status'] = 'failed'
                    output_data['patched_variants_results'].append(variant_result)
                    failure_count += 1
                    continue
                
                try:
                    variant_output_dir = os.path.join(self.DEFAULT_OUTPUT_BASE_DIR, sanitized_variant_id_for_dir)
                    if not os.path.exists(variant_output_dir):
                        os.makedirs(variant_output_dir)
                        print(f"Created output directory: {variant_output_dir} for variant '{raw_variant_id}'")

                    # Sanitize original_file_name as well before joining path, just in case
                    safe_original_file_name = self._sanitize_filename(original_file_name)
                    if not safe_original_file_name:
                        raise ValueError("Original file name is empty or invalid after sanitization.")

                    patched_file_path = os.path.join(variant_output_dir, safe_original_file_name)
                    
                    with open(patched_file_path, 'w') as f:
                        f.write(selected_variant_code)
                    
                    variant_result['patched_file_path'] = os.path.abspath(patched_file_path)
                    variant_result['status'] = 'success'
                    print(f"Successfully wrote patched file for {raw_variant_id}: {variant_result['patched_file_path']}")
                    success_count += 1
                except Exception as e_variant:
                    error_msg_variant = f"Error patching variant {raw_variant_id}: {e_variant}"
                    print(error_msg_variant)
                    variant_result['error'] = error_msg_variant
                    variant_result['status'] = 'failed'
                    failure_count += 1
                
                output_data['patched_variants_results'].append(variant_result)

            if success_count > 0 and failure_count == 0:
                output_data['patcher_status'] = 'all_success'
            elif success_count > 0 and failure_count > 0:
                output_data['patcher_status'] = 'partial_success'
            elif success_count == 0 and failure_count > 0:
                output_data['patcher_status'] = 'all_failed'
            else: # Should not happen if modified_code_variants is non-empty
                output_data['patcher_status'] = 'all_failed' 
                output_data['patcher_overall_error'] = 'No variants processed or unexpected state.'

        except Exception as e_global:
            error_msg_global = f"Critical error during Patcher execution: {e_global}"
            print(error_msg_global)
            import traceback
            traceback.print_exc()            
            # Ensure Patcher-specific fields are present even in critical error cases if initialized from deepcopy
            output_data['patcher_overall_error'] = output_data.get('patcher_overall_error', error_msg_global) 
            output_data['patcher_status'] = output_data.get('patcher_status', 'all_failed')
            if 'patched_variants_results' not in output_data:
                output_data['patched_variants_results'] = []
        
        return output_data

if __name__ == '__main__': # pragma: no cover
    patcher = Patcher()
    try:
        patcher.parse_arguments()
        setup_start_time = time.time()
        patcher.setup()
        setup_end_time = time.time()
        print(f"TIME: setup duration: {(setup_end_time-setup_start_time):.4f} seconds")
        
        step_start_time = time.time()
        patcher.step()
        step_end_time = time.time()
        print(f"TIME: step duration: {(step_end_time-step_start_time):.4f} seconds")
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"ERROR during Patcher execution (Setup/Config/File Error): {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"ERROR during Patcher execution (Unexpected Error): {e}")
        import traceback
        traceback.print_exc()
    