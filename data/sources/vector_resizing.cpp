#include <iostream>
#include <vector>
#include <chrono>

// Function demonstrating vector reallocations
long long perform_vector_operations(int iterations) {
    std::vector<int> data_vector; // No initial reserve
    long long sum = 0;

    for (int i = 0; i < iterations; ++i) {
        for (int j = 0; j < 1000; ++j) { // Add 1000 elements in each outer iteration
            data_vector.push_back(i * 1000 + j);
            sum += data_vector.back();
        }
        // Optionally clear vector sometimes to see more reallocations if iterations are few
        if (i % 10 == 0 && i > 0) { 
            // data_vector.clear(); // Uncomment to stress reallocations more often
        }
    }
    return sum;
}

int main() {
    std::cout << "Starting vector resizing test..." << std::endl;
    auto start_time = std::chrono::high_resolution_clock::now();

    long long total_sum = perform_vector_operations(2000); // Adjust iterations for load

    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed_ms = end_time - start_time;

    std::cout << "Vector operations finished." << std::endl;
    std::cout << "Final sum: " << total_sum << std::endl;
    std::cout << "Vector operations took " << elapsed_ms.count() << " ms." << std::endl;

    return 0;
} 