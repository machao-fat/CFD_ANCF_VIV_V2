"""Fixed N5 topology inherited from successful NM12 implicit XML."""
import copy
import re
import xml.etree.ElementTree as ET
from .errors import GenerationError

PREFIXES=('data','mapping','m2n','coupling-scheme','acceleration')
for prefix in PREFIXES:
    ET.register_namespace(prefix,f'urn:precice:{prefix}')


def parse_production_xml(data):
    if isinstance(data,bytes): data=data.decode('utf-8')
    if '<!DOCTYPE' in data or '<!ENTITY' in data:
        raise GenerationError('UNSUPPORTED_PRODUCTION_XML','entities are prohibited')
    # preCICE's historical XML accepts colon names without xmlns declarations.
    # Add lexical namespace declarations for standard XML parsing only.
    if 'xmlns:' not in data:
        marker='<precice-configuration>'
        if data.count(marker)!=1:
            raise GenerationError('UNSUPPORTED_PRODUCTION_XML','expected one configuration root')
        declaration=' '.join(f'xmlns:{p}="urn:precice:{p}"' for p in PREFIXES)
        data=data.replace(marker,f'<precice-configuration {declaration}>',1)
    return ET.fromstring(data)


def semantic_identity(root,mask_mutable=False):
    def node(n):
        attrs=dict(n.attrib)
        if mask_mutable and n.tag=='max-time-windows': attrs['value']='<horizon>'
        if mask_mutable and n.tag=='{urn:precice:m2n}sockets': attrs['exchange-directory']='<case-local>'
        return [n.tag,sorted(attrs.items()),(n.text or '').strip(),[node(c) for c in n]]
    return node(root)


class V2606ImplicitTopologyBuilder:
    def __init__(self,template):
        self.root=parse_production_xml(template)
        self.check_topology(self.root)

    @staticmethod
    def check_topology(root):
        names=[p.get('name') for p in root.findall('participant')]
        expected=[f'Fluid-S{i}' for i in range(1,6)]+['Structure']
        if names!=expected or len(set(names))!=6:
            raise GenerationError('INVALID_PRODUCTION_TOPOLOGY','requires Fluid-S1..S5 and Structure')
        scheme=root.find('{urn:precice:coupling-scheme}multi')
        if scheme is None or len([n for n in root if 'coupling-scheme}' in n.tag])!=1:
            raise GenerationError('INVALID_PRODUCTION_TOPOLOGY','one implicit multi scheme required')
        if scheme.find('time-window-size').get('value')!='0.0004':
            raise GenerationError('INVALID_PRODUCTION_TOPOLOGY','fixed dt/window 0.0004')
        if scheme.find('{urn:precice:acceleration}IQN-ILS') is None or len(scheme.findall('exchange'))!=10:
            raise GenerationError('INVALID_PRODUCTION_TOPOLOGY','production IQN-ILS/exchanges required')
        return names

    def build(self,windows):
        if isinstance(windows,bool) or not isinstance(windows,int) or windows<1:
            raise GenerationError('INVALID_COUPLED_DURATION','positive integral time-window count required')
        root=copy.deepcopy(self.root)
        root.find('{urn:precice:coupling-scheme}multi/max-time-windows').set('value',str(windows))
        for n in root.findall('{urn:precice:m2n}sockets'):
            n.set('exchange-directory','..')
        if semantic_identity(root,True)!=semantic_identity(self.root,True):
            raise GenerationError('IMPLICIT_SEMANTICS_CHANGED','only horizon/socket path may change')
        ET.indent(root,space='  ')
        return ET.tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'

    def validate(self,generated,windows):
        root=parse_production_xml(generated)
        self.check_topology(root)
        if semantic_identity(root,False)!=semantic_identity(parse_production_xml(self.build(windows)),False):
            raise GenerationError('IMPLICIT_SEMANTICS_CHANGED','generated XML differs outside whitelist or has wrong horizon/path')
        return root
