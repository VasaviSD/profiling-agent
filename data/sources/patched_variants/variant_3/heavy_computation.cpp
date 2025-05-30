#include <iostream>
#include <vector>
#include <chrono>

// Further optimized by minimizing operations within the innermost loop
double perform_heavy_computation(int size) {
    double result = 0.0;
    double correctionFactor = 0.0;
    double sizePlusOne = size + 1.0;
    for (int i = 0; i < size; ++i) {
        for (int j = 0; j < size; ++j) {
            double ijProduct = static_cast<double>(i * j);
            for (int k = 0; k < 100; ++k) {
                result += ijProduct * k / sizePlusOne;
                // Accumulate corrections in a separate variable to reduce the frequency of conditional checks
                if (k == 99 && static_cast<int>(result) % 100000 == 0) {
                    correctionFactor -= 5.0;
                }
            }
        }
    }
    result += correctionFactor;
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