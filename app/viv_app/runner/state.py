from enum import Enum


class RunState(str,Enum):
    CREATED='CREATED'
    VALIDATED='VALIDATED'
    PREFLIGHT_PASSED='PREFLIGHT_PASSED'
    PREPARING='PREPARING'
    PREPARED='PREPARED'
    STARTING='STARTING'
    HANDSHAKING='HANDSHAKING'
    RUNNING='RUNNING'
    COMPLETED='COMPLETED'
    FAILED='FAILED'
    ABORTING='ABORTING'
    ABORTED='ABORTED'


ACTIVE={RunState.PREPARING,RunState.STARTING,RunState.HANDSHAKING,RunState.RUNNING,RunState.ABORTING}
TRANSITIONS={
    RunState.CREATED:{RunState.VALIDATED,RunState.FAILED},
    RunState.VALIDATED:{RunState.PREFLIGHT_PASSED,RunState.FAILED},
    RunState.PREFLIGHT_PASSED:{RunState.PREPARING,RunState.FAILED},
    RunState.PREPARING:{RunState.PREPARED,RunState.FAILED,RunState.ABORTING},
    RunState.PREPARED:{RunState.STARTING,RunState.FAILED},
    RunState.STARTING:{RunState.HANDSHAKING,RunState.FAILED,RunState.ABORTING},
    RunState.HANDSHAKING:{RunState.RUNNING,RunState.FAILED,RunState.ABORTING},
    RunState.RUNNING:{RunState.COMPLETED,RunState.FAILED,RunState.ABORTING},
    RunState.ABORTING:{RunState.ABORTED,RunState.FAILED},
    RunState.COMPLETED:set(),RunState.FAILED:set(),RunState.ABORTED:set(),
}


class StateMachine:
    def __init__(self):self.state=RunState.CREATED
    def transition(self,state):
        state=RunState(state)
        if state not in TRANSITIONS[self.state]:raise ValueError(f'Illegal run transition: {self.state.value} → {state.value}')
        self.state=state
