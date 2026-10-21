import argparse
import json
from pathlib import Path

from .config import Settings
from .store import Store


def main():
    parser = argparse.ArgumentParser(description='OpenKatana hosting control plane; deployment is explicit')
    parser.add_argument('--config', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    web = sub.add_parser('web'); web.add_argument('--port', type=int, default=8090)
    sub.add_parser('worker')
    sub.add_parser('check')
    account = sub.add_parser('invite')
    identity = account.add_mutually_exclusive_group(required=True)
    identity.add_argument('--name', help='Create a new account with this label')
    identity.add_argument('--user', help='Renew access to an existing account ID, preserving its workspace')
    account.add_argument('--out', type=Path, required=True, help='Write the single-use credential to a private new file')
    args = parser.parse_args(); settings = Settings.load(args.config)
    if args.command == 'web':
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(settings), host='127.0.0.1', port=args.port, proxy_headers=False, access_log=False)
    elif args.command == 'worker':
        from .runner import serve
        serve(settings)
    elif args.command == 'check':
        from .runner import check_runtime
        check_runtime(settings)
        print(json.dumps({'worker_ready': True, 'public_url': settings.public_url,
                          'oauth_configured': bool(settings.issuer), 'models_configured': bool(settings.comfy_proxy),
                          'deployed': False}))
    elif args.command == 'invite':
        if args.out.exists():
            parser.error('Credential output already exists')
        store = Store(settings)
        value = store.renew_invitation(args.user) if args.user else store.add_user(args.name)
        with args.out.open('x', encoding='utf-8') as f:
            json.dump(value, f)
        args.out.chmod(0o600)
        print('Single-use invitation written to the requested private file; expires in seven days.')


if __name__ == '__main__':
    main()
