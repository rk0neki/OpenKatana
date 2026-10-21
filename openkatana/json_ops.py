"""Original RFC 6901/6902 document operations. Apply a whole batch or change nothing."""
import copy
import json
import re
from .contracts import ContractError, fields


def tokens(path):
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise ContractError('JSON Pointer must be empty or start with /')
    if re.search(r'~(?![01])', path): raise ContractError('Invalid JSON Pointer escape')
    return [s.replace('~1','/').replace('~0','~') for s in path[1:].split('/')] if path else []


def index(token, length, add=False):
    if add and token=='-': return length
    if not re.fullmatch('0|[1-9][0-9]*',token): raise ContractError('Invalid array index')
    i=int(token)
    if i > length if add else i >= length: raise ContractError('Array index outside document')
    return i


def read(value, path):
    for part in path:
        if isinstance(value,list): value=value[index(part,len(value))]
        elif isinstance(value,dict) and part in value: value=value[part]
        else: raise ContractError('JSON Pointer target is missing')
    return value


def write(doc, path, value=None, remove=False, replace=False):
    if not path:
        if remove: raise ContractError('Removing the whole document is not supported')
        return copy.deepcopy(value)
    parent=read(doc,path[:-1]); key=path[-1]
    if isinstance(parent,list):
        i=index(key,len(parent),add=not remove and not replace)
        if remove: parent.pop(i)
        elif replace: parent[i]=copy.deepcopy(value)
        else: parent.insert(i,copy.deepcopy(value))
    elif isinstance(parent,dict):
        if (remove or replace) and key not in parent: raise ContractError('Operation target is missing')
        if remove: del parent[key]
        else: parent[key]=copy.deepcopy(value)
    else: raise ContractError('Operation parent must be an object or array')
    return doc


def apply(document, operations):
    if not isinstance(operations,list) or not 1 <= len(operations) <= 256:
        raise ContractError('Use 1..256 operations')
    try: json.dumps([document,operations],allow_nan=False)
    except (TypeError,ValueError) as e: raise ContractError('Operations require finite JSON values') from e
    result=copy.deepcopy(document)
    for n,op in enumerate(operations):
        if not isinstance(op,dict): raise ContractError(f'Operation {n} must be an object')
        kind=op.get('op'); allowed={'add':'value','replace':'value','remove':'','test':'value','copy':'from','move':'from'}
        if kind not in allowed: raise ContractError(f'Unknown operation: {kind}')
        fields(op,'op path '+allowed[kind],f'operation {n}')
        if 'path' not in op or (allowed[kind] and allowed[kind] not in op): raise ContractError('Missing operation argument')
        path=tokens(op['path'])
        if kind=='test':
            # JSON booleans must not compare equal to numbers (Python True == 1).
            def eq(a,b):
                if type(a) is bool or type(b) is bool: return type(a) is type(b) and a==b
                if isinstance(a,dict) and isinstance(b,dict): return a.keys()==b.keys() and all(eq(a[k],b[k]) for k in a)
                if isinstance(a,list) and isinstance(b,list): return len(a)==len(b) and all(eq(x,y) for x,y in zip(a,b))
                return a==b
            if not eq(read(result,path),op['value']): raise ContractError(f'Operation {n} test failed')
        elif kind in ('copy','move'):
            source=tokens(op['from']); value=copy.deepcopy(read(result,source))
            if kind=='move':
                if path[:len(source)]==source and len(path)>len(source): raise ContractError('Cannot move a parent into its descendant')
                if source==path: continue
                result=write(result,source,remove=True)
            result=write(result,path,value)
        else: result=write(result,path,op.get('value'),remove=kind=='remove',replace=kind=='replace')
    return result
