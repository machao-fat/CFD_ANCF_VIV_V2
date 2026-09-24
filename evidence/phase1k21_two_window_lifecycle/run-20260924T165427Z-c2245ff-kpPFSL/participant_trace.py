"""HH06 Case 1, single-slice ``Structure_0000`` preCICE wrapper.

This module is deliberately a small adapter layer.  It does not implement an
ANCF element or a new structural model: the P1 static state and explicit
section properties are loaded from the frozen HH06 artifacts, while the
existing ``PreciceStructureFleetBackend``, ``GenericStructuralCoordinator``
and persistent worker protocol remain the owners of communication,
gather/advance/scatter, and numerical integration respectively.

The default command is an offline contract audit.  A real coupling requires
the explicit ``--run`` switch and is intentionally not invoked by this file's
validation workflow.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from coupling.arbitrary_n_live_orchestration_v1 import (  # noqa: E402
    ForceSample,
    GenericStructuralCoordinator,
    OrchestrationSlice,
    SliceManifest,
    WorkerRequest,
)
from coupling.arbitrary_n_live_orchestration_v1.precice_backend import (  # noqa: E402
    PreciceStructureFleetBackend,
)
from coupling.arbitrary_n_live_orchestration_v1.coordinator import (  # noqa: E402
    _dot,
    checkpoint_sha256,
)
from coupling.multi_slice_mapping.mapping import ancf_hermite_H  # noqa: E402
from ancf.protocol import (  # noqa: E402
    HEADER,
    MAX_UINT64,
    MAGIC,
    MESSAGE_INITIALIZE,
    MESSAGE_INITIALIZE_ACK,
    MESSAGE_SHUTDOWN,
    encode_control,
)
from ancf.kernel_protocol import (  # noqa: E402
    KernelModel,
    KernelStepRequest,
    MESSAGE_KERNEL_STEP_RESPONSE,
    decode_kernel_response,
    encode_kernel_request,
    validate_kernel_response,
)


class HH06ContractError(RuntimeError):
    """A fail-closed HH06 contract or capability error."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HH06ContractError(f"{name} is not numeric") from exc
    if not math.isfinite(result):
        raise HH06ContractError(f"{name} is NaN/Inf")
    return result


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise HH06ContractError(f"missing contract document: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HH06ContractError(f"contract root is not an object: {path}")
    return value


def _resolve_path(raw: str | Path) -> Path:
    """Resolve Windows and WSL paths without changing provenance."""
    text = str(raw)
    candidate = Path(text)
    if candidate.is_file():
        return candidate
    if text.startswith("D:/") or text.startswith("D:\\"):
        wsl = Path("/mnt/d") / text[3:].replace("\\", "/")
        # P1 provenance roots are directories, while individual artifacts are
        # files.  Accept both so the same contract resolves under WSL.
        if wsl.is_file() or wsl.is_dir():
            return wsl
    if text.startswith("/mnt/") and len(text) >= 6:
        drive = text[5].upper()
        windows = Path(f"{drive}:" + text[6:].replace("/", "\\"))
        if windows.is_file():
            return windows
    return candidate


def _read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _sha256_numbers(values: Sequence[float]) -> str:
    return hashlib.sha256(struct.pack("<" + "d" * len(values), *values)).hexdigest()


def _parse_q_record(path: Path, selector: str, expected_dof: int) -> tuple[float, ...]:
    """Load only the selected Q record from the verified P1 text artifact."""
    lines = path.read_text(encoding="utf-8").splitlines()
    selected = False
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) >= 3 and fields[0] == "CASE" and fields[1] == selector:
            selected = True
            continue
        if selected and fields and fields[0] == "CASE":
            break
        if selected and fields and fields[0] == "Q":
            try:
                count = int(fields[1])
                values = tuple(_finite(value, f"{selector}.Q[{j}]") for j, value in enumerate(fields[2:]))
            except (IndexError, ValueError) as exc:
                raise HH06ContractError(f"invalid Q record in {path} near line {index + 1}") from exc
            if count != expected_dof or len(values) != expected_dof:
                raise HH06ContractError(
                    f"{selector} Q length mismatch: declared={count}, values={len(values)}, expected={expected_dof}"
                )
            return values
    raise HH06ContractError(f"Q record {selector} not found in {path}")


@dataclass(frozen=True)
class HH06ContractBundle:
    case_dir: Path
    root: Mapping[str, Any]
    structure: Mapping[str, Any]
    mapping: Mapping[str, Any]
    interface: Mapping[str, Any]
    p1_parameters: Mapping[str, Any]
    q0: tuple[float, ...]
    q0_artifact: Path
    config_file: Path
    dt_s: float
    duration_s: float
    unit_span_m: float
    slice_length_m: float
    slice_center_m: float

    @property
    def case_id(self) -> str:
        return str(self.root["case_id"])

    @property
    def dof(self) -> int:
        return int(self.structure["geometry"]["state_dof_count"])


@dataclass
class CouplingIterationState:
    """Participant-owned fixed-point history, separate from physical rollback.

    This object intentionally contains no ANCF q/qdot/qddot and no transport
    identity counters.  The coordinator owns physical checkpoints; the worker
    backend owns session-monotonic transport identities.
    """

    window_index: int
    iteration_index: int
    current_force_raw_N: tuple[float, float, float]
    force_source_global_time_s: float
    force_source_kind: str
    force_read_offset_s: float
    committed_motion_m: tuple[float, float, float]
    previous_force_raw_N: tuple[float, float, float] | None = None
    current_trial_displacement_m: tuple[float, float, float] | None = None
    previous_trial_displacement_m: tuple[float, float, float] | None = None
    residual_history: list[dict[str, float | None]] = field(default_factory=list)
    event_history: list[str] = field(default_factory=list)


