#include <iostream>
#include <vector>
#include <chrono>

// Hoist invariant computations outside inner loops and minimize condition checks inside innermost loop
double perform_heavy_computation(int size) {
    double result = 0.0;
    const double divisor = size + 1.0;

    for (int i = 0; i < size; ++i) {
        for (int j = 0; j < size; ++j) {
            double base_val = static_cast<double>(i * j) / divisor;
            // Accumulate partial sum for k loop
            double inner_sum = 0.0;
            for (int k = 0; k < 100; ++k) {
                inner_sum += base_val * k;
            }
            result += inner_sum;
            // Apply condition once per (i,j) pair instead of every inner iteration
            if (static_cast<int>(result) % 100000 == 0) {
                result -= 5.0;
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