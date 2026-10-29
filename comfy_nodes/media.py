"""Typed IMAGE/VIDEO ports. Expensive editor dependencies stay in the subprocess."""
from contextlib import contextmanager
from pathlib import Path
import json
import wave

import numpy as np
import torch

from . import bridge


@contextmanager
def transfer():
    import uuid
    root = Path(bridge.configuration()['workspace']) / '.comfy-apps' / 'transfers'
    root.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    folder = root / key
    folder.mkdir()
    try:
        yield key, folder
    finally:
        import shutil
        # Only the temporary directory created by this call is removed.
        shutil.rmtree(folder)


def save_images(images, path):
    if images.ndim != 4 or images.shape[-1] != 3 or min(images.shape) < 1:
        raise ValueError('Connect a nonempty RGB IMAGE batch; composite alpha before import')
    if images.numel() > 512 * 1024**2:
        raise ValueError('Frame batch exceeds 512 MiB as RGB8; use a shorter/smaller batch')
    if not torch.isfinite(images).all():
        raise ValueError('Image batch contains non-finite values')
    np.save(path, images.detach().cpu().clamp(0, 1).mul(255).round().to(torch.uint8).numpy(), allow_pickle=False)


def interpolate_images(images, multiplier):
    with transfer() as (key, folder):
        save_images(images, folder / 'input.npy')
        bridge.invoke('interpolate_frames', transfer_id=key, multiplier=multiplier)
        value = np.load(folder / 'output.npy', allow_pickle=False)
        return torch.from_numpy(value.astype('float32') / 255)


def save_audio(audio, path):
    samples = audio['waveform'].detach().cpu()
    if samples.ndim != 3 or samples.shape[0] != 1 or samples.shape[1] not in (1, 2):
        raise ValueError('AUDIO must contain one mono or stereo waveform')
    rate = int(audio['sample_rate'])
    if not 8000 <= rate <= 192000 or not torch.isfinite(samples).all():
        raise ValueError('Invalid AUDIO samples/sample rate')
    data = samples[0].T.clamp(-1, 1).mul(32767).to(torch.int16).numpy().astype('<i2')
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(samples.shape[1]); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes(data.tobytes())


def input_choices(kind):
    """Files of one kind in ComfyUI's input folder; the first choice, '', means none."""
    import os
    import folder_paths
    root = folder_paths.get_input_directory()
    files = [f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))]
    return [''] + sorted(folder_paths.filter_files_content_types(files, [kind]))


def check_choice(name):
    import folder_paths
    return True if not name or folder_paths.exists_annotated_filepath(name) else f'File not found in input: {name}'


def skipped(message, outputs):
    """A clear result instead of an error when the user chose no media."""
    output = bridge.response({'state': 'skipped', 'message': message})
    output['result'] = (*outputs, output['result'][0])
    return output


class OpenKatanaVideoFile:
    DESCRIPTION = 'Choose or upload a video, or leave it empty; an empty slot skips the media steps instead of failing.'
    CATEGORY = 'OpenKatana/Media'
    RETURN_TYPES = ('VIDEO',)
    RETURN_NAMES = ('video',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'video': (input_choices('video'), {'video_upload': True})}}

    @classmethod
    def VALIDATE_INPUTS(cls, video):
        return check_choice(video)

    def load(self, video):
        if not video:
            return (None,)
        import folder_paths
        from comfy_api.latest import InputImpl
        return (InputImpl.VideoFromFile(folder_paths.get_annotated_filepath(video)),)


