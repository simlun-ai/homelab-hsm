"""Container command dispatcher; the underlying commands own all secret handling."""
import sys

from .cli import unwrap_main, wrap_main


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('Usage: homelab-secrets {wrap|unwrap} [arguments]')
        return 0 if len(sys.argv) > 1 else 2
    command = sys.argv.pop(1)
    if command not in ('wrap', 'unwrap'):
        print('Expected wrap or unwrap. Use --help for usage.', file=sys.stderr)
        return 2
    return {'wrap': wrap_main, 'unwrap': unwrap_main}[command]()


if __name__ == '__main__':
    sys.exit(main())
