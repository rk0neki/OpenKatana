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
            ['job_id'], [''], 'Read job status; never automatically repeat a submission.')}