class OpenKatanaAudioFile:
    DESCRIPTION = 'Choose or upload music, or leave it empty to use the video\'s own sound.'
    CATEGORY = 'OpenKatana/Media'
    RETURN_TYPES = ('AUDIO',)
    RETURN_NAMES = ('audio',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        # Named music: ComfyUI's legacy upload helper wants LoadAudio's own player on an input named audio.
        return {'required': {'music': (input_choices('audio'), {'audio_upload': True})}}

    @classmethod
    def VALIDATE_INPUTS(cls, music):
        return check_choice(music)

    def load(self, music):
        if not music:
            return (None,)
        import folder_paths
        from comfy_extras.nodes_audio import load
        waveform, rate = load(folder_paths.get_annotated_filepath(music))
        return ({'waveform': waveform.unsqueeze(0), 'sample_rate': rate},)


class OpenKatanaImageFile:
    DESCRIPTION = 'Choose or upload a photo, or leave it empty to skip it.'
    CATEGORY = 'OpenKatana/Media'
    RETURN_TYPES = ('IMAGE',)
    RETURN_NAMES = ('image',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': (input_choices('image'), {'image_upload': True})}}

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        return check_choice(image)

    def load(self, image):
        if not image:
            return (None,)
        import folder_paths
        from PIL import Image, ImageOps
        with Image.open(folder_paths.get_annotated_filepath(image)) as im:
            rgb = ImageOps.exif_transpose(im).convert('RGB')
            return (torch.from_numpy(np.asarray(rgb, dtype=np.float32) / 255)[None],)


class OpenKatanaImportMedia(bridge.OpenKatanaTool):
    DESCRIPTION = ('Import model IMAGE frames or VIDEO into a shared project; preserve VIDEO audio or connect AUDIO. '
                   'Connect exactly one of images/video; with neither, the import is skipped. '
                   'The fps field applies to IMAGE batches only.')
    CATEGORY = 'OpenKatana/Media'
    RETURN_TYPES = ('STRING', 'STRING', 'STRING')
    RETURN_NAMES = ('media_id', 'music_asset_id', 'result_json')

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project_id': ('STRING', {'default': 'my-film'}),
            'fps': ('FLOAT', {'default': 24, 'min': 1, 'max': 120}),
            'rights': (['review_pending', 'own', 'licensed', 'public_domain'],)},
            'optional': {'images': ('IMAGE',), 'video': ('VIDEO',), 'audio': ('AUDIO',)}}

    def execute(self, project_id, fps, rights, images=None, video=None, audio=None):
        if images is None and video is None:  # an empty file slot upstream
            return skipped('No video or photo chosen; nothing imported.', ('', ''))
        if images is not None and video is not None:
            raise ValueError('Connect exactly one IMAGE or VIDEO source')
        with transfer() as (key, folder):
            if images is not None:
                save_images(images, folder / 'input.npy')
            else:
                from comfy_api.latest import Types
                video.save_to(str(folder / 'input.mp4'), format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264)
            if audio is not None:
                save_audio(audio, folder / 'input.wav')
            result = bridge.invoke('import_frames', transfer_id=key, project_id=project_id,
                                   fps=fps, rights=rights, video=video is not None)
        output = bridge.response(result)
        output['result'] = (result['media_id'], result['music_asset_id'], json.dumps(result))
        return output


