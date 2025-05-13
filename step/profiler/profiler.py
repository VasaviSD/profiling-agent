#!/usr/bin/env python3
# See LICENSE for details

import os
import sys
import time
from core.step import Step
from core.llm_wrap import LLM_wrap


class Profiler(Step):

    def setup(self):
        super().setup()

    def run(self, data):
        print(data)
        


if __name__ == '__main__':  # pragma: no cover

    start_time = time.time()
    rep_step = Profiler()
    rep_step.parse_arguments()  # or rep_step.set_io(...)
    end_time = time.time()
    print(f"\nTIME: parse duration: {(end_time-start_time):.4f} seconds\n")
    start_time = time.time()
    rep_step.setup()
    end_time = time.time()
    print(f"\nTIME: setup duration: {(end_time-start_time):.4f} seconds\n")
    start_time = time.time()
    #result = 
    rep_step.step()
    end_time = time.time()
    print(f"\nTIME: step duration: {(end_time-start_time):.4f} seconds\n")

    #result = wrap_literals(result)



