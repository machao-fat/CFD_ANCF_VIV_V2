from dataclasses import dataclass, asdict
import math
import re
from pathlib import Path
from viv_app.generator.errors import GenerationError
from viv_app.utils.paths import local_path, within, CASES_ROOT


@dataclass(frozen=True)
class FlowProfile:
    kind: str = 'Uniform'
    u0: float = 0.31
    u_bottom: float = 0.31
    u_top: float = 0.31
    transition: float = 0.45
    u_active: float = 0.6
    u_inactive: float = 0.0

    def validate(self):
        if self.kind not in ('Uniform', 'Linear Shear', 'Step Current'):
            raise GenerationError('INVALID_FLOW_PROFILE', self.kind)
        for value in (self.u0, self.u_bottom, self.u_top, self.u_active, self.u_inactive):
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise GenerationError('INVALID_FLOW_PROFILE', 'speeds must be finite and non-negative')
        if not math.isfinite(self.transition) or not 0 <= self.transition <= 1:
            raise GenerationError('INVALID_FLOW_PROFILE', 'transition s/L must be in [0,1]')

    def velocity(self, s_over_l):
        self.validate()
        if self.kind == 'Uniform':
            return self.u0
        if self.kind == 'Linear Shear':
            return self.u_bottom + (self.u_top - self.u_bottom) * s_over_l
        return self.u_active if s_over_l <= self.transition else self.u_inactive


@dataclass(frozen=True)
class StructureParameters:
    diameter_m: float
    length_m: float
    ea_n: float
    ei_nm2: float
    mass_per_length: float
    pretension_n: float
    damping_alpha: float
    elements: int

    @property
    def nodes(self):
        return self.elements + 1


@dataclass(frozen=True)
class SimulationSpec:
    case_name: str
    baseline_path: str
    output_root: str
    initial_state_time: str
    positions_over_l: tuple[float, ...]
    mpi_ranks: tuple[int, ...]
    structure: StructureParameters
    flow: FlowProfile
    delta_t: float
    end_time: float
    write_interval: float
    placement: str = 'custom'
    enabled: tuple[bool, ...] = ()

    def validate(self):
        # Safe on Windows too; refuse reserved device names/trailing dots.
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,62}', self.case_name) or self.case_name.upper() in {
            'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))
        }:
            raise GenerationError('INVALID_CASE_NAME', self.case_name)
        n = len(self.positions_over_l)
        if not 1 <= n <= 32 or len(self.mpi_ranks) != n:
            raise GenerationError('INVALID_SLICE_COUNT', 'positions/ranks must have matching N=1..32')
        if any(isinstance(x, bool) or not math.isfinite(x) or not 0 <= x <= 1 for x in self.positions_over_l):
            raise GenerationError('INVALID_SLICE_POSITION', 's/L must be finite and in [0,1]')
        if any(b <= a for a,b in zip(self.positions_over_l, self.positions_over_l[1:])):
            raise GenerationError('DUPLICATE_OR_UNORDERED_SLICE_POSITION', 'positions must be strictly increasing')
        if any(isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 1024 for x in self.mpi_ranks):
            raise GenerationError('INVALID_MPI_RANKS', 'integer ranks in [1,1024] required')
        if self.enabled and (len(self.enabled) != n or not all(self.enabled)):
            raise GenerationError('DISABLED_SLICE_NOT_SUPPORTED', 'V1 N equals enabled participants; reduce N to remove slices')
        if self.placement not in ('uniform', 'custom'):
            raise GenerationError('INVALID_SLICE_PLACEMENT', self.placement)
        for name, value in [('deltaT',self.delta_t), ('endTime',self.end_time), ('writeInterval',self.write_interval)]:
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise GenerationError('INVALID_NUMERICS', f'{name} must be finite and >0')
        try:
            start = float(self.initial_state_time)
        except ValueError as exc:
            raise GenerationError('INVALID_INITIAL_TIME', self.initial_state_time) from exc
        if not math.isfinite(start) or start < 0 or self.end_time <= start:
            raise GenerationError('INVALID_NUMERICS', 'endTime must exceed selected initial time')
        self.flow.validate()
        root = local_path(self.output_root)
        if not within(root, CASES_ROOT):
            raise GenerationError('OUTPUT_OUTSIDE_APP_WORKSPACE', str(root))
        baseline = local_path(self.baseline_path)
        target = root / self.case_name
        if within(target, baseline) or within(baseline, target):
            raise GenerationError('BASELINE_OUTPUT_OVERLAP', str(target))
        s = self.structure
        for value in (s.diameter_m,s.length_m,s.ea_n,s.ei_nm2,s.mass_per_length):
            if isinstance(value,bool) or not math.isfinite(value) or value <= 0:
                raise GenerationError('INVALID_STRUCTURE_PARAMETERS', 'positive finite structural parameters required')
        if not math.isfinite(s.pretension_n) or s.pretension_n < 0 or not math.isfinite(s.damping_alpha) or s.damping_alpha < 0:
            raise GenerationError('INVALID_STRUCTURE_PARAMETERS', 'pretension/damping must be nonnegative')
        if isinstance(s.elements,bool) or not isinstance(s.elements,int) or not 1 <= s.elements <= 340:
            raise GenerationError('INVALID_STRUCTURE_PARAMETERS', 'element count exceeds wire DOF limit')

    def to_dict(self):
        return asdict(self)


def uniform_positions(count, length, start, end):
    # This is a display adapter, actual positions are checked by native builder.
    if not 1 <= count <= 32 or length <= 0:
        raise GenerationError('INVALID_SLICE_COUNT', str(count))
    return tuple((start+(i+0.5)*(end-start)/count)/length for i in range(count))
