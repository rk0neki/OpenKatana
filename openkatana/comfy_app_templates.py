"""Original App Mode graphs. ComfyUI frontend 1.55's public workflow format."""
import uuid


def app_workflow(name, node_type, fields, values, description):
    graph_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'openkatana/app/' + name))
    return {'id': graph_id, 'revision': 0, 'last_node_id': 2, 'last_link_id': 1,
        'nodes': [
            {'id': 1, 'type': node_type, 'title': name, 'pos': [80, 100], 'size': [430, 400],
             'flags': {}, 'order': 0, 'mode': 0, 'inputs': [],
             'outputs': [{'name': 'result_json', 'type': 'STRING', 'links': [1], 'slot_index': 0}],
             'properties': {'Node name for S&R': node_type}, 'widgets_values': values},
            {'id': 2, 'type': 'PreviewAny', 'title': 'Result · OpenKatana', 'pos': [580, 100],
             'size': [500, 400], 'flags': {}, 'order': 1, 'mode': 0,
             'inputs': [{'name': 'source', 'type': '*', 'link': 1}],
             'outputs': [{'name': 'STRING', 'type': 'STRING', 'links': None}],
             'properties': {'Node name for S&R': 'PreviewAny'}, 'widgets_values': []}],
        'links': [[1, 1, 0, 2, 0, 'STRING']], 'groups': [], 'config': {},
        'extra': {'ds': {'scale': 1, 'offset': [0, 0]}, 'linearMode': True,
            'linearData': {'inputs': [[graph_id + ':1:' + field, field] for field in fields],
                           'outputs': [1, 2]},
            'openkatana': {'description': description, 'local_only': True}}, 'version': 0.4}


def templates():
    return {
        '01 Open Studio.app.json': app_workflow('OpenKatana · Open Studio', 'OpenKatanaWorkspace',
            ['project_id', 'name'], ['my-film', 'My film'],
            'Create or reopen your project, then follow the Studio link. Your agent uses the same project through CLI/MCP.'),
        '02 All tools.app.json': app_workflow('OpenKatana · All tools', 'OpenKatanaTool',
            ['tool', 'project_id', 'arguments'], ['get_capabilities', 'my-film', '{}'],
            'All shared tools, using their documented JSON arguments. Begin with get_capabilities and read_guide.'),
        '03 Make a 3D scene.app.json': app_workflow('OpenKatana · Make a 3D scene', 'OpenKatanaScene',
            ['project_id', 'template', 'width', 'height', 'frames', 'fps'],
            ['my-film', 'product', 640, 360, 60, 30],
            'Render an editable WebGL product, morph or physics starter locally. No model or credits.'),
        '04 Background job.app.json': app_workflow('OpenKatana · Background job', 'OpenKatanaJob',
            ['job_id'], [''], 'Read job status; never automatically repeat a submission.'),
        '05 Video to edit.app.json': video_edit_workflow()}


def video_edit_workflow():
    """A typed graph: upload any generated video, then import/edit/render it."""
    graph_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'openkatana/app/video-to-edit'))
    def node(i, kind, title, inputs, outputs, widgets):
        return {'id': i, 'type': kind, 'title': title, 'pos': [60+390*(i-1), 100],
                'size': [340, 340], 'flags': {}, 'order': i-1, 'mode': 0,
                'inputs': inputs, 'outputs': outputs,
                'properties': {'Node name for S&R': kind}, 'widgets_values': widgets}
    def inp(name, kind, link): return {'name': name, 'type': kind, 'link': link}
    def out(name, kind, links): return {'name': name, 'type': kind, 'links': links}
    return {'id': graph_id, 'revision': 0, 'last_node_id': 4, 'last_link_id': 4,
        'nodes': [
            node(1, 'LoadVideo', '1 · Your generated video', [], [out('VIDEO', 'VIDEO', [1])], ['']),
            node(2, 'OpenKatanaImportMedia', '2 · Import into OpenKatana',
                 [inp('images', 'IMAGE', None), inp('video', 'VIDEO', 1), inp('audio', 'AUDIO', None)],
                 [out('media_id', 'STRING', [2]), out('music_asset_id', 'STRING', [3]), out('result_json', 'STRING', None)],
                 ['my-film', 24, 'review_pending']),
            node(3, 'OpenKatanaMakeEdit', '3 · Make your edit',
                 [inp('media_id', 'STRING', 2), inp('music_asset_id', 'STRING', 3)],
                 [out('result_json', 'STRING', [4])],
                 ['my-film', 'ramp-freeze', 6, 1280, 720, 24, False, '[]']),
            node(4, 'OpenKatanaRenderVideo', '4 · Finished video', [inp('after', 'STRING', 4)],
                 [out('video', 'VIDEO', None), out('preview_frames', 'IMAGE', None), out('result_json', 'STRING', None)],
                 ['my-film', 16])],
        'links': [[1,1,0,2,1,'VIDEO'], [2,2,0,3,0,'STRING'], [3,2,1,3,1,'STRING'], [4,3,0,4,0,'STRING']],
        'groups': [], 'config': {}, 'version': .4,
        'extra': {'linearMode': True, 'linearData': {'inputs': [
            [graph_id+':1:file','file'], [graph_id+':2:project_id','project_id'],
            [graph_id+':2:rights','rights'], [graph_id+':3:project_id','project_id'],
            [graph_id+':3:preset','preset'], [graph_id+':3:seconds','seconds'],
            [graph_id+':3:replace_existing','replace_existing'], [graph_id+':4:project_id','project_id']], 'outputs': [4]},
            'openkatana': {'description': 'Set all three project IDs alike. Upload a video or replace LoadVideo with a model VIDEO output. IMAGE batches connect to Import media images. Model weights are separate.',
                          'local_only': True}}}
