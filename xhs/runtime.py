from __future__ import annotations

import random
import time


def sleep_random(min_delay: float, max_delay: float) -> None:
    if max_delay < min_delay:
        max_delay = min_delay
    time.sleep(random.uniform(min_delay, max_delay))
