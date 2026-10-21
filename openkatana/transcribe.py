"""Local speech transcription with word timings, for captions (make_captions takes the words file it writes).

Uses faster-whisper (MIT; optional extra `pip install -e ".[transcribe]"`) with Whisper models already present in the
local Hugging Face cache (for example Systran/faster-whisper-small). It never downloads: models load with
local_files_only and HF_HUB_OFFLINE set, and a missing model is reported with the installed ones listed.
Transcripts are machine output; words, spelling and timings must be checked against the audio.
"""
import os
import subprocess
import tempfile
from pathlib import Path

from .contracts import ContractError
from .render import digest, write_json

REPO = 'Systran/faster-whisper-'
PREFERENCE = ('small', 'small.en', 'base', 'base.en', 'medium', 'medium.en', 'large-v3', 'tiny', 'tiny.en')


def hub_cache():
    if os.environ.get('HF_HUB_CACHE'):
        return Path(os.environ['HF_HUB_CACHE'])
    home = Path(os.environ.get('HF_HOME') or Path.home() / '.cache' / 'huggingface')
    return home / 'hub'


def installed():
    """Whisper model names whose CTranslate2 files are complete in the local cache."""
    names = []
    for folder in sorted(hub_cache().glob('models--Systran--faster-whisper-*')):
        if any((snap / 'model.bin').is_file() and (snap / 'config.json').is_file() for snap in (folder / 'snapshots').glob('*')):
            names.append(folder.name.split('faster-whisper-', 1)[1])
    return names


def available():
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _audio(src, start, duration, target):
    args = ['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(src)]
    if duration is not None:
        args += ['-t', str(duration)]
    proc = subprocess.run(args + ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(target)], capture_output=True, text=True)
    if proc.returncode or not target.is_file() or target.stat().st_size <= 44:
        raise ContractError(f'{Path(src).name}: no decodable audio in the requested range ({proc.stderr.strip()[:200]})')


def transcribe(src, out, model=None, language=None, start=0, duration=None, device='auto'):
    """Write out/words.json ({"words": [{start, end, word, probability}], "segments": [...], ...}); times are seconds
    of the source file."""
    if not available():
        raise ContractError('Transcription needs the optional faster-whisper package: pip install -e ".[transcribe]" '
                            '(no models are downloaded by OpenKatana; use a Whisper model already in the local cache)')
    have = installed()
    if model is None:
        model = next((m for m in PREFERENCE if m in have), None)
        if model is None:
            raise ContractError(f'No faster-whisper model in the local cache ({hub_cache()}). OpenKatana does not download models')
    elif model not in have:
        raise ContractError(f'Whisper model {model!r} is not in the local cache; installed: {", ".join(have) or "none"}. '
                            'OpenKatana does not download models')
    if language is not None and (model.endswith('.en') and language != 'en'):
        raise ContractError(f'{model} is an English-only model; choose a multilingual model for language {language!r}')
    os.environ['HF_HUB_OFFLINE'] = '1'
    from faster_whisper import WhisperModel
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / 'audio.wav'
        _audio(src, start, duration, wav)
        tried = []
        for dev, compute in ([('cuda', 'float16'), ('cpu', 'int8')] if device == 'auto' else [(device, 'float16' if device == 'cuda' else 'int8')]):
            try:
                engine = WhisperModel(REPO + model, device=dev, compute_type=compute, local_files_only=True)
                segments, info = engine.transcribe(str(wav), language=language, word_timestamps=True, beam_size=5,
                                                   condition_on_previous_text=False)
                segments = list(segments)
                break
            except Exception as err:  # a missing CUDA runtime surfaces at load or first inference; fall back to CPU
                tried.append(f'{dev}: {err.__class__.__name__}: {str(err)[:160]}')
        else:
            raise ContractError('Transcription failed: ' + '; '.join(tried))
    words, segs = [], []
    for s in segments:
        segs.append({'start': round(s.start + start, 3), 'end': round(s.end + start, 3), 'text': s.text.strip()})
        for w in s.words or []:
            text = w.word.strip()
            if text:
                words.append({'start': round(w.start + start, 3), 'end': round(max(w.end, w.start) + start, 3), 'word': text,
                              'probability': round(w.probability, 3)})
    result = {'words': words, 'segments': segs, 'language': info.language, 'language_probability': round(info.language_probability, 3),
              'model': REPO + model, 'device': dev, 'source': str(src), 'source_sha256': digest(Path(src)),
              'range': {'start': start, 'duration': duration}, 'timing_basis': 'seconds of the source file',
              'review': 'machine transcript: check words, names and timings against the audio'}
    write_json(out / 'words.json', result)
    low = [w for w in words if w['probability'] < .5]
    return {'words_file': str(out / 'words.json'), 'text': ' '.join(s['text'] for s in segs), 'words': len(words),
            'segments': len(segs), 'language': result['language'], 'model': result['model'], 'device': dev,
            'low_confidence': [{'start': w['start'], 'word': w['word'], 'probability': w['probability']} for w in low[:40]],
            **({'fallback': tried} if tried else {}),
            'next': 'make_captions(words=words_file, offset=<audio start used in the timeline>) after checking the text'}
