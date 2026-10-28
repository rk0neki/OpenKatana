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
        '00 Full workflow.app.json': full_workflow(),
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


def full_workflow():
    """Every App in one graph. One Project ID feeds every OpenKatana node, so Studio, the edit,
    the 3D starter and the tool all work on the same project. Video, music and a photo are imported
    as project assets; the photo joins the edit as an extra media ID."""
    graph_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'openkatana/app/full-workflow'))
    def node(i, kind, title, pos, size, inputs, outputs, widgets):
        return {'id': i, 'type': kind, 'title': title, 'pos': pos, 'size': size, 'flags': {},
                'order': i-1, 'mode': 0, 'inputs': inputs, 'outputs': outputs,
                'properties': {'Node name for S&R': kind}, 'widgets_values': widgets}
    def inp(name, kind, link): return {'name': name, 'type': kind, 'link': link}
    def widget(name, kind, link): return {'name': name, 'type': kind, 'widget': {'name': name}, 'link': link}
    def out(name, kind, links): return {'name': name, 'type': kind, 'links': links}
    def preview(i, title, pos, link):
        return node(i, 'PreviewAny', title, pos, [440, 260], [inp('source', '*', link)], [out('STRING', 'STRING', None)], [])
    def imports(i, title, pos, images, video, audio, project, media_links, music_links):
        return node(i, 'OpenKatanaImportMedia', title, pos, [340, 260],
                    [inp('images', 'IMAGE', images), inp('video', 'VIDEO', video), inp('audio', 'AUDIO', audio),
                     widget('project_id', 'STRING', project)],
                    [out('media_id', 'STRING', media_links), out('music_asset_id', 'STRING', music_links),
                     out('result_json', 'STRING', None)], ['my-film', 24, 'review_pending'])
    def group(i, title, bounding, color):
        return {'id': i, 'title': title, 'bounding': bounding, 'color': color, 'font_size': 24, 'flags': {}}
    return {'id': graph_id, 'revision': 0, 'last_node_id': 14, 'last_link_id': 17,
        'nodes': [
            node(1, 'PrimitiveString', 'Project ID', [60, 160], [300, 90],
                 [{**widget('value', 'STRING', None), 'label': 'project_id'}],
                 [out('STRING', 'STRING', [1, 2, 3, 4, 5, 6, 17])], ['my-film']),
            node(2, 'OpenKatanaWorkspace', '1 · Open Studio', [420, 80], [360, 150], [widget('project_id', 'STRING', 1)],
                 [out('result_json', 'STRING', [7])], ['my-film', 'My film']),
            preview(3, 'Studio link · OpenKatana', [840, 80], 7),
            node(4, 'LoadVideo', '2 · Your video', [60, 460], [340, 360], [], [out('VIDEO', 'VIDEO', [8])], ['']),
            imports(5, '3 · Import video and music', [440, 460], None, 8, 14, 2, [9], [10]),
            node(6, 'OpenKatanaMakeEdit', '4 · Make your edit', [840, 460], [340, 420],
                 [inp('media_id', 'STRING', 9), inp('music_asset_id', 'STRING', 10), widget('project_id', 'STRING', 3),
                  widget('extra_media_ids', 'STRING', 16)],
                 [out('result_json', 'STRING', [11])],
                 ['my-film', 'ramp-freeze', 5, 1280, 720, 24, False, '[]']),
            node(7, 'OpenKatanaRenderVideo', '5 · Finished video', [1220, 460], [380, 420],
                 [inp('after', 'STRING', 11), widget('project_id', 'STRING', 4)],
                 [out('video', 'VIDEO', None), out('preview_frames', 'IMAGE', None), out('result_json', 'STRING', None)],
                 ['my-film', 16]),
            node(8, 'OpenKatanaScene', '6 · 3D starter', [1660, 460], [340, 300], [widget('project_id', 'STRING', 5)],
                 [out('result_json', 'STRING', [12])], ['my-film', 'product', 640, 360, 60, 30]),
            preview(9, '3D result · OpenKatana', [1660, 820], 12),
            node(10, 'OpenKatanaTool', '7 · Any of the 72 tools', [1340, 80], [340, 220],
                 [inp('after', 'STRING', None), widget('project_id', 'STRING', 6)],
                 [out('result_json', 'STRING', [13])], ['get_capabilities', 'my-film', '{}']),
            preview(11, 'Tool result · OpenKatana', [1720, 80], 13),
            node(12, 'LoadAudio', '2 · Your music', [60, 860], [340, 130], [], [out('AUDIO', 'AUDIO', [14])], ['', None, '']),
            node(13, 'LoadImage', '2 · Your photo', [60, 1030], [340, 400], [],
                 [out('IMAGE', 'IMAGE', [15]), out('MASK', 'MASK', None)], ['', 'image']),
            imports(14, '3 · Import your photo', [440, 1030], 15, None, None, 17, [16], None)],
        'links': [[1, 1, 0, 2, 0, 'STRING'], [2, 1, 0, 5, 3, 'STRING'], [3, 1, 0, 6, 2, 'STRING'],
                  [4, 1, 0, 7, 1, 'STRING'], [5, 1, 0, 8, 0, 'STRING'], [6, 1, 0, 10, 1, 'STRING'],
                  [7, 2, 0, 3, 0, 'STRING'], [8, 4, 0, 5, 1, 'VIDEO'], [9, 5, 0, 6, 0, 'STRING'],
                  [10, 5, 1, 6, 1, 'STRING'], [11, 6, 0, 7, 0, 'STRING'], [12, 8, 0, 9, 0, 'STRING'],
                  [13, 10, 0, 11, 0, 'STRING'], [14, 12, 0, 5, 2, 'AUDIO'], [15, 13, 0, 14, 0, 'IMAGE'],
                  [16, 14, 0, 6, 3, 'STRING'], [17, 1, 0, 14, 3, 'STRING']],
        'groups': [group(1, 'Your project and Studio (your agent works here)', [40, 20, 1260, 360], '#3f789e'),
                   group(2, 'Your media: video, music and photos', [40, 400, 760, 1080], '#8A8'),
                   group(3, 'Make the edit', [820, 400, 800, 500], '#88A'),
                   group(4, '3D starter', [1640, 400, 540, 720], '#a1309b'),
                   group(5, 'Every tool', [1320, 20, 860, 360], '#b58b2a')],
        'config': {}, 'version': .4,
        'extra': {'ds': {'scale': .65, 'offset': [0, 0]}, 'linearMode': True, 'linearData': {'inputs': [
            [graph_id+':1:value', 'value'], [graph_id+':2:name', 'name'], [graph_id+':4:file', 'file'],
            [graph_id+':12:audio', 'audio'], [graph_id+':13:image', 'image'], [graph_id+':5:rights', 'rights'],
            [graph_id+':6:preset', 'preset'], [graph_id+':6:seconds', 'seconds'],
            [graph_id+':6:replace_existing', 'replace_existing'], [graph_id+':8:template', 'template'],
            [graph_id+':10:tool', 'tool'], [graph_id+':10:arguments', 'arguments']], 'outputs': [7, 3, 9, 11]},
            'openkatana': {'description': 'Every App in one graph. One Project ID feeds every node: open Studio for your agent, import your video, music and a photo, build and render the edit, start a 3D scene and call any tool. Keep seconds within the video and music length. Bypass (Ctrl+B) the music or photo loader and its import if you do not use it. Model weights are separate.',
                          'local_only': True}}}
