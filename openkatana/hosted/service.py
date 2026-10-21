import asyncio
import json
import uuid
from pathlib import Path
from .dispatch import validate_call, MODEL_TOOLS
from .files import inventory, safe_path
from .store import Store


class Service:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings)

    def submit(self, user, tool, arguments, request_id=None):
        validate_call(tool, arguments)
        arguments = dict(arguments)
        if tool in MODEL_TOOLS:
            if arguments.get('execution', 'local') == 'cloud':
                # Cloud credentials belong in a separately configured model
                # broker. They are never copied into authored-code workers.
                raise ValueError('Paid cloud execution is not enabled on this host. Use the configured private Comfy model service.')
            if not self.settings.comfy_proxy:
                raise ValueError('This tool needs the operator to configure a Comfy model service and installed models')
            proxy, native, _ = self.settings.models_for(user)
            if tool in ('submit_workflow', 'run_model_workflow'):
                arguments['endpoint'] = proxy
            if tool in ('submit_workflow', 'run_model_workflow', 'check_workflow'):
                arguments['native_endpoint'] = native
        inventory(self.store.workspace(user), self.settings.workspace_bytes)
        return self.store.submit(user, tool, arguments, request_id or uuid.uuid4().hex)

    async def wait(self, user, key, seconds=1):
        import time
        end = time.monotonic() + seconds
        while True:
            job = self.store.job(user, key)
            if job['state'] not in ('queued', 'running') or time.monotonic() >= end:
                return job
            await asyncio.sleep(.1)

    def project(self, user):
        project = self.store.selected(user)
        if not project:
            raise ValueError('Choose or create a project first')
        return project, self.store.workspace(user) / project

    def file_url(self, path):
        from urllib.parse import quote
        if isinstance(path, str) and path.startswith('workspace://'):
            return '/files/' + quote(path[len('workspace://'):], safe='/')
        return None
