"""Official MCP SDK stdio adapter; stdout contains only protocol messages."""
import asyncio
import base64
import inspect
import io
import json
import logging
import os
from pathlib import Path
from .agent_api import AgentAPI,TOOLS

def create_server(workspace):
    # Load the numerical DLLs before stdio starts its blocking reader threads.
    # On Windows, their first import from a tool worker can otherwise stall.
    from . import audio
    try:   # OpenCV (analyze_energy, analyze_clip) too: imported lazily inside a tool worker it stalls the call
        import cv2  # noqa: F401
    except ImportError:
        pass
    from mcp.server.fastmcp import FastMCP
    from mcp.types import CallToolResult,TextContent,ImageContent,AudioContent,ToolAnnotations
    api=AgentAPI(workspace);lock=asyncio.Lock()
    server=FastMCP('OpenKatana',instructions=(
        'You are the editor. Read get_capabilities and read_guide before authoring. Inspect source images, '
        'choose shots and write a full timeline using OpenKatana. Preview actual frames, then '
        'start_render with a stable request_id and poll '
        'get_render. Review the rendered result. Do not claim human approval or publish. '
        'No automatic cloud fallback. Model downloads, paid jobs and uploads need applicable user authorization.'),log_level='WARNING')
    if os.environ.get('OPENKATANA_MCP_TRACE')=='1':
        logging.getLogger('openkatana.mcp').setLevel(logging.DEBUG)
    readers={'get_capabilities','read_guide','get_project','inspect_media','view_image','validate_timeline','get_render','check_workflow','list_fonts','audit_reference_plan','inspect_model3d','check_scene3d'}
    def wrap(method):
        async def invoke(**kwargs):
            logging.getLogger('openkatana.mcp').debug('Starting %s',method.__name__)
            # The SDK client temporarily changes its endpoint environment. One
            # dispatch lock avoids concurrent clients selecting each other's URL.
            async with lock:
                result=await asyncio.to_thread(method,**kwargs)
            logging.getLogger('openkatana.mcp').debug('Completed %s',method.__name__)
            content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False))]
            for filename in result.get('preview_images',[])[:4]:
                from PIL import Image
                with Image.open(filename) as im:
                    im=im.convert('RGB');im.thumbnail((1024,768));buffer=io.BytesIO();im.save(buffer,format='JPEG',quality=90)
                content.append(ImageContent(type='image',data=base64.b64encode(buffer.getvalue()).decode('ascii'),mimeType='image/jpeg'))
            for filename in result.get('preview_audio',[])[:1]:
                content.append(AudioContent(type='audio',data=base64.b64encode(Path(filename).read_bytes()).decode('ascii'),mimeType='audio/wav'))
            return CallToolResult(content=content,structuredContent=result)
        signature=inspect.signature(method).replace(return_annotation=CallToolResult)
        invoke.__signature__=signature
        invoke.__annotations__={name:p.annotation for name,p in signature.parameters.items()}
        invoke.__annotations__['return']=CallToolResult
        invoke.__name__=method.__name__;invoke.__doc__=method.__doc__
        return invoke
    from pydantic import ConfigDict
    for name in TOOLS:
        tool=server.add_tool(wrap(getattr(api,name)),name=name,structured_output=False,
            annotations=ToolAnnotations(readOnlyHint=name in readers,destructiveHint=False,
                idempotentHint=name in readers or name in ('start_render','collect_workflow','submit_workflow'),openWorldHint=name in ('submit_workflow','collect_workflow','import_workflow_output')))
        # Unknown arguments are errors, as on the CLI (the SDK's argument model would otherwise drop them silently).
        registered=server._tool_manager.get_tool(name);base=registered.fn_metadata.arg_model
        registered.fn_metadata.arg_model=type(base.__name__,(base,),{'model_config':ConfigDict(**base.model_config,extra='forbid')})
        registered.parameters['additionalProperties']=False
    @server.resource('openkatana://guide/{topic}')
    def guide(topic:str)->str:return api.read_guide(topic)['markdown']
    return server

def serve(workspace):create_server(workspace).run(transport='stdio')
