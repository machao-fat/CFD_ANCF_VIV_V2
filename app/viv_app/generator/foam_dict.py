"""Conservative byte-preserving editor for literal OpenFOAM dictionaries.

Not a general OpenFOAM evaluator: preprocessing, code and substitutions are
rejected. Only an exact dictionary path can be edited. Binary U payloads are
opaque; just their verified ASCII header and final boundary dictionary are read.
"""
from dataclasses import dataclass
import re
from .errors import GenerationError

TOKEN = re.compile(rb'\s+|//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|[{}();\[\]]|[^\s{}();\[\]"]+', re.S)


@dataclass(frozen=True)
class Entry:
    start: int
    end: int
    tokens: tuple[bytes, ...]


class FoamDict:
    def __init__(self, data: bytes):
        self.data = data
        self.entries = {}
        self.blocks = set()
        self.tokens = []
        end = 0
        for m in TOKEN.finditer(data):
            if m.start() != end:
                raise ValueError('unrecognized dictionary bytes')
            end = m.end()
            t = m.group()
            if t.isspace() or t.startswith((b'//', b'/*')):
                continue
            if any(x in t for x in (b'#', b'$', b'\x00')):
                raise ValueError('OpenFOAM directives/substitution/binary are unsupported')
            self.tokens.append((t, m.start(), m.end()))
        if end != len(data):
            raise ValueError('unrecognized trailing dictionary bytes')
        self._parse(0, (), False)

    def _parse(self, index, prefix, nested):
        while index < len(self.tokens):
            key, _, _ = self.tokens[index]
            if key == b'}':
                if not nested:
                    raise ValueError('unexpected closing brace')
                return index + 1
            if key in (b'{', b';', b')', b']'):
                raise ValueError('invalid dictionary key')
            path = prefix + (key.decode('ascii').strip('"'),)
            if path in self.entries or path in self.blocks:
                raise ValueError(f'duplicate dictionary path: {path}')
            index += 1
            if index >= len(self.tokens):
                raise ValueError('missing dictionary value')
            if self.tokens[index][0] == b'{':
                self.blocks.add(path)
                index = self._parse(index + 1, path, True)
                if index < len(self.tokens) and self.tokens[index][0] == b';':
                    index += 1
                continue
            start = self.tokens[index][1]
            values = []
            stack = []
            while index < len(self.tokens):
                token, _, token_end = self.tokens[index]
                if token == b';' and not stack:
                    break
                if token in (b'(', b'['):
                    stack.append(token)
                elif token in (b')', b']'):
                    if not stack or stack.pop() != {b')': b'(', b']': b'['}[token]:
                        raise ValueError('unbalanced list')
                elif token in (b'{', b'}'):
                    raise ValueError('nonliteral dictionary value')
                values.append(token)
                index += 1
            if index >= len(self.tokens) or not values or stack:
                raise ValueError('unterminated dictionary value')
            self.entries[path] = Entry(start, self.tokens[index - 1][2], tuple(values))
            index += 1
        if nested:
            raise ValueError('missing closing brace')
        return index

    def get(self, *path):
        return self.entries[tuple(path)].tokens

    def scalar(self, *path):
        values = self.get(*path)
        if len(values) != 1:
            raise ValueError(f'not a scalar: {path}')
        return values[0].decode('ascii').strip('"')

    def edit(self, changes):
        edits = []
        for path, value in changes.items():
            entry = self.entries[tuple(path)]
            edits.append((entry.start, entry.end, str(value).encode('ascii')))
        data = self.data
        for start, end, value in sorted(edits, reverse=True):
            data = data[:start] + value + data[end:]
        FoamDict(data)
        return data


def add_entry(data,block,key,value):
    dictionary=FoamDict(data)
    path=tuple(block)+(key,)
    if path in dictionary.entries: return dictionary.edit({path:value})
    if tuple(block) not in dictionary.blocks: raise ValueError('dictionary block missing')
    # Locate the exact block using parser token offsets, not text replacement.
    stack=[]
    for i,(token,start,end) in enumerate(dictionary.tokens):
        if token==b'{':
            stack.append(dictionary.tokens[i-1][0].decode('ascii').strip('"'))
            if tuple(stack)==tuple(block):
                result=data[:end]+b'\n        '+key.encode()+b' '+str(value).encode('ascii')+b';'+data[end:]
                FoamDict(result)
                return result
        elif token==b'}': stack.pop()
    raise ValueError('block not found')


def velocity_boundary(data):
    marker = b'boundaryField'
    # No numeric parsing or decoding of an opaque binary internalField.
    matches = list(re.finditer(rb'(?m)^\s*boundaryField\s*\n?\s*\{', data))
    if len(matches) != 1:
        raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION', 'U: ambiguous boundaryField')
    start = matches[0].start()
    header_end = data.find(b'}') + 1
    try:
        header = FoamDict(data[:header_end])
        if header.scalar('FoamFile', 'class') != 'volVectorField' or header.scalar('FoamFile', 'object') != 'U':
            raise ValueError('U must be a volVectorField')
        if header.scalar('FoamFile', 'format') not in ('ascii', 'binary'):
            raise ValueError('unknown field encoding')
        boundary = FoamDict(data[start:])
        if boundary.blocks - {('boundaryField',)} and any(
            path[0] != 'boundaryField' for path in boundary.blocks
        ):
            raise ValueError('extra field dictionaries')
        return data[:start], boundary
    except (ValueError, KeyError, UnicodeError) as exc:
        raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION', f'U: {exc}') from exc


def inlet_vector(data, patch):
    prefix, boundary = velocity_boundary(data)
    try:
        if boundary.scalar('boundaryField', patch, 'type') != 'fixedValue':
            raise ValueError('only an explicitly declared fixedValue inlet is supported')
        values = boundary.get('boundaryField', patch, 'value')
        if len(values) != 6 or values[0:2] != (b'uniform', b'(') or values[-1] != b')':
            raise ValueError('inlet must have one uniform vector')
        return tuple(float(x) for x in values[2:5])
    except (ValueError, KeyError) as exc:
        raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION', f'U/{patch}: {exc}') from exc


def set_inlet(data, patch, vector):
    inlet_vector(data, patch)
    prefix, boundary = velocity_boundary(data)
    value = 'uniform (' + ' '.join(f'{x:.17g}' for x in vector) + ')'
    return prefix + boundary.edit({('boundaryField', patch, 'value'): value})
