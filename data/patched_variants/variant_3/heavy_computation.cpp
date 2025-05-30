#include <iostream>
#include <vector>
#include <chrono>

// Use formula for sum of k: sum_{k=0}^{99} k = 99*100/2 = 4950
// Replace branch with branchless conditional subtraction.
double perform_heavy_computation(int size) {
    double denom = size + 1.0;
    double result = 0.0;
    const int k_sum = 4950; // sum of 0..99

    for (int i = 0; i < size; ++i) {
        for (int j = 0; j < size; ++j) {
            double temp = static_cast<double>(i * j) / denom;
            result += temp * k_sum;

            // Branchless subtraction if condition met
            int cond = (static_cast<int>(result) % 100000 == 0);
            result -= 5.0 * cond;
        }
    }
    return result;
}