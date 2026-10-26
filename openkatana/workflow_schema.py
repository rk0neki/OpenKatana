"""Validate public Comfy node contracts, including V3 flattened dynamic ports and MatchType links."""
import math

MATCHTYPE='COMFY_MATCHTYPE_V3'


def expanded_inputs(spec, inputs):
    rules, required, errors = {}, set(), []

    def expand(groups, prefix=''):
        for group in ('required', 'optional'):
            for key, rule in groups.get(group, {}).items():
                name=prefix+key;typ=rule[0];options=rule[1] if len(rule)>1 else {}
                if typ=='COMFY_AUTOGROW_V3':
                    template=options.get('template',{});matched=[]
                    # The template's one input may be listed as required or optional
                    # (core ReferenceMultiLatent lists it as optional).
                    port=template.get('input',{});nested={**port.get('optional',{}),**port.get('required',{})}
                    for field in inputs:
                        if not field.startswith(name+'.'):continue
                        suffix=field[len(name)+1:]
                        names=template.get('names',[]);stem=template.get('prefix','')
                        valid=suffix in names if names else bool(stem and suffix.startswith(stem) and suffix[len(stem):].isdigit() and int(suffix[len(stem):])<template.get('max',1000))
                        if not valid:errors.append(f'{field}: invalid reference port');continue
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


def common_type(*types):
    """Type shared by all given types, as Comfy's editor resolves MatchType sockets: '*' matches anything,
    comma-separated lists intersect, and None means nothing is shared."""
    named=[t.split(',') for t in types if t!='*']
    if not named:return '*'
    shared=[t for t in dict.fromkeys(named[0]) if all(t in other for other in named[1:])]
    return ','.join(shared) or None


def matchtype_template(rule):
    """(template_id, allowed_types) of a MatchType input. As in Comfy's editor, a malformed template is a plain wildcard."""
    template=rule[1].get('template') if len(rule)>1 and isinstance(rule[1],dict) else None
    if isinstance(template,dict) and isinstance(template.get('template_id'),str) and isinstance(template.get('allowed_types'),str):
        return template['template_id'],template['allowed_types']
    return None,'*'


def check_graph(graph, info, asset_inputs):
    errors=[]
    expanded={node_id:expanded_inputs(info[node['class_type']],node['inputs']) for node_id,node in graph.items() if info.get(node['class_type'])}
    resolved={};resolving=set()

    def is_link(value):return isinstance(value,list) and len(value)==2 and str(value[0]) in graph

    def template_links(node_id,template):
        """(input, link, allowed types) for each linked MatchType input of a node in the given template."""
        links=[]
        if template is None or node_id not in expanded:return links
        for key,rule in expanded[node_id][0].items():
            value=graph[node_id]['inputs'].get(key)
            if rule[0]!=MATCHTYPE or not is_link(value):continue
            template_id,allowed=matchtype_template(rule)
            if template_id==template:links.append((key,value,allowed))
        return links

    def link_type(value):
        """Type a link carries, or '*' when it cannot be decided. A MatchType output carries the common type of the
        concrete types linked into its template, each limited to what its own input allows."""
        source,index=str(value[0]),value[1];spec=info.get(graph[source]['class_type'],{})
        outputs=spec.get('output') or []
        if type(index) is not int or not 0<=index<len(outputs):return '*'
        if outputs[index]!=MATCHTYPE:return outputs[index] if isinstance(outputs[index],str) else '*'
        port=(source,index)
        if port in resolving:return '*'  # a cycle, reported below
        if port not in resolved:
            templates=spec.get('output_matchtypes')
            template=templates[index] if isinstance(templates,list) and index<len(templates) else None
            resolving.add(port)
            try:
                parts=[]
                for _,link,allowed in template_links(source,template):
                    carried=link_type(link)
                    if carried!='*':parts.append(common_type(carried,allowed))
                resolved[port]='*' if None in parts else (common_type(*parts) or '*')
            except RecursionError:resolved[port]='*'  # too deep to decide
            finally:resolving.discard(port)
        return resolved[port]

    for node_id,node in graph.items():
        if node_id not in expanded:continue
        name=node['class_type'];inputs=node['inputs'];rules,required,issues=expanded[node_id]
        errors.extend(f'{node_id}.{e}' for e in issues)
        for key in inputs.keys()-rules.keys():errors.append(f'{node_id}.{key}: unknown input')
        for key in required-inputs.keys():errors.append(f'{node_id}.{key}: missing required input')
        for key,value in inputs.items():
            if key not in rules:continue
            rule=rules[key];typ=rule[0];opts=rule[1] if len(rule)>1 else {}
            if is_link(value):
                upstream=info.get(graph[str(value[0])]['class_type'],{})
                outputs=upstream.get('output')
                if outputs is not None:
                    index=value[1]
                    if type(index) is not int or not 0<=index<len(outputs):errors.append(f'{node_id}.{key}: invalid output index');continue
                    actual=link_type(value);wanted=typ
                    if typ==MATCHTYPE:
                        # Comfy's editor accepts what the template allows that also matches the template's other links.
                        template,allowed=matchtype_template(rule)
                        wanted=common_type(allowed,*(link_type(link) for other,link,_ in template_links(node_id,template) if other!=key)) or allowed
                    if isinstance(wanted,str) and isinstance(actual,str) and wanted not in ('*','COMBO') and actual!='*' and not set(wanted.split(',')).intersection(actual.split(',')) and not (wanted=='FLOAT' and actual=='INT'):
                        errors.append(f'{node_id}.{key}: {actual} output cannot feed {wanted}')
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
