"""Validate public Comfy node contracts, including V3 flattened dynamic ports."""
import math


def expanded_inputs(spec, inputs):
    rules, required, errors = {}, set(), []

    def expand(groups, prefix=''):
        for group in ('required', 'optional'):
            for key, rule in groups.get(group, {}).items():
                name=prefix+key;typ=rule[0];options=rule[1] if len(rule)>1 else {}
                if typ=='COMFY_AUTOGROW_V3':
                    template=options.get('template',{});matched=[]
                    for field in inputs:
                        if not field.startswith(name+'.'):continue
                        suffix=field[len(name)+1:]
                        names=template.get('names',[]);stem=template.get('prefix','')
                        valid=suffix in names if names else bool(stem and suffix.startswith(stem) and suffix[len(stem):].isdigit() and int(suffix[len(stem):])<template.get('max',1000))
                        if not valid:errors.append(f'{field}: invalid reference port');continue
                        nested=template.get('input',{}).get('required',{})
                        if len(nested)==1:rules[field]=next(iter(nested.values()));matched.append(field)
                    if len(matched)<template.get('min',0):errors.append(f'{name}: too few references')
                    continue
                rules[name]=rule
                if group=='required':required.add(name)
                if typ=='COMFY_DYNAMICCOMBO_V3':
                    selected=inputs.get(name)
                    choices=options.get('options',[])
                    chosen=next((v for v in choices if v['key']==selected),None)
                    if chosen:expand(chosen.get('inputs',{}),name+'.')
    expand(spec.get('input',{}))
    return rules,required,errors


def check_graph(graph, info, asset_inputs):
    errors=[]
    for node_id,node in graph.items():
        name=node['class_type'];spec=info.get(name)
        if not spec:continue
        inputs=node['inputs'];rules,required,issues=expanded_inputs(spec,inputs)
        errors.extend(f'{node_id}.{e}' for e in issues)
        for key in inputs.keys()-rules.keys():errors.append(f'{node_id}.{key}: unknown input')
        for key in required-inputs.keys():errors.append(f'{node_id}.{key}: missing required input')
        for key,value in inputs.items():
            if key not in rules:continue
            rule=rules[key];typ=rule[0];opts=rule[1] if len(rule)>1 else {}
            linked=isinstance(value,list) and len(value)==2 and str(value[0]) in graph
            if linked:
                upstream=info.get(graph[str(value[0])]['class_type'],{})
                outputs=upstream.get('output')
                if outputs is not None:
                    index=value[1]
                    if type(index) is not int or not 0<=index<len(outputs):errors.append(f'{node_id}.{key}: invalid output index');continue
                    actual=outputs[index]
                    if isinstance(typ,str) and isinstance(actual,str) and typ not in ('*','COMBO') and actual!='*' and not set(typ.split(',')).intersection(actual.split(',')) and not (typ=='FLOAT' and actual=='INT'):
                        errors.append(f'{node_id}.{key}: {actual} output cannot feed {typ}')
                continue
            if (name,key) in asset_inputs:continue
            if typ in ('INT','FLOAT'):
                types=(int,) if typ=='INT' else (int,float)
                if type(value) not in types or not math.isfinite(value) or value<opts.get('min',-math.inf) or value>opts.get('max',math.inf):
                    errors.append(f'{node_id}.{key}: invalid numeric value')
            elif typ=='BOOLEAN' and type(value) is not bool:errors.append(f'{node_id}.{key}: expected boolean')
            elif typ=='STRING' and not isinstance(value,str):errors.append(f'{node_id}.{key}: expected string')
            elif typ=='COMFY_DYNAMICCOMBO_V3' and value not in [x['key'] for x in opts.get('options',[])]:errors.append(f'{node_id}.{key}: invalid dynamic choice')
    # A malformed cyclic graph must fail locally rather than waiting for GPU execution.
    visited=set();active=set()
    def visit(key):
        if key in active:raise ValueError('Workflow contains a dependency cycle')
        if key in visited:return
        active.add(key)
        for v in graph[key]['inputs'].values():
            if isinstance(v,list) and len(v)==2 and str(v[0]) in graph:visit(str(v[0]))
        active.remove(key);visited.add(key)
    try:
        for key in graph:visit(key)
    except (ValueError,RecursionError):errors.append('Workflow contains a dependency cycle or excessive depth')
    return errors
