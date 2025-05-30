#include <iostream>
#include <vector>
#include <chrono>

// Optimized by reducing redundant calculations
double perform_heavy_computation(int size) {
    double result = 0.0;
    double sizePlusOne = size + 1.0; // Avoid repeated calculation
    for (int i = 0; i < size; ++i) {
        for (int j = 0; j < size; ++j) {
            double precomputedValue = static_cast<double>(i * j) / sizePlusOne;
            for (int k = 0; k < 100; ++k) {
                result += precomputedValue * k;
                if (static_cast<int>(result) % 100000 == 0) {
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

    double final_result = perform_heavy_computation(500);

    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed_ms = end_time - start_time;

    std::cout << "Heavy computation finished." << std::endl;
    std::cout << "Final result: " << final_result << std::endl;
    std::cout << "Computation took " << elapsed_ms.count() << " ms." << std::endl;

    return 0;
}