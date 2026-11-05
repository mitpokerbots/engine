'''
Ways to start a bot for check_bot.py and the tournament runner.

HostLauncher runs the bot directly on this machine with the same Python that's
running the engine. ContainerLauncher runs it in a locked-down Docker or Podman
container: no network, 1 CPU, 2 GB of memory, a read-only bot folder, and a
Unix socket as its only connection to the engine.
'''
import os
import subprocess
import sys


class HostLauncher:
    '''Runs `python player.py <connection>` in the bot's folder, with this Python.'''

    def command(self, name, bot_path, connect_arg):
        return [sys.executable, 'player.py', connect_arg], bot_path

    def cleanup(self, name):
        pass


class ContainerLauncher:
    '''
    Runs each bot in its own container. The engine must be started with a
    socket_dir, so connect_arg is the path of that bot's Unix socket.
    '''

    def __init__(self, runtime='podman', image='devnet-pokerbots', python='python3',
                 cpus='1', memory='2g', pids=64, game_id='game', cpuset=None, extra_mounts=(),
                 selinux=False):
        self.runtime = runtime
        self.image = image
        self.python = python
        self.cpus = cpus
        self.memory = memory
        self.pids = pids
        self.game_id = game_id
        self.cpuset = cpuset or {}          # optional {bot name: '2'} to pin a bot to a core
        self.extra_mounts = list(extra_mounts)  # e.g. ['/usr:/usr:ro'] for local testing
        self.label = ',Z' if selinux else ''     # relabel mounts on SELinux hosts (Fedora, CentOS)

    def container_name(self, name):
        return 'pokerbots-{}-{}'.format(self.game_id, name)

    def command(self, name, bot_path, connect_arg):
        socket_dir = os.path.dirname(os.path.abspath(connect_arg))
        argv = [
            self.runtime, 'run', '--rm',
            '--name', self.container_name(name),
            '--network', 'none',                         # no internet, no other containers
            '--cpus', str(self.cpus),
            '--memory', self.memory, '--memory-swap', self.memory,
            '--pids-limit', str(self.pids),
            '--read-only',                               # nothing written survives the game
            '--tmpfs', '/tmp:rw,size=64m,mode=1777',
            '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges',
            '--user', '65534:65534',                     # an unprivileged user
            '-e', 'PYTHONDONTWRITEBYTECODE=1',
            '-v', '{}:/bot:ro{}'.format(os.path.abspath(bot_path), self.label),
            '-v', '{}:/sock{}'.format(socket_dir, ':Z' if self.label else ''),  # only this bot's socket
            '-w', '/bot',
        ]
        if name in self.cpuset:
            argv += ['--cpuset-cpus', str(self.cpuset[name])]
        for mount in self.extra_mounts:
            argv += ['-v', mount]
        argv += [self.image, self.python, 'player.py', '/sock/' + os.path.basename(connect_arg)]
        return argv, None

    def cleanup(self, name):
        # if the bot hung and its container is still running, remove it
        subprocess.run([self.runtime, 'rm', '-f', self.container_name(name)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
