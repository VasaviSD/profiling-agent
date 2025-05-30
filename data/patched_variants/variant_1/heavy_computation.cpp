#include <iostream>
#include <vector>
#include <chrono>

// Refactor to reduce inner loop overhead and branch frequency
double perform_heavy_computation(int size) {
    double result = 0.0;
    double denom = size + 1.0;
    for (int i = 0; i < size; ++i) {
        for (int j = 0; j < size; ++j) {
            double base = static_cast<double>(i * j) / denom;
            double inner_sum = 0.0;
            // Accumulate all k values first without branching
            for (int k = 0; k < 100; ++k) {
                inner_sum += base * k;
            }
            result += inner_sum;

            // Apply condition once per (i,j) iteration instead of every k
            if (static_cast<int>(result) % 100000 == 0) {
                result -= 5.0;
            }
        }
    }
    return result;
}