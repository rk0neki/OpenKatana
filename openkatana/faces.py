"""Validate supplied face coordinates; no detection or identity processing."""
import json
from .contracts import ContractError, fields, number, local_path


def coordinates(value, count, where):
    if not isinstance(value,list) or len(value)!=count:raise ContractError(f'{where}: expected {count} coordinates')
    for v in value:number(v,where)


def shot_face(value):
    if value is False:return
    fields(value,'box','shot.face')
    coordinates(value.get('box'),4,'shot.face.box')
    x0,y0,x1,y1=value['box']
    if x1<=x0 or y1<=y0:raise ContractError('shot.face.box requires positive width and height')


def read_track(root, clip):
    path=local_path(root,clip['faces'])
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise ContractError('Cannot read face track JSON') from e
    if not isinstance(data,list) or len(data)!=clip['n']:raise ContractError('Face track requires one entry per source frame')
    for i,row in enumerate(data):
        if row is None:continue
        fields(row,'f box eyes nose mouth score src detector eyes_src','face track entry')
        if row.get('f')!=i:raise ContractError('Face track frame index must match source frame')
        number(row['f'],'face frame',0,clip['n']-1,integer=True)
        if row.get('box') is None:
            if row.get('eyes') is not None:raise ContractError('Face eyes require a box')
            continue
        coordinates(row['box'],4,'face box')
        if row['box'][2]<=0 or row['box'][3]<=0:raise ContractError('Face box width and height must be positive')
        for key in ('eyes','mouth'):
            if row.get(key) is not None:
                if not isinstance(row[key],list) or len(row[key])!=2:raise ContractError(f'{key} requires two points')
                for point in row[key]:coordinates(point,2,key)
        if row.get('nose') is not None:coordinates(row['nose'],2,'nose')
        if row.get('score') is not None:number(row['score'],'face score',0,1)
        if row.get('src') is not None and row['src'] not in ('det','track','interp','hold','none'):raise ContractError('Unknown face source')
        # provenance written by analyze_clip faces (which detector found the box; how the eyes were obtained)
        if row.get('detector') is not None and (not isinstance(row['detector'],str) or len(row['detector'])>32):raise ContractError('face detector: a short name')
        if row.get('eyes_src') is not None and row['eyes_src'] not in ('det','track','estimate'):raise ContractError('Unknown face eyes_src')
    return data
