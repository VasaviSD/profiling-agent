#include <iostream>
#include <vector>
#include <chrono>
#ifdef _OPENMP
#include <omp.h>
#endif

double perform_heavy_computation(int size) {
    double denom = size + 1.0;
    double result = 0.0;

    #pragma omp parallel for reduction(+:result) schedule(static)
    for (int i = 0; i < size; ++i) {
        double local_result = 0.0;
        for (int j = 0; j < size; ++j) {
            double base = static_cast<double>(i * j) / denom;
            double inner_sum = 0.0;
            for (int k = 0; k < 100; ++k) {
                inner_sum += base * k;
            }
            local_result += inner_sum;
            if (static_cast<int>(local_result) % 100000 == 0) {
                local_result -= 5.0;
            }
        }
        result += local_result;
    }
    return result;
}