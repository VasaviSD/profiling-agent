#include <iostream>
#include <string>
#include <vector>
#include <chrono>

// Function with potentially inefficient string operations
std::string perform_string_operations(int iterations) {
    std::string result_string = "Start:";
    std::vector<std::string> parts;
    for (int i = 0; i < 100; ++i) {
        parts.push_back("Part" + std::to_string(i));
    }

    for (int i = 0; i < iterations; ++i) {
        // Inefficient concatenation
        result_string += "Iteration" + std::to_string(i);
        for(const std::string& p : parts) {
            result_string += "-" + p;
            if (result_string.length() > 1024 * 5) { // Keep string from growing too excessively large
                result_string = result_string.substr(0, 100) + "...truncated..."; 
            }
        }
    }
    return result_string;
}

int main() {
    std::cout << "Starting string operations test..." << std::endl;
    auto start_time = std::chrono::high_resolution_clock::now();

    std::string final_str = perform_string_operations(200); // Adjust iterations for load

    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed_ms = end_time - start_time;

    std::cout << "String operations finished." << std::endl;
    // std::cout << "Final string (sample): " << final_str.substr(0, 200) << "..." << std::endl;
    std::cout << "String operations took " << elapsed_ms.count() << " ms." << std::endl;

    return 0;
} 