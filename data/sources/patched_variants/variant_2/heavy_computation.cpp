#include <iostream>
#include <vector>
#include <chrono>
#include <execution>

// Utilizing parallel algorithms for heavy computation
double perform_heavy_computation(int size) {
    std::vector<double> results(size * size * 100);
    std::for_each(std::execution::par, results.begin(), results.end(), [size, &results](double& result) {
        int index = &result - &results[0];
        int i = index / (size * 100);
        int j = (index % (size * 100)) / 100;
        int k = index % 100;
        double tempResult = static_cast<double>(i * j * k) / (size + 1.0);
        result = tempResult;
        if (static_cast<int>(tempResult) % 100000 == 0) {
            result -= 5.0;
        }
    });

    double finalResult = 0.0;
    for (auto& result : results) {
        finalResult += result;
    }
    return finalResult;
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