def _phase1k18_7b_ancf_checkpoint_snapshot(stage: str, coordinator: GenericStructuralCoordinator) -> None:
    """Persist full ANCF state and checkpoint identity for S0/S1 only."""
    raw_path = os.environ.get("PHASE1K18_7B_ANCF_TRACE")
    if not raw_path:
        return
    checkpoint = coordinator._checkpoint
    live = dict(coordinator.backend.snapshot())
    checkpoint_state = None if checkpoint is None else dict(checkpoint.backend_state)

    def state_hashes(state: Mapping[str, Any] | None) -> dict[str, str] | None:
        if state is None:
            return None
        return {name: _sha256_numbers(state[name]) for name in ("q", "qdot", "qddot")}

    payload = {
        "stage": stage,
        "checkpoint_id": None if checkpoint is None else checkpoint.checkpoint_id,
        "checkpoint_sha256": None if checkpoint is None else checkpoint_sha256(checkpoint),
        "checkpoint_committed_step": None if checkpoint is None else checkpoint.committed_step,
        "checkpoint_backend_state": checkpoint_state,
        "live_backend_state": live,
        "checkpoint_state_sha256": state_hashes(checkpoint_state),
        "live_state_sha256": state_hashes(live),
        "live_equals_checkpoint": (
            None if checkpoint_state is None else all(
                live.get(name) == checkpoint_state.get(name)
                for name in ("q", "qdot", "qddot", "committed", "pending")
            )
        ),
    }
    output = Path(raw_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()


def _phase1k18_7b_pre_advance_attempt(
    *, window_index: int, iteration_index: int, force_raw_N: Sequence[float],
    trial_motion_m: Sequence[float], written_motion_m: Sequence[float],
    result: Mapping[str, Any], backend: Any,
) -> None:
    """Capture the sent retry trial even if the deliberate Fluid stop precedes advance return."""
    raw_path = os.environ.get("PHASE1K18_7B_PRE_ADVANCE_TRACE")
    if not raw_path:
        return
    payload = {
        "window_index": window_index,
        "iteration_index": iteration_index,
        "physical_identity": result.get("physical_identity"),
        "transport_ids": {key: result.get(key) for key in ("sequence", "request_id", "transaction_id")},
        "force_input_raw_N": list(force_raw_N),
        "D_trial_m": list(trial_motion_m),
        "D_written_to_precice_m": list(written_motion_m),
        "D_written_equals_trial": list(written_motion_m) == list(trial_motion_m[:2]),
        "q_sha256": _sha256_numbers(backend.q),
        "qdot_sha256": _sha256_numbers(backend.qdot),
        "qddot_sha256": _sha256_numbers(backend.qddot),
    }
    output = Path(raw_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()


def load_contract_bundle(case_dir: str | Path) -> HH06ContractBundle:
    case = Path(case_dir).expanduser().resolve()
    root = _json(case / "contract.json")
    structure = _json(case / "structure_contract.json")
    mapping = _json(case / "mapping_contract.json")
    interface = _json(case / "interface_contract.json")
    source_root = _resolve_path(str(root["p1_artifact"]["root"]))
    parameter_contract = _json(source_root / str(root["p1_artifact"]["parameter_contract"]))
    q_ref = structure["static_initial_state"]["serialized_q0"]
    q0_artifact = _resolve_path(str(q_ref.get("artifact_wsl_path") or q_ref["artifact"]))
    geometry = structure["geometry"]
    dof = int(geometry["state_dof_count"])
    q0 = _parse_q_record(q0_artifact, str(q_ref.get("selector", "CASE REF_NE32")).replace("CASE ", ""), dof)
    coupling = root["coupling"]
    structural_ref = mapping["structural_reference"]
    fluid = mapping["fluid_interface"]
    config = case / "precice-config.xml"
    return HH06ContractBundle(
        case_dir=case, root=root, structure=structure, mapping=mapping, interface=interface,
        p1_parameters=parameter_contract["parameters"], q0=q0, q0_artifact=q0_artifact,
        config_file=config, dt_s=_finite(coupling["dt_s"], "coupling.dt_s"),
        duration_s=_finite(coupling["duration_s"], "coupling.duration_s"),
        unit_span_m=_finite(fluid["cfd_extrusion_span_m"], "fluid_interface.cfd_extrusion_span_m"),
        slice_length_m=_finite(structural_ref["deltaL_m"], "structural_reference.deltaL_m"),
        slice_center_m=_finite(structural_ref["slice_center_s_m"], "structural_reference.slice_center_s_m"),
    )


def build_manifest(bundle: HH06ContractBundle) -> SliceManifest:
    """Build the one-point, LegacyPointLumped orchestration manifest."""
    item = OrchestrationSlice(
        slice_id="slice_0000", ordinal=0, s_ref_m=bundle.slice_center_m,
        slice_length_m=bundle.slice_length_m, unit_span_m=bundle.unit_span_m,
        fluid_participant="Fluid_0000", structure_participant="Structure_0000",
        structure_mesh="Structure-Mesh", fluid_mesh="Fluid-Mesh",
        force_data="Force", motion_data="Displacement", openfoam_case_id=bundle.case_id,
        force_slot=0, motion_slot=0,
    )
    return SliceManifest(
        schema_version="arbitrary-n-live-coupling-v1", case_id=bundle.case_id,
        reference_length_m=float(bundle.structure["geometry"]["length_m"]),
        active_start_m=bundle.slice_center_m - 0.5 * bundle.slice_length_m,
        active_end_m=bundle.slice_center_m + 0.5 * bundle.slice_length_m,
        reconstruction_mode="LegacyPointLumped", endpoint_policy="NearestConstant",
        structure_participant="Structure_0000", slices=(item,),
    )


def _hydro_capability() -> bool:
    """Return whether this checked-out Python wire protocol emits SHM1."""
    try:
        from ancf import kernel_protocol as protocol
        return hasattr(protocol, "SpanwiseHydrodynamicRegion") and hasattr(protocol.KernelModel, "__dataclass_fields__") and "hydrodynamic_regions" in protocol.KernelModel.__dataclass_fields__
    except Exception:
        return False


def audit_contract(bundle: HH06ContractBundle) -> dict[str, Any]:
    root = bundle.root
    geometry = bundle.structure["geometry"]
    pretension = bundle.structure["pretension"]
    coupling = root["coupling"]
    meshes = bundle.interface["meshes"]
    checks: dict[str, bool] = {}
    checks["status_is_dry_run"] = root.get("status") == "READY_FOR_DRY_RUN"
    checks["participants"] = (coupling.get("fluid_participant") == "Fluid_0000" and coupling.get("structure_participant") == "Structure_0000")
    checks["parallel_implicit"] = coupling.get("scheme") == "parallel-implicit"
    checks["hh06_geometry"] = (geometry.get("length_m") == 13.12 and geometry.get("diameter_m") == 0.028 and geometry.get("element_count") == 32 and geometry.get("state_dof_count") == 198)
    checks["q0_dimension_and_finite"] = len(bundle.q0) == 198 and all(math.isfinite(value) for value in bundle.q0)
    checks["one_structure_point"] = meshes["structure_coupling"].get("vertex_count") == 1
    checks["no_legacy_604_vertex"] = not bool(meshes["structure_coupling"].get("legacy_604_vertex_participant", False))
    checks["single_slice_mapping"] = (bundle.slice_center_m == 2.97 and bundle.slice_length_m == 1.98 and bundle.mapping["force_conversion"].get("double_counting_forbidden") is True)
    checks["absolute_displacement_declared"] = bundle.interface.get("displacement_type") == "absolute"
    checks["resultant_mapping_declared"] = bundle.interface.get("mapping_mode") == "single_slice_resultant_force"
    checks["tension_quantities_distinct"] = float(pretension["benchmark_top_tension_N"]) == 1175.0 and float(pretension["equilibrium_reaction_tension_N"]) == 1188.28
    try:
        ET.parse(bundle.config_file)
        checks["precice_xml_parse"] = True
    except (OSError, ET.ParseError):
        checks["precice_xml_parse"] = False
    try:
        _load_release_force_contract(bundle)
        checks["physical_release_force_provenance"] = True
    except (HH06ContractError, OSError, ValueError, KeyError, TypeError):
        checks["physical_release_force_provenance"] = False
    try:
        _precice_max_iterations(bundle.config_file)
        checks["precice_max_iterations_present"] = True
    except (HH06ContractError, OSError, ET.ParseError):
        checks["precice_max_iterations_present"] = False
    checks["force_initial_data_exchange"] = _force_exchange_initializes(bundle.config_file)
    checks["hydrodynamic_wire_extension"] = _hydro_capability()
    blocking = [name for name, passed in checks.items() if not passed]
    status = "PASS" if not blocking else "BLOCKED"
    return {
        "audit": "HH06_STRUCTURE_0000_WRAPPER_CONTRACT_AUDIT_V1",
        "status": status,
        "blocking_checks": blocking,
        "checks": checks,
        "case_dir": str(bundle.case_dir),
        "case_id": bundle.case_id,
        "participants": {"fluid": "Fluid_0000", "structure": "Structure_0000"},
        "model": {"length_m": geometry["length_m"], "diameter_m": geometry["diameter_m"], "elements": geometry["element_count"], "nodes": geometry["state_node_count"], "dof": geometry["state_dof_count"]},
        "mapping": {"mode": "single_slice_resultant_force", "structure_points": 1, "s_ref_m": bundle.slice_center_m, "deltaL_m": bundle.slice_length_m, "fluid_faces_external_only": True},
        "tension": {"benchmark_top_tension_N": pretension["benchmark_top_tension_N"], "equilibrium_reaction_tension_N": pretension["equilibrium_reaction_tension_N"]},
        "q0": {"artifact": str(bundle.q0_artifact), "sha256": _sha256(bundle.q0_artifact), "count": len(bundle.q0), "q_sha256": _sha256_numbers(bundle.q0), "velocity_zero": True},
        "wire_capability": {"SHM1_hydrodynamic_regions": _hydro_capability(), "note": "Current checked-out protocol must expose SHM1 before a wet-mass runtime is authorized."},
        "iteration_cap": {
            "contract_json": coupling.get("max_iterations"),
            "precice_xml": _precice_max_iterations(bundle.config_file) if checks["precice_max_iterations_present"] else None,
            "values_match": (
                int(coupling.get("max_iterations", -1)) == _precice_max_iterations(bundle.config_file)
                if checks["precice_max_iterations_present"] else False
            ),
        },
        "release_force": (
            {"Fx0_raw_N": root["initial_state"].get("Fx0_total_N"),
             "Fy0_raw_N": root["initial_state"].get("Fy0_total_N"),
             "source_global_time_s": root["initial_state"].get("openfoam_global_time_s"),
             "provenance": root["initial_state"].get("release_force_provenance")}
            if checks["physical_release_force_provenance"] else None
        ),
        "no_runtime_started": True,
    }


def _build_kernel_model(bundle: HH06ContractBundle) -> KernelModel:
    """Build the P1 explicit-section + SHM1 model; never silently fall back."""
    from ancf import kernel_protocol as kp
    region_type = getattr(kp, "SpanwiseHydrodynamicRegion", None)
    if region_type is None or "hydrodynamic_regions" not in KernelModel.__dataclass_fields__:
        raise HH06ContractError("checked-out kernel protocol has no SHM1 hydrodynamic-region extension")
    params = bundle.p1_parameters
    D = float(bundle.structure["geometry"]["diameter_m"])
    area = math.pi * D * D / 4.0
    ea = float(bundle.structure["stiffness"]["EA_N"])
    hydro = bundle.structure["mass"]["added_mass_per_length_kg_m"]
    region = region_type(0.0, float(bundle.structure["geometry"]["length_m"]), tuple(float(v) for v in hydro), (0.0, 0.0, 0.0))
    kwargs: dict[str, Any] = {
        "length_m": float(bundle.structure["geometry"]["length_m"]), "diameter_m": D, "inner_diameter_m": 0.0,
        "elements": int(bundle.structure["geometry"]["element_count"]), "slices": 1,
        "top_tension_N": float(bundle.structure["pretension"]["benchmark_top_tension_N"]),
        # The explicit SPX1 line properties are authoritative.  The legacy
        # scalar density is only a required wire field; derive an equivalent
        # value from the P1 line mass and outer reference area instead of
        # importing an unrelated material-density assumption.
        "youngs_modulus_Pa": ea / area,
        "material_density": float(bundle.structure["mass"]["mass_per_length_kg_m"]) / area,
        "fluid_density": 1000.0,
        "gravity": 9.81, "beta": 0.25, "gamma": 0.5,
        "newton_tolerance": float(params.get("dynamic_newton_tolerance", {}).get("value", 2e-10)),
        "damping_alpha": float(bundle.structure["damping"]["rayleigh_alpha_1_s"]),
        "damping_beta": float(bundle.structure["damping"]["rayleigh_beta_s"]),
        "gauss_order": 3, "mass_gauss_order": 5, "max_newton": 40,
        "slice_positions_m": (bundle.slice_center_m,),
        "section_property_mode": kp.SECTION_PROPERTY_MODE_EXPLICIT,
        "explicit_EA_N": ea, "explicit_EI_Nm2": float(bundle.structure["stiffness"]["EI_Nm2"]),
        "explicit_mass_per_length_kg_m": float(bundle.structure["mass"]["mass_per_length_kg_m"]),
        "explicit_displaced_area_m2": area,
        "base_load_source": kp.BASE_LOAD_SOURCE_MODEL_STATIC,
        "hydrodynamic_regions": (region,),
    }
    return KernelModel(**kwargs)


class PersistentHH06KernelBackend:
    """Stateful Python bridge; each request still carries complete state."""

    _MAX_TRANSPORT_SEQUENCE = 0xFFFFFFFF
    _REQUEST_ID_ORIGIN = 910000
    _TRANSACTION_ID_ORIGIN = 1910000

    def __init__(self, bundle: HH06ContractBundle, manifest: SliceManifest, worker_path: str | Path) -> None:
        self.bundle = bundle
        self.manifest = manifest
        self.worker_path = str(worker_path)
        self.mesh_nodes = tuple(float(bundle.structure["geometry"]["length_m"]) * i / 32.0 for i in range(33))
        self.model = _build_kernel_model(bundle)
        self.q = tuple(bundle.q0)
        self.qdot = (0.0,) * self.model.ndof
        self.qddot = (0.0,) * self.model.ndof
        # ``attempted_advance_count`` is diagnostic only.  It is deliberately
        # not checkpointed: a retry is a new wire attempt, not a new physical
        # window, and the diagnostic count must remain monotonic as well.
        self.attempted_advance_count = 0
        self.committed_advance_count = 0
        # A restarted physical segment resumes global_step/time, while the
        # fresh worker transport session begins its bridge-local step at 1.
        self._bridge_step_origin = 0
        # Transport identity belongs to the worker session, not to physical
        # solver state.  These counters therefore survive checkpoint/restore.
        self._transport_sequence_counter = 0
        self._transport_request_id_counter = self._REQUEST_ID_ORIGIN
        self._transport_transaction_id_counter = self._TRANSACTION_ID_ORIGIN
        self._pending = False
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if self.process is not None:
            raise HH06ContractError("worker already started")
        worker_environment = os.environ.copy()
        # The C++ worker keeps implicit same-window retry identity disabled by
        # default. This participant uses the already-qualified physical-identity
        # retry contract, so enable that protocol path explicitly per worker.
        worker_environment["CFD_ANCF_ALLOW_IMPLICIT_RETRY"] = "1"
        self.process = subprocess.Popen(
            [self.worker_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=worker_environment,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise HH06ContractError("worker streams are unavailable")
        self.process.stdin.write(encode_control(MESSAGE_INITIALIZE)); self.process.stdin.flush()
        header = _read_exact(self.process.stdout, HEADER.size)
        if len(header) != HEADER.size:
            raise HH06ContractError("worker initialize acknowledgement is missing")
        magic, length, message_type = HEADER.unpack(header)
        body = _read_exact(self.process.stdout, length)
        if magic != MAGIC or message_type != MESSAGE_INITIALIZE_ACK or len(body) != length:
            raise HH06ContractError("worker initialize acknowledgement is invalid")

    def snapshot(self) -> Mapping[str, Any]:
        # A checkpoint is intentionally physical-only.  In particular, do not
        # serialize sequence/request/transaction IDs (or their generators):
        # the persistent C++ worker keeps those transport identities monotonic
        # for the whole process lifetime.
        return {
            "q": list(self.q),
            "qdot": list(self.qdot),
            "qddot": list(self.qddot),
            "committed": self.committed_advance_count,
            "pending": self._pending,
        }

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        self.q = tuple(_finite(value, "snapshot.q") for value in snapshot["q"])
        self.qdot = tuple(_finite(value, "snapshot.qdot") for value in snapshot["qdot"])
        self.qddot = tuple(_finite(value, "snapshot.qddot") for value in snapshot["qddot"])
        if len(self.q) != self.model.ndof or len(self.qdot) != self.model.ndof or len(self.qddot) != self.model.ndof:
            raise HH06ContractError("checkpoint state dimension mismatch")
        pending = snapshot.get("pending", False)
        if not isinstance(pending, bool):
            raise HH06ContractError("checkpoint pending state must be boolean")
        # Older in-memory snapshots may still contain ``attempted``.  It is
        # intentionally ignored rather than copied into any transport counter.
        self.committed_advance_count = int(snapshot["committed"])
        self._pending = pending

    @staticmethod
    def _next_transport_counter(current: int, maximum: int, name: str) -> int:
        """Advance a session-monotonic wire counter, failing before wrap."""
        if current < 0 or current >= maximum:
            raise HH06ContractError(f"{name} exhausted; refusing transport-ID wraparound")
        return current + 1

    def advance(self, request: WorkerRequest) -> Mapping[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise HH06ContractError("worker is not started")
        if self._pending:
            raise HH06ContractError("tentative worker advance is still pending")
        if request.sld1 or len(request.slice_force_N) != 3:
            raise HH06ContractError("HH06 single-slice request must be LegacyPointLumped with one resultant force")
        self.attempted_advance_count += 1
        sequence = self._next_transport_counter(
            self._transport_sequence_counter, self._MAX_TRANSPORT_SEQUENCE, "sequence"
        )
        request_id = self._next_transport_counter(
            self._transport_request_id_counter, MAX_UINT64, "request_id"
        )
        transaction_id = self._next_transport_counter(
            self._transport_transaction_id_counter, MAX_UINT64, "transaction_id"
        )
        self._transport_sequence_counter = sequence
        self._transport_request_id_counter = request_id
        self._transport_transaction_id_counter = transaction_id

        # ``global_step`` and ``case_local_bridge_step`` identify the physical
        # coupling window.  They intentionally remain unchanged on an
        # implicit retry after rollback, while the wire identity above is new.
        physical_window = self.committed_advance_count + 1
        kernel_request = KernelStepRequest(
            sequence=sequence, global_step=physical_window,
            case_local_bridge_step=physical_window - self._bridge_step_origin,
            integer_tick=int(round(request.time_s * 1e9)),
            time_s=request.time_s, dt_s=self.bundle.dt_s, request_id=request_id,
            transaction_id=transaction_id, run_id="hh06-single-slice-structure-0000-v1",
            case_id=request.case_id, model=self.model, q=self.q, qdot=self.qdot, qddot=self.qddot,
            base_load=(0.0,) * self.model.ndof, slice_force=request.slice_force_N,
        )
        self.process.stdin.write(encode_kernel_request(kernel_request)); self.process.stdin.flush()
        header = _read_exact(self.process.stdout, HEADER.size)
        if len(header) != HEADER.size:
            raise HH06ContractError(f"worker response header missing at sequence {sequence}")
        magic, length, message_type = HEADER.unpack(header)
        body = _read_exact(self.process.stdout, length)
        if magic != MAGIC or message_type != MESSAGE_KERNEL_STEP_RESPONSE:
            raise HH06ContractError(f"worker response frame invalid at sequence {sequence}")
        response = decode_kernel_response(header + body); validate_kernel_response(kernel_request, response)
        self.q, self.qdot, self.qddot = response.q, response.qdot, response.qddot
        self._pending = True
        return {
            "iterations": response.iterations,
            "residual": response.residual,
            "q_sha256": _sha256_numbers(self.q),
            "qdot_sha256": _sha256_numbers(self.qdot),
            "qddot_sha256": _sha256_numbers(self.qddot),
            "sequence": sequence,
            "request_id": request_id,
            "transaction_id": transaction_id,
            "physical_identity": {
                "global_step": physical_window,
                "bridge_step": physical_window,
                "integer_tick": kernel_request.integer_tick,
                "time_s": kernel_request.time_s,
                "dt_s": kernel_request.dt_s,
            },
        }

    def commit(self) -> None:
        if not self._pending:
            raise HH06ContractError("no tentative worker state to commit")
        self.committed_advance_count += 1; self._pending = False

    def evaluate_position(self, s_ref_m: float) -> tuple[float, float, float]:
        H = ancf_hermite_H(float(s_ref_m), self.mesh_nodes, ndof=self.model.ndof)
        return _dot(H, self.q)  # type: ignore[return-value]

    def close(self) -> dict[str, Any]:
        if self.process is None:
            return {"started": False}
        result: dict[str, Any] = {"started": True, "pid": self.process.pid}
        try:
            if self.process.poll() is None and self.process.stdin is not None:
                self.process.stdin.write(encode_control(MESSAGE_SHUTDOWN)); self.process.stdin.flush(); self.process.stdin.close()
            self.process.wait(timeout=20)
        except Exception as exc:
            result["shutdown_error"] = f"{type(exc).__name__}: {exc}"
            if self.process.poll() is None:
                self.process.kill(); self.process.wait(timeout=20)
        stderr = self.process.stderr.read().decode("utf-8", errors="replace") if self.process.stderr else ""
        result.update({"return_code": self.process.returncode, "stderr": stderr, "closed": self.process.poll() is not None})
        return result


def _force_total(rows: Any) -> tuple[float, float, float]:
    """Accept exactly the one mapped structural resultant, never CFD faces."""
    if hasattr(rows, "tolist"):
        rows = rows.tolist()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise HH06ContractError("preCICE Force result is not a sequence")
    if len(rows) == 2 and all(isinstance(value, (int, float)) for value in rows):
        rows = [rows]
    if len(rows) != 1:
        raise HH06ContractError(f"Structure_0000 must receive one mapped force point, got {len(rows)}")
    row = rows[0]
    if not isinstance(row, Sequence) or len(row) not in (2, 3):
        raise HH06ContractError("mapped force point must be 2-D or 3-D")
    values = tuple(_finite(value, f"Force[{i}]") for i, value in enumerate(row))
    return (values[0], values[1], values[2] if len(values) == 3 else 0.0)


def _load_release_force_contract(bundle: HH06ContractBundle) -> dict[str, Any]:
    """Verify the numeric F0 contract against its frozen Phase 1C.7A evidence."""
    initial = bundle.root.get("initial_state")
    if not isinstance(initial, Mapping):
        raise HH06ContractError("initial_state is missing from HH06 contract")
    provenance = initial.get("release_force_provenance")
    if not isinstance(provenance, Mapping):
        raise HH06ContractError("physical release Force provenance is missing")

    result_path = (bundle.case_dir / str(provenance["result_json"])).resolve()
    expected_result_sha = str(provenance["result_json_sha256"])
    if not result_path.is_file() or _sha256(result_path) != expected_result_sha:
        raise HH06ContractError("frozen release Force result is missing or its SHA256 changed")
    result = _json(result_path)

    report_path = (bundle.case_dir / str(provenance["recovery_report"])).resolve()
    expected_report_sha = str(provenance["recovery_report_sha256"])
    if not report_path.is_file() or _sha256(report_path) != expected_report_sha:
        raise HH06ContractError("release Force recovery report is missing or its SHA256 changed")

    expected_identity = {
        "restart_case_id": str(bundle.root["case_id"]),
        "restart_time_directory": "30",
        "restart_global_time_s": 30.0,
        "restart_time_index": 150000,
        "patch": "cylinder",
    }
    actual_identity = {
        "restart_case_id": str(provenance["restart_case_id"]),
        "restart_time_directory": str(provenance["restart_time_directory"]),
        "restart_global_time_s": _finite(provenance["restart_global_time_s"], "F0.restart_global_time_s"),
        "restart_time_index": int(provenance["restart_time_index"]),
        "patch": str(provenance["patch"]),
    }
    if actual_identity != expected_identity:
        raise HH06ContractError(f"release Force restart identity mismatch: {actual_identity}")
    if result.get("classification") != "RELEASE_FORCE_RECOVERED_REPRODUCIBLY":
        raise HH06ContractError("frozen release Force result is not reproducibly qualified")
    if result.get("case_id") != expected_identity["restart_case_id"]:
        raise HH06ContractError("release Force result case ID mismatch")
    if result.get("global_time_s") != expected_identity["restart_global_time_s"]:
        raise HH06ContractError("release Force result time mismatch")
    if result.get("patch") != expected_identity["patch"]:
        raise HH06ContractError("release Force result patch mismatch")

    contract_force = (
        _finite(initial["Fx0_total_N"], "initial_state.Fx0_total_N"),
        _finite(initial["Fy0_total_N"], "initial_state.Fy0_total_N"),
        _finite(provenance["Fz0_measured_N"], "release_force_provenance.Fz0_measured_N"),
    )
    evidence_force = tuple(_finite(result[key], f"release_force_result.{key}") for key in (
        "Fx_raw_N", "Fy_raw_N", "Fz_raw_N"
    ))
    if contract_force != evidence_force:
        raise HH06ContractError("numeric F0 contract differs from the frozen release Force result")
    if str(provenance.get("raw_force_units")) != "N":
        raise HH06ContractError("F0 must remain raw patch-integrated Force in N")
    tolerance = _finite(provenance["initial_data_comparison_tolerance_N"], "F0 comparison tolerance")
    if tolerance <= 0.0:
        raise HH06ContractError("F0 initial-data comparison tolerance must be positive")
    return {
        "force_raw_N": contract_force,
        "source_global_time_s": _finite(initial["openfoam_global_time_s"], "initial_state.openfoam_global_time_s"),
        "comparison_tolerance_N": tolerance,
        "result_json": str(result_path),
        "result_json_sha256": expected_result_sha,
    }


def _precice_max_iterations(config_file: str | Path) -> int:
    try:
        root = ET.parse(config_file).getroot()
    except (OSError, ET.ParseError) as exc:
        raise HH06ContractError("cannot parse preCICE configuration for max-iterations") from exc
    matches = [element for element in root.iter() if element.tag.split("}")[-1] == "max-iterations"]
    if len(matches) != 1:
        raise HH06ContractError(f"expected exactly one preCICE max-iterations element, found {len(matches)}")
    try:
        value = int(matches[0].attrib["value"])
    except (KeyError, ValueError) as exc:
        raise HH06ContractError("preCICE max-iterations value is invalid") from exc
    if value < 1:
        raise HH06ContractError("preCICE max-iterations must be positive")
    return value


def _force_exchange_initializes(config_file: str | Path) -> bool:
    try:
        root = ET.parse(config_file).getroot()
    except (OSError, ET.ParseError):
        return False
    exchanges = [element for element in root.iter() if element.tag.split("}")[-1] == "exchange"]
    return any(
        element.attrib.get("data") == "Force"
        and element.attrib.get("from") == "Fluid_0000"
        and element.attrib.get("to") == "Structure_0000"
        and element.attrib.get("initialize") == "yes"
        for element in exchanges
    )


def _vector_norm_delta(current: Sequence[float], previous: Sequence[float] | None) -> float | None:
    if previous is None:
        return None
    if len(current) != len(previous):
        raise HH06ContractError("diagnostic vector dimensions changed between coupling attempts")
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(current, previous)))


def _bounded_window_limit(bundle: HH06ContractBundle, requested: int | None) -> int:
    """Fail closed on the real HH06 case unless its exact bounded profile is requested."""
    if bundle.case_id == "ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1":
        authorization = bundle.root.get("execution_authorization")
        if not isinstance(authorization, Mapping):
            raise HH06ContractError("missing bounded execution authorization")
        if authorization.get("mode") != "BOUNDED_COUPLING_QUALIFICATION":
            raise HH06ContractError("HH06 runtime is not authorized for bounded coupling qualification")
        authorized_windows = authorization.get("max_windows")
        if isinstance(authorized_windows, bool) or not isinstance(authorized_windows, int) or authorized_windows != 25:
            raise HH06ContractError("HH06 bounded authorization must specify exactly max_windows=25")
        if requested != authorized_windows:
            raise HH06ContractError(
                "HH06 runtime requires explicit --max-windows 25; larger, smaller, or unlimited runs are forbidden"
            )
        return 25
    return int(bundle.root["coupling"]["accepted_window_limit"] if requested is None else requested)


def run(
    case_dir: str | Path,
    worker_path: str | Path,
    max_windows: int | None = None,
    *,
    trace_output: str | Path | None = None,
) -> dict[str, Any]:
    """Run the live wrapper only when the caller explicitly requests it.

    Each implicit attempt advances the ANCF state from the physical window
    checkpoint, writes that attempt's absolute trial displacement, and only
    then calls preCICE ``advance``.  The latest Force returned by that advance
    is retained as the next fixed-point iterate across physical rollback.
    """
    bundle = load_contract_bundle(case_dir)
    audit = audit_contract(bundle)
    if audit["status"] != "PASS":
        raise HH06ContractError("contract audit failed: " + ", ".join(audit["blocking_checks"]))
    limit = _bounded_window_limit(bundle, max_windows)
    manifest = build_manifest(bundle)
    item = manifest.slices[0]
    max_iterations = _precice_max_iterations(bundle.config_file)
    worker = PersistentHH06KernelBackend(bundle, manifest, worker_path)
    fleet = PreciceStructureFleetBackend(manifest, bundle.config_file, {item.slice_id: [(0.0, 0.0)]})
    coordinator = GenericStructuralCoordinator(manifest, worker, reference_positions_by_slice={item.slice_id: (0.0, 0.0, item.s_ref_m)})
    restart_state = bundle.root.get("phase1k18_7b_restart")
    if restart_state is not None:
        if not isinstance(restart_state, Mapping):
            raise HH06ContractError("Phase 1K.18.7B restart metadata must be an object")
        state_path = Path(str(restart_state["ancf_state_file"])).expanduser().resolve()
        if not state_path.is_file() or _sha256(state_path) != str(restart_state["ancf_state_sha256"]):
            raise HH06ContractError("preserved Phase 1K.7A ANCF state file hash mismatch")
        state_document = _json(state_path)
        accepted_window = int(restart_state["accepted_window_count"])
        accepted_state = state_document["accepted_state"]
        identity = state_document["physical_identity"]
        if (
            state_document.get("schema") != "PHASE1K18_7A_ACCEPTED_ANCF_STATE_V1"
            or state_document.get("accepted_window_index") != accepted_window
            or identity.get("accepted_global_time_s") != restart_state.get("global_time_s")
            or accepted_state.get("q_sha256") != _sha256_numbers(accepted_state["q"])
            or accepted_state.get("qdot_sha256") != _sha256_numbers(accepted_state["qdot"])
            or accepted_state.get("qddot_sha256") != _sha256_numbers(accepted_state["qddot"])
        ):
            raise HH06ContractError("preserved nonzero ANCF restart identity or state hash mismatch")
        worker.restore({
            "q": accepted_state["q"],
            "qdot": accepted_state["qdot"],
            "qddot": accepted_state["qddot"],
            "committed": accepted_window,
            "pending": False,
        })
        worker._bridge_step_origin = accepted_window
        # The new worker session intentionally starts fresh transport IDs;
        # only physical ANCF state/window identity is resumed.
        coordinator.committed_step = accepted_window
    records: list[dict[str, Any]] = []
    attempt_trace: list[dict[str, Any]] = []
    accepted = int(restart_state.get("accepted_window_count", 0)) if restart_state is not None else 0
    initial_position = worker.evaluate_position(item.s_ref_m)
    initial_reference = (0.0, 0.0, item.s_ref_m)
    initial_motion = tuple(
        initial_position[index] - initial_reference[index] for index in range(3)
    )
    # The preCICE Structure mesh is one 2-D coupling point.  Only the
    # absolute section displacement (x, y) is sent; the complete 198-DOF q0
    # remains internal to the ANCF participant.
    initial_motion_by_slice = {
        item.slice_id: [[initial_motion[0], initial_motion[1]]]
    }
    committed_motion = {item.slice_id: initial_motion}
    trace_stream = None
    fleet_initialized = False
    worker.start()
    try:
        fleet.initialize(initial_motion_by_slice=initial_motion_by_slice)
        fleet_initialized = True
        initial_rows = _force_total(
            fleet.read_force(item.slice_id, relative_read_time_s=0.0)
        )
        initial_state = bundle.root.get("initial_state", {})
        initial_provenance = initial_state.get("release_force_provenance", {})
        restart_force = restart_state.get("force_seed_raw_N") if restart_state is not None else None
        expected_f0 = tuple(
            _finite(value, f"phase1k18_7b_restart.force_seed_raw_N[{index}]")
            for index, value in enumerate(restart_force[:2])
        ) if restart_force is not None else (
            _finite(initial_state.get("Fx0_total_N"), "initial_state.Fx0_total_N"),
            _finite(initial_state.get("Fy0_total_N"), "initial_state.Fy0_total_N"),
        )
        f0_tolerance = _finite(
            restart_state.get("force_tolerance_N", 5.0e-13) if restart_state is not None
            else initial_provenance.get("initial_data_comparison_tolerance_N", 5.0e-13),
            "restart Force comparison tolerance" if restart_state is not None else "release Force comparison tolerance",
        )
        initial_force_error = max(abs(initial_rows[0] - expected_f0[0]), abs(initial_rows[1] - expected_f0[1]))
        if initial_force_error > f0_tolerance:
            raise HH06ContractError(
                "initialized preCICE Force does not match the contracted physical restart Force: "
                f"received={initial_rows[:2]}, expected={expected_f0}, error={initial_force_error:.17g} N, "
                f"tolerance={f0_tolerance:.17g} N"
            )
        source_global_time_s = _finite(
            restart_state.get("global_time_s") if restart_state is not None
            else initial_state.get("openfoam_global_time_s"),
            "restart global time" if restart_state is not None else "initial_state.openfoam_global_time_s",
        )
        expected_source_time_s = _finite(
            restart_state.get("global_time_s") if restart_state is not None else 30.0,
            "restart expected global time" if restart_state is not None else "release expected global time",
        )
        if abs(source_global_time_s - expected_source_time_s) > 1.0e-12:
            raise HH06ContractError("initial Force source time does not match the selected physical restart")

        if trace_output is not None:
            trace_path = Path(trace_output)
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation preserves earlier diagnostic evidence.
            trace_stream = trace_path.open("x", encoding="utf-8")
        current_force_raw_N = initial_rows
        current_force_read_offset_s = 0.0
        initial_force_source_kind = str(
            restart_state.get("force_source_kind", "ACCEPTED_CFD_RESTART_FORCE")
            if restart_state is not None else initial_provenance.get("source_kind", "HH06_PHYSICAL_RELEASE_FORCE")
        )
        while fleet.is_coupling_ongoing() and accepted < limit:
            window_index = accepted + 1
            previous_committed_motion = tuple(committed_motion[item.slice_id])
            state = CouplingIterationState(
                window_index=window_index,
                iteration_index=1,
                current_force_raw_N=current_force_raw_N,
                force_source_global_time_s=source_global_time_s,
                force_source_kind=initial_force_source_kind if window_index == 1 else "PRECEDING_ACCEPTED_PRECICE_EXCHANGE",
                force_read_offset_s=current_force_read_offset_s,
                committed_motion_m=previous_committed_motion,
            )
            checkpoint_active = False
            target_local_time_s = window_index * bundle.dt_s
            time_origin_global_s = _finite(
                restart_state.get("time_origin_global_s") if restart_state is not None
                else initial_state["openfoam_global_time_s"],
                "restart physical time origin" if restart_state is not None else "initial global time",
            )
            target_global_time_s = time_origin_global_s + target_local_time_s

            while True:
                iteration_events: list[str] = []
                checkpoint_request = bool(fleet.requires_writing_checkpoint())
                checkpoint_created = False
                if checkpoint_request and not checkpoint_active:
                    coordinator.checkpoint(f"hh06-window-{window_index}")
                    checkpoint_active = True
                    checkpoint_created = True
                    _phase1k18_7b_ancf_checkpoint_snapshot("S0_after_checkpoint_save", coordinator)
                    state.event_history.append("physical_checkpoint_created")
                    iteration_events.append("physical_checkpoint_created")
                if not checkpoint_active:
                    raise HH06ContractError(
                        f"preCICE did not request a physical checkpoint before window {window_index} ANCF trial"
                    )

                # The Force iterate is converted from raw integrated N exactly
                # once, here, by the established ForceSample contract.
                force_input_raw_N = state.current_force_raw_N
                sample = ForceSample.from_openfoam_integrated(
                    manifest, item.slice_id, iteration=window_index,
                    time_s=target_local_time_s, force_N=force_input_raw_N,
                    unit_span_m=bundle.unit_span_m,
                )
                coordinator.submit_force(sample)
                iteration_events.append("force_iterate_submitted_to_ancf")
                result = coordinator.advance_if_complete()
                scattered = coordinator.scatter_motion()
                trial_motion = tuple(scattered[item.slice_id])
                trial_vector = tuple(float(value) for value in trial_motion)
                iteration_events.append("ancf_trial_solved_and_scattered")
                trial_xy = (trial_vector[0], trial_vector[1])
                written_motion = [[trial_xy[0], trial_xy[1]]]
                written_xy_tuple = tuple(float(value) for value in written_motion[0])
                if written_xy_tuple != trial_vector[:2]:
                    raise HH06ContractError("D_written_to_precice differs from the ANCF trial interface displacement")

                # Critical implicit contract: write the exact current ANCF
                # trial before the advance that evaluates it.
                fleet.write_motion(item.slice_id, written_motion)
                iteration_events.append("trial_displacement_written_to_precice")
                _phase1k18_7b_pre_advance_attempt(
                    window_index=window_index,
                    iteration_index=state.iteration_index,
                    force_raw_N=force_input_raw_N,
                    trial_motion_m=trial_vector,
                    written_motion_m=written_xy_tuple,
                    result=result,
                    backend=coordinator.backend,
                )
                fleet.advance(bundle.dt_s)
                iteration_events.append("precice_advance_completed")
                rollback_request = bool(fleet.requires_reading_checkpoint())
                iteration_events.append(
                    "requires_reading_checkpoint_true" if rollback_request
                    else "requires_reading_checkpoint_false"
                )
                returned_force_read_offset_s = bundle.dt_s if rollback_request else 0.0
                returned_force_raw_N = _force_total(
                    fleet.read_force(
                        item.slice_id,
                        relative_read_time_s=returned_force_read_offset_s,
                    )
                )
                iteration_events.append(
                    "force_read_at_retry_endpoint_dt" if rollback_request
                    else "force_read_at_accepted_window_start_zero"
                )
                returned_force_source_kind = (
                    "CURRENT_WINDOW_ENDPOINT_RETRY_ITERATE"
                    if rollback_request else "ACCEPTED_WINDOW_BOUNDARY_FORCE"
                )

                previous_trial_xy = (
                    tuple(state.previous_trial_displacement_m[:2])
                    if state.previous_trial_displacement_m is not None
                    else tuple(state.committed_motion_m[:2])
                )
                trial_displacement_residual = _vector_norm_delta(trial_xy, previous_trial_xy)
                force_residual_raw = _vector_norm_delta(returned_force_raw_N, force_input_raw_N)
                strip_factor = bundle.slice_length_m / bundle.unit_span_m
                force_residual_applied = None if force_residual_raw is None else force_residual_raw * strip_factor
                written_motion_delta = _vector_norm_delta(trial_xy, state.previous_trial_displacement_m[:2] if state.previous_trial_displacement_m is not None else None)

                if rollback_request:
                    coordinator.rollback()
                    _phase1k18_7b_ancf_checkpoint_snapshot("S1_after_rollback_restore", coordinator)
                    commit_status = "rolled_back"
                    convergence_status = "retry_required"
                    state.event_history.append("physical_state_rolled_back_trial_retained_as_history")
                    iteration_events.append("physical_state_rolled_back_trial_retained_as_history")
                else:
                    coordinator.commit()
                    committed_motion = dict(scattered)
                    accepted += 1
                    commit_status = "committed"
                    convergence_status = (
                        "ACCEPTED_AT_ITERATION_LIMIT"
                        if state.iteration_index >= max_iterations
                        else "accepted_by_precice_before_iteration_limit"
                    )
                    state.event_history.append("accepted_trial_committed")
                    iteration_events.append("accepted_trial_committed")
                    checkpoint_active = False

                force_input_applied_N = tuple(float(value) for value in sample.values)
                transport_ids = {
                    "sequence": result.get("sequence"),
                    "request_id": result.get("request_id"),
                    "transaction_id": result.get("transaction_id"),
                }
                physical_identity = result.get("physical_identity")
                if not isinstance(physical_identity, Mapping):
                    raise HH06ContractError("worker result is missing its physical identity tuple")

                trace_record = {
                    "case_id": bundle.case_id,
                    "window_index": window_index,
                    "iteration_index": state.iteration_index,
                    "sequence": transport_ids["sequence"],
                    "request_id": transport_ids["request_id"],
                    "transaction_id": transport_ids["transaction_id"],
                    "transport_ids": transport_ids,
                    "physical_identity": dict(physical_identity),
                    "physical_time_s": target_global_time_s,
                    "case_local_time_s": target_local_time_s,
                    "force_source_global_time_s": state.force_source_global_time_s,
                    "force_source_kind": state.force_source_kind,
                    "force_input_source_global_time_s": state.force_source_global_time_s,
                    "force_input_read_offset_s": state.force_read_offset_s,
                    "force_input_source_kind": state.force_source_kind,
                    "force_input_vector_raw_N": list(force_input_raw_N),
                    "force_input_window_index": window_index,
                    "force_input_iteration_index": state.iteration_index,
                    "returned_force_source_global_time_s": target_global_time_s,
                    "returned_force_source_kind": returned_force_source_kind,
                    "force_source_time_global_s": target_global_time_s,
                    "force_read_time_s": returned_force_read_offset_s,
                    "force_read_offset_s": returned_force_read_offset_s,
                    "force_read_source_global_time_s": target_global_time_s,
                    "force_read_source_kind": returned_force_source_kind,
                    "force_source_vector_raw_N": list(returned_force_raw_N),
                    "force_read_vector_raw_N": list(returned_force_raw_N),
                    "force_read_window_index": window_index,
                    "force_read_iteration_index": state.iteration_index,
                    "window_target_global_time_s": target_global_time_s,
                    "dt_s": bundle.dt_s,
                    "D_previous_committed_m": list(previous_committed_motion),
                    "D_trial_from_ancf_m": list(trial_vector),
                    "D_trial_interface_m": list(trial_vector[:2]),
                    "D_written_to_precice_m": list(written_xy_tuple),
                    "written_motion_vector_m": [list(written_xy_tuple)],
                    "force_input_raw_N": list(force_input_raw_N),
                    "force_input_applied_N": list(force_input_applied_N),
                    "Fx_raw_N": force_input_raw_N[0],
                    "Fy_raw_N": force_input_raw_N[1],
                    "Fz_raw_N": force_input_raw_N[2],
                    "Fx_section_Npm": force_input_raw_N[0] / bundle.unit_span_m,
                    "Fy_section_Npm": force_input_raw_N[1] / bundle.unit_span_m,
                    "Fx_applied_N": force_input_applied_N[0],
                    "Fy_applied_N": force_input_applied_N[1],
                    "Fz_applied_N": force_input_applied_N[2],
                    "returned_force_raw_N": list(returned_force_raw_N),
                    "returned_force_applied_N": [value * strip_factor for value in returned_force_raw_N],
                    "Fx_returned_raw_N": returned_force_raw_N[0],
                    "Fy_returned_raw_N": returned_force_raw_N[1],
                    "force_residual_raw_N": force_residual_raw,
                    "force_residual_applied_N": force_residual_applied,
                    "trial_displacement_residual_m": trial_displacement_residual,
                    "written_motion_delta_m": written_motion_delta,
                    "checkpoint_request": checkpoint_request,
                    "checkpoint_created": checkpoint_created,
                    "rollback_request": rollback_request,
                    "commit_status": commit_status,
                    "iteration_events": iteration_events,
                    "time_window_complete": not rollback_request,
                    "convergence_status": convergence_status,
                    "precice_max_iterations": max_iterations,
                    "ancf_newton_iterations": result.get("iterations"),
                    "ancf_residual": result.get("residual"),
                    "q_state_hash": result.get("q_sha256"),
                    "qdot_state_hash": result.get("qdot_sha256"),
                    "qddot_state_hash": result.get("qddot_sha256"),
                }
                attempt_trace.append(trace_record)
                state.current_trial_displacement_m = trial_vector
                state.residual_history.append({
                    "force_residual_raw_N": force_residual_raw,
                    "trial_displacement_residual_m": trial_displacement_residual,
                })
                if trace_stream is not None:
                    trace_stream.write(json.dumps(trace_record, ensure_ascii=False, allow_nan=False) + "\n")
                    trace_stream.flush()

                if rollback_request:
                    state.previous_force_raw_N = force_input_raw_N
                    state.previous_trial_displacement_m = trial_vector
                    state.current_force_raw_N = returned_force_raw_N
                    state.force_source_global_time_s = target_global_time_s
                    state.force_source_kind = "PRECEDING_PRECICE_ADVANCE_ITERATE"
                    state.force_read_offset_s = returned_force_read_offset_s
                    state.iteration_index += 1
                    current_force_raw_N = returned_force_raw_N
                    source_global_time_s = target_global_time_s
                    current_force_read_offset_s = returned_force_read_offset_s
                    continue

                records.append({
                    "accepted_window": accepted,
                    "time_s": target_global_time_s,
                    "force_N": list(force_input_raw_N),
                    "returned_force_N": list(returned_force_raw_N),
                    "motion_m": list(scattered[item.slice_id]),
                    "written_motion_m": list(written_xy_tuple),
                    "convergence_status": convergence_status,
                    **result,
                })
                current_force_raw_N = returned_force_raw_N
                source_global_time_s = target_global_time_s
                current_force_read_offset_s = returned_force_read_offset_s
                initial_force_source_kind = "PRECEDING_ACCEPTED_PRECICE_EXCHANGE"
                break
    finally:
        try:
            if fleet_initialized:
                fleet.finalize()
        finally:
            try:
                worker.close()
            finally:
                if trace_stream is not None:
                    trace_stream.close()
    return {
        "status": "PASS",
        "accepted_windows": accepted,
        "records": records,
        "attempt_trace": attempt_trace,
        "manifest_sha256": manifest.manifest_sha256,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HH06 single-slice Structure_0000 adapter")
    parser.add_argument("--case", required=True, help="HH06 slice0000 case directory")
    parser.add_argument("--audit-only", action="store_true", help="validate contracts; never initialize preCICE")
    parser.add_argument("--run", action="store_true", help="explicitly enable live run (not used in offline validation)")
    parser.add_argument("--worker", help="persistent ANCF worker executable; required with --run")
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--trace-output", type=Path, help="write one JSON object per coupling attempt; refuses to overwrite")
    args = parser.parse_args(argv)
    if args.run and not args.worker:
        parser.error("--worker is required with --run")
    if args.run and args.max_windows is None:
        parser.error("--max-windows is required with --run; HH06 requires exactly the authorized value 25")
    try:
        bundle = load_contract_bundle(args.case)
        audit = audit_contract(bundle)
        if args.audit_output:
            args.audit_output.parent.mkdir(parents=True, exist_ok=True)
            args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        if not args.run:
            return 0 if audit["status"] == "PASS" else 2
        result = run(args.case, args.worker, args.max_windows, trace_output=args.trace_output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"HH06_STRUCTURE_0000_WRAPPER_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
