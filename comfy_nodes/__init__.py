"""OpenKatana local nodes and Apps. Install with scripts/install_comfy_nodes.py.

The original tensor helpers use Comfy's environment. Full editor tools run in
OpenKatana's separate interpreter and share projects with Studio/CLI/MCP.
"""
import json
import re

import numpy as np
import torch


class OpenKatanaMatte:
    DESCRIPTION = 'Create a soft foreground MASK from a chroma-key color. Uses ComfyUI tensors; no model download.'
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),'key':('STRING',{'default':'#00ff00'}),
        'tolerance':('FLOAT',{'default':.18,'min':0,'max':1}),'softness':('FLOAT',{'default':.08,'min':.0001,'max':1})}}
    RETURN_TYPES=('MASK',)
    FUNCTION='execute'
    CATEGORY='OpenKatana/Image'
    def execute(self,image,key,tolerance,softness):
        if not isinstance(key, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', key):
            raise ValueError('key: expected a six-digit RGB color such as #00ff00')
        rgb=torch.tensor([int(key[i:i+2],16)/255 for i in (1,3,5)],device=image.device,dtype=image.dtype)
        mask=((torch.linalg.vector_norm(image[:,:,:,:3]-rgb,dim=-1)/(3**.5)-tolerance)/softness).clamp(0,1)
        return (mask,)

class OpenKatanaInterpolate:
    DESCRIPTION = 'Interpolate an IMAGE frame batch using optical flow in the separate OpenKatana vision environment.'
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'multiplier':('INT',{'default':2,'min':2,'max':8})}}
    RETURN_TYPES=('IMAGE',)
    FUNCTION='execute'
    CATEGORY='OpenKatana/Image'
    def execute(self,images,multiplier):
        from .media import interpolate_images
        return (interpolate_images(images, multiplier),)

class OpenKatanaPoints:
    """Click points in 0..1 frame coordinates -> pixel coordinate strings for point-prompted segmenters.
    positive/negative: JSON lists of [x, y]; the frame size comes from the connected image batch."""
    DESCRIPTION = 'Convert normalized positive/negative points into pixel-coordinate JSON for a connected image.'
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),'positive':('STRING',{'default':'[[0.5, 0.5]]'}),
        'negative':('STRING',{'default':'[]'})}}
    RETURN_TYPES=('STRING','STRING')
    RETURN_NAMES=('positive_coordinates','negative_coordinates')
    FUNCTION='execute'
    CATEGORY='OpenKatana/Image'
    @staticmethod
    def parse(text,name,required):
        try:points=json.loads(text or '[]')
        except ValueError as e:raise ValueError(f'{name}: expected a JSON list of [x, y] points') from e
        if not isinstance(points,list) or (required and not points):raise ValueError(f'{name}: expected at least one [x, y] point' if required else f'{name}: expected a list')
        for p in points:
            if not (isinstance(p,list) and len(p)==2 and all(isinstance(v,(int,float)) and 0<=v<=1 for v in p)):
                raise ValueError(f'{name}: each point is [x, y] with both values in 0..1, got {p!r}')
        return points
    def execute(self,image,positive,negative):
        _,h,w,_=image.shape
        def pixels(points):return json.dumps([{'x':round(x*(w-1)),'y':round(y*(h-1))} for x,y in points])
        return (pixels(self.parse(positive,'positive',True)),pixels(self.parse(negative,'negative',False)))

NODE_CLASS_MAPPINGS={'OpenKatanaMatte':OpenKatanaMatte,'OpenKatanaInterpolate':OpenKatanaInterpolate,'OpenKatanaPoints':OpenKatanaPoints}
NODE_DISPLAY_NAME_MAPPINGS={'OpenKatanaMatte':'OpenKatana · Chroma matte','OpenKatanaInterpolate':'OpenKatana · Optical flow',
                            'OpenKatanaPoints':'OpenKatana · Click points'}

from . import bridge
NODE_CLASS_MAPPINGS.update(bridge.NODE_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(bridge.NODE_DISPLAY_NAME_MAPPINGS)
from . import media
NODE_CLASS_MAPPINGS.update(media.NODE_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(media.NODE_DISPLAY_NAME_MAPPINGS)
WEB_DIRECTORY = './web'
try:
    from server import PromptServer
    if getattr(PromptServer, 'instance', None) is not None:
        bridge.register_routes()
except ImportError:
    pass  # standalone node tests have no running Comfy server