class OpenKatanaMakeEdit(bridge.OpenKatanaTool):
    DESCRIPTION = ('Build and save an edit from a connected media ID; optional extra media IDs are a JSON list or one connected ID. '
                   'Choose beat-montage with music, or a silent preset. Existing timelines require replace_existing.')
    CATEGORY = 'OpenKatana/Media'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project_id': ('STRING', {'default': 'my-film'}),
            'media_id': ('STRING', {'forceInput': True}),
            'preset': (['ramp-freeze', 'travel-diary', 'beat-montage', 'split-collage', 'glitch-drop'],),
            'seconds': ('FLOAT', {'default': 6, 'min': .5, 'max': 600}),
            'width': ('INT', {'default': 1280, 'min': 64, 'max': 3840, 'step': 2}),
            'height': ('INT', {'default': 720, 'min': 64, 'max': 2160, 'step': 2}),
            'fps': ('FLOAT', {'default': 24, 'min': 1, 'max': 120}),
            'replace_existing': ('BOOLEAN', {'default': False})},
            'optional': {'music_asset_id': ('STRING', {'forceInput': True}),
                         'extra_media_ids': ('STRING', {'default': '[]'})}}

    def execute(self, project_id, media_id, preset, seconds, width, height, fps,
                replace_existing=False, music_asset_id='', extra_media_ids='[]'):
        text = extra_media_ids.strip()
        extra = json.loads(text) if text.startswith('[') else [text] if text else []  # a connected Import media ID
        if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
            raise ValueError('extra_media_ids must be a JSON list of media IDs or one media ID')
        assets = [x for x in (media_id, *extra) if x]  # imports with no chosen media pass ''
        if not assets:
            return skipped('No media imported; no edit made.', ())
        state = bridge.invoke('call', tool='get_project', arguments={'project_id': project_id})
        if state['timeline'] is not None and not replace_existing:
            raise ValueError('Project already has an edit; choose another project or enable replace_existing')
        result = bridge.invoke('call', tool='build_recipe', arguments={'project_id': project_id,
            'family': preset, 'asset_ids': assets, 'music_asset_id': music_asset_id or None,
            'seconds': seconds, 'width': width, 'height': height, 'fps': fps})
        saved = bridge.invoke('call', tool='save_timeline', arguments={'project_id': project_id,
            'timeline': result['timeline'], 'revision': state['revision']})
        return bridge.response({**result, **saved, 'project_id': project_id})


class OpenKatanaRenderVideo(bridge.OpenKatanaTool):
    DESCRIPTION = ('Render the saved timeline as a full VIDEO and an IMAGE preview batch. '
                   'Preview frames are bounded; VIDEO always contains the complete render and soundtrack.')
    CATEGORY = 'OpenKatana/Media'
    RETURN_TYPES = ('VIDEO', 'IMAGE', 'STRING')
    RETURN_NAMES = ('video', 'preview_frames', 'result_json')

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project_id': ('STRING', {'default': 'my-film'}),
            'preview_frames': ('INT', {'default': 16, 'min': 1, 'max': 256})},
            'optional': {'after': ('STRING', {'forceInput': True})}}

    def execute(self, project_id, preview_frames=16, after=None):
        if after and after.lstrip().startswith('{') and json.loads(after).get('state') == 'skipped':
            return skipped('No edit was made, so nothing was rendered.', (None, None))
        from comfy_api.latest import InputImpl
        from PIL import Image
        result = bridge.invoke('render_video', project_id=project_id)
        files = sorted(Path(result['frames_directory']).glob('*.png'))
        with Image.open(files[0]) as first:
            limit = max(1, min(preview_frames, 256 * 1024**2 // (first.width * first.height * 3 * 4)))
        indices = np.linspace(0, len(files)-1, min(limit, len(files))).astype(int)
        frames = []
        for i in indices:
            with Image.open(files[i]) as im:
                frames.append(np.asarray(im.convert('RGB'), dtype=np.float32) / 255)
        result['preview_frame_indices'] = indices.tolist()
        output = bridge.response(result)
        output['result'] = (InputImpl.VideoFromFile(result['video_path']), torch.from_numpy(np.stack(frames)), json.dumps(result))
        return output


NODE_CLASS_MAPPINGS = {'OpenKatanaImportMedia': OpenKatanaImportMedia,
    'OpenKatanaMakeEdit': OpenKatanaMakeEdit, 'OpenKatanaRenderVideo': OpenKatanaRenderVideo,
    'OpenKatanaVideoFile': OpenKatanaVideoFile, 'OpenKatanaAudioFile': OpenKatanaAudioFile,
    'OpenKatanaImageFile': OpenKatanaImageFile}
NODE_DISPLAY_NAME_MAPPINGS = {'OpenKatanaImportMedia': 'OpenKatana · Import media',
    'OpenKatanaMakeEdit': 'OpenKatana · Make edit', 'OpenKatanaRenderVideo': 'OpenKatana · Render to video',
    'OpenKatanaVideoFile': 'OpenKatana · Video file', 'OpenKatanaAudioFile': 'OpenKatana · Music file',
    'OpenKatanaImageFile': 'OpenKatana · Photo file'}
