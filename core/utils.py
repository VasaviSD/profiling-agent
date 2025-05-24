#!/usr/bin/env python3
# See LICENSE for details

import yaml
import os

def read_yaml(file_path: str):
    """Reads a YAML file and returns its content as a Python dictionary.

    Args:
        file_path: The path to the YAML file.

    Returns:
        A dictionary representing the YAML content, or None if an error occurs.
    """
    try:
        # Ensure the directory exists before trying to read (though less critical for read)
        # directory = os.path.dirname(file_path)
        # if directory and not os.path.exists(directory):
        #     print(f"Warning: Directory for reading YAML does not exist: {directory}")
            # Depending on desired behavior, could return None or raise error here

        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        return data
    except FileNotFoundError:
        print(f"Error: YAML file not found at {file_path}")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {file_path}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading YAML file {file_path}: {e}")
        return None

def write_yaml(data: dict, file_path: str):
    """Writes a Python dictionary to a YAML file.

    Args:
        data: The dictionary to write.
        file_path: The path to the output YAML file.

    Returns:
        True if successful, False otherwise.
    """
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory for YAML output: {directory}")
        
        with open(file_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        # print(f"Successfully wrote YAML to {file_path}") # Optional: for verbose logging
        return True
    except yaml.YAMLError as e:
        print(f"Error writing YAML to file {file_path} (YAML issue): {e}")
        return False
    except IOError as e:
        print(f"Error writing YAML to file {file_path} (IO issue): {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while writing YAML file {file_path}: {e}")
        return False

if __name__ == '__main__': # pragma: no cover
    # Basic test cases
    test_data = {
        'name': 'Test Project',
        'version': 1.0,
        'settings': {
            'input_dir': '/path/to/input',
            'output_dir': '/path/to/output'
        },
        'files': ['file1.txt', 'file2.txt']
    }
    test_file_path = './temp_test.yaml'

    print(f"Attempting to write test YAML to: {test_file_path}")
    if write_yaml(test_data, test_file_path):
        print("Write successful.")
        print(f"Attempting to read test YAML from: {test_file_path}")
        read_data = read_yaml(test_file_path)
        if read_data:
            print("Read successful.")
            assert read_data == test_data, "Data mismatch after read/write!"
            print("Data integrity check passed.")
        else:
            print("Read failed.")
        
        # Clean up the test file
        try:
            os.remove(test_file_path)
            print(f"Cleaned up test file: {test_file_path}")
        except OSError as e:
            print(f"Error cleaning up test file {test_file_path}: {e}")
    else:
        print("Write failed.")

    print("\nTesting read of non-existent file:")
    read_yaml("./non_existent_file.yaml")

    print("\nTesting write to a problematic path (e.g. permission denied if run as non-root to /test.yaml)")
    # write_yaml(test_data, "/test.yaml") # This would likely fail, commented out for safety
    print("Write test to restricted path skipped.") 