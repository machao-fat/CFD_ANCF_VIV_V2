from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import codecs
import math


@dataclass(frozen=True)
class MonitorEvent:
    event_type: str
    participant: str = "APP"
    physical_time: float | None = None
    window: int | None = None
    iteration: int | None = None
    value: object = None
    timestamp: str = ""

    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp or datetime.now(timezone.utc).isoformat()
        return data


def json_value(value):
    """Bootstrap relative residual inf is meaningful, not a nonfinite state."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):return {k:json_value(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):return [json_value(v) for v in value]
    return value


class LineBuffer:
    """UTF-8 and partial-line aware, with a bounded unfinished-line buffer."""
    def __init__(self, limit=262144):
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.pending = ''
        self.limit = limit

    def feed(self, data, final=False):
        text = self.pending + self.decoder.decode(data, final=final)
        parts = text.split('\n')
        self.pending = parts.pop()
        if len(self.pending)>self.limit:
            parts.append('APP_MONITOR_OVERSIZED_LINE: discarded unfinished line')
            self.pending = ''
        if final and self.pending:
            parts.append(self.pending); self.pending = ''
        return [line if len(line)<=self.limit else 'APP_MONITOR_OVERSIZED_LINE: discarded completed line' for line in parts]
