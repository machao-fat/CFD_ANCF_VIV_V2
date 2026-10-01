from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class RunOptions:
    startup_timeout_s: float = 180
    abort_grace_s: float = 10
    prepare_timeout_s: float = 300
    poll_interval_s: float = .1
    sample_interval_s: float = 1
    log_drain_timeout_s: float = 5

    def __post_init__(self):
        import math
        for value in self.__dict__.values():
            if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError('Run timeouts / intervals must be positive and finite')

    @classmethod
    def load(cls):
        return cls(**json.loads((Path(__file__).parent/'run_options.json').read_text()))
