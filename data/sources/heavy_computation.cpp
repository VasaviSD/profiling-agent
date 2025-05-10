#include <iostream>
#include <vector>
#include <chrono>

// Function with a heavy computation load
double perform_heavy_computation(int size) {
    double result = 0.0;
    for (int i = 0; i < size; ++i) {
        for (int j = 0; j < size; ++j) {
            for (int k = 0; k < 100; ++k) { // Inner loop to make it more intensive
                result += static_cast<double>(i * j * k) / (size + 1.0);
                if (static_cast<int>(result) % 100000 == 0) { // Some condition to prevent over-optimization
                     result -= 5.0;
                }
            }
        }
    }
    return result;
}

int main() {
    std::cout << "Starting heavy computation test..." << std::endl;
    auto start_time = std::chrono::high_resolution_clock::now();

    double final_result = perform_heavy_computation(500); // Adjust size for desired load

    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed_ms = end_time - start_time;

    std::cout << "Heavy computation finished." << std::endl;
    std::cout << "Final result: " << final_result << std::endl;
    std::cout << "Computation took " << elapsed_ms.count() << " ms." << std::endl;

    return 0;
} 