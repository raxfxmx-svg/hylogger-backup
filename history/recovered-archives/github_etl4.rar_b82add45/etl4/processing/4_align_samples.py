"""Map sample indices to depths and check tray and section ranges.
Map sample indices to depths and check tray and section ranges.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processing._etl_common import fail_main, run_holes
from processing.sample_alignment import align_hole


def main():
    run_holes("step 4 align samples", align_hole)


if __name__ == "__main__":
    fail_main(main)
