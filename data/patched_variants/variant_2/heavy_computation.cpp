#include <iostream>
#include <vector>
#include <chrono>
#include <thread>
#include <atomic>

double perform_heavy_computation(int size) {
    const double divisor = size + 1.0;
    std::atomic<double> result(0.0);
    const int num_threads = std::thread::hardware_concurrency();
    if (num_threads == 0) {
        // Fallback if hardware_concurrency not detected
        const int fallback_threads = 4;
        return perform_heavy_computation(size); // fallback to single-threaded (or handle differently)
    }

    auto worker = [&](int start, int end) {
        double local_result = 0.0;
        for (int i = start; i < end; ++i) {
            for (int j = 0; j < size; ++j) {
                double base_val = static_cast<double>(i * j) / divisor;
                double inner_sum = 0.0;
                for (int k = 0; k < 100; ++k) {
                    inner_sum += base_val * k;
                }
                local_result += inner_sum;
                if (static_cast<int>(local_result) % 100000 == 0) {
                    local_result -= 5.0;
                }
            }
        }
        // Atomic add to global result
        double current = result.load();
        while (!result.compare_exchange_weak(current, current + local_result)) {}
    };

    std::vector<std::thread> threads;
    int chunk_size = size / num_threads;
    int remainder = size % num_threads;
    int start = 0;
    for (int t = 0; t < num_threads; ++t) {
        int end = start + chunk_size + (t < remainder ? 1 : 0);
        threads.emplace_back(worker, start, end);
        start = end;
    }
    for (auto& th : threads) {
        th.join();
    }
    return result.load();
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