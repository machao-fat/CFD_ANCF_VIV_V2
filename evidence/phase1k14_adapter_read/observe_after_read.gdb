set pagination off
set confirm off
set breakpoint pending on
set disable-randomization off
set print thread-events off
python
import datetime
import hashlib
import json
import math
import os
import struct
import gdb

EXPECTED_ADAPTER = "/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so"
EXPECTED_SHA256 = "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
READ_RETURN_OFFSET = 0xD7
read_counter = 0
return_breakpoint = None

class AfterRead(gdb.Breakpoint):
    def stop(self):
        global read_counter
        read_counter += 1
        record = {
            "event": "K14_PRECICE_READDATA_RETURN",
            "read_index": read_counter,
            "wall_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "observation": "adapter Interface::readCouplingData after Participant::readData returned",
        }
        try:
            pointer = int(gdb.parse_and_eval("$r14"))
            count = int(gdb.parse_and_eval("$r15"))
            if pointer == 0 or count < 1 or count > 10000:
                raise ValueError("invalid buffer pointer or scalar count: %s %s" % (pointer, count))
            raw = bytes(gdb.selected_inferior().read_memory(pointer, count * 8))
            values = struct.unpack("<" + "d" * count, raw)
            record["scalar_count"] = count
            record["buffer_pointer"] = hex(pointer)
            record["first_six_scalars"] = list(values[:6])
            record["nonzero_scalar_count"] = sum(value != 0 for value in values)
            record["finite"] = all(math.isfinite(value) for value in values)
            if count % 2 == 0:
                x_values = values[0::2]
                y_values = values[1::2]
                record["vector_count_2d"] = count // 2
                record["x_min"] = min(x_values)
                record["x_max"] = max(x_values)
                record["y_min"] = min(y_values)
                record["y_max"] = max(y_values)
                record["max_vector_norm"] = max(math.hypot(x, y) for x, y in zip(x_values, y_values))
        except Exception as exc:
            record["observation_error"] = str(exc)
        print("K14_READ_JSON " + json.dumps(record, sort_keys=True), flush=True)
        return False

class AtAdapterReadLoop(gdb.Breakpoint):
    def stop(self):
        global return_breakpoint
        if return_breakpoint is None:
            entry = int(gdb.parse_and_eval("$pc"))
            loaded_path = gdb.solib_name(entry)
            resolved = os.path.realpath(loaded_path) if loaded_path else None
            actual_sha = None
            if resolved and os.path.isfile(resolved):
                digest = hashlib.sha256()
                with open(resolved, "rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                actual_sha = digest.hexdigest()
            print("K14_LOADED_ADAPTER_JSON " + json.dumps({
                "path": resolved, "sha256": actual_sha, "entry_pc": hex(entry),
                "return_break_offset": hex(READ_RETURN_OFFSET)
            }, sort_keys=True), flush=True)
            if resolved != EXPECTED_ADAPTER or actual_sha != EXPECTED_SHA256:
                print("K14_IDENTITY_MISMATCH_STOP", flush=True)
                return True
            return_breakpoint = AfterRead("*" + hex(entry + READ_RETURN_OFFSET), internal=True)
        return False

AtAdapterReadLoop("preciceAdapter::Interface::readCouplingData(double)")
end
run
