'''
Self-check for your bot. Run it before every submission:

    python3 check_bot.py my_bot

It plays a short game against a house bot under the official settings and
reports crashes, illegal actions, and how much of your clock you'd use.
Like the official machine, it runs your bot from a read-only copy of its
folder with `python3 player.py`, ignoring commands.json.

Options:
    --opponent house_bots/monte_carlo   which bot to play (default: rule_book)
    --hands 300                         how many hands (default: 100)
'''
import argparse
import ast
import hashlib
import os
import shutil
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
START_DIR = os.getcwd()
sys.path.insert(0, HERE)
os.chdir(HERE)  # the engine reads config.py from the current folder

import engine  # noqa: E402
from launchers import HostLauncher  # noqa: E402

APPROVED = {'eval7', 'numpy', 'skeleton'}
SIZE_LIMIT_MB = 100
OFFICIAL_HANDS = engine.NUM_ROUNDS
OFFICIAL_CLOCK = engine.STARTING_GAME_CLOCK


def ok(msg):
    print('  [ok]   ' + msg)


def warn(msg):
    print('  [warn] ' + msg)


def fail(msg):
    print('  [FAIL] ' + msg)


def folder_size_mb(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total / 1e6


def tree_hash(path):
    digest = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(path)):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in sorted(files):
            if f.endswith('.pyc'):
                continue
            digest.update(os.path.relpath(os.path.join(root, f), path).encode())
            with open(os.path.join(root, f), 'rb') as fh:
                digest.update(fh.read())
    return digest.hexdigest()


def unapproved_imports(bot_dir):
    local = {os.path.splitext(f)[0] for f in os.listdir(bot_dir)}
    local |= {d for d in os.listdir(bot_dir) if os.path.isdir(os.path.join(bot_dir, d))}
    found = set()
    for root, dirs, files in os.walk(bot_dir):
        dirs[:] = [d for d in dirs if d not in ('skeleton', '__pycache__')]
        for f in files:
            if not f.endswith('.py'):
                continue
            try:
                tree = ast.parse(open(os.path.join(root, f), encoding='utf-8').read())
            except (SyntaxError, UnicodeDecodeError):
                continue  # a syntax error will show up when the bot runs
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                for n in names:
                    top = n.split('.')[0]
                    if top not in sys.stdlib_module_names and top not in APPROVED and top not in local:
                        found.add(top)
    return sorted(found)


def read_only_copy(src):
    dst = os.path.join(tempfile.mkdtemp(prefix='check_bot-'), os.path.basename(os.path.abspath(src)))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    for root, dirs, files in os.walk(dst):
        for f in files:
            os.chmod(os.path.join(root, f), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o555)
    os.chmod(dst, 0o555)
    return dst


def make_writable(path):
    for root, dirs, files in os.walk(path):
        os.chmod(root, 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)


def tail(path, lines=15):
    try:
        with open(path, 'r', errors='replace') as fh:
            content = fh.read().strip().splitlines()
    except FileNotFoundError:
        return []
    return content[-lines:]


def resolve(path):
    '''Finds a folder relative to where you ran the command, or else to this script.'''
    for base in (START_DIR, HERE):
        candidate = os.path.abspath(os.path.join(base, path))
        if os.path.isdir(candidate):
            return candidate
    return os.path.abspath(os.path.join(START_DIR, path))


def main():
    parser = argparse.ArgumentParser(description='Check your bot before submitting it.')
    parser.add_argument('bot', help='path to your bot folder, e.g. my_bot')
    parser.add_argument('--opponent', default='house_bots/rule_book')
    parser.add_argument('--hands', type=int, default=100)
    args = parser.parse_args()
    bot_dir = resolve(args.bot)
    opponent_dir = resolve(args.opponent)
    if not os.path.isdir(bot_dir):
        print('No folder named {}'.format(args.bot))
        sys.exit(1)

    print('Checking {} against {} ({} hands, official settings)\n'.format(
        os.path.basename(bot_dir), os.path.basename(opponent_dir), args.hands))
    problems = 0

    if sys.version_info[:2] != (3, 12):
        warn('You are running Python {}.{}; the official machine uses Python 3.12.'.format(*sys.version_info[:2]))

    # 1. Folder layout
    if not os.path.isfile(os.path.join(bot_dir, 'player.py')):
        fail('No player.py in {}. The official machine always runs player.py.'.format(bot_dir))
        sys.exit(1)
    if not os.path.isdir(os.path.join(bot_dir, 'skeleton')):
        fail('No skeleton/ folder. Copy it unchanged from python_skeleton/.')
        sys.exit(1)
    ok('Folder has player.py and skeleton/')
    if tree_hash(os.path.join(bot_dir, 'skeleton')) != tree_hash(os.path.join(HERE, 'python_skeleton', 'skeleton')):
        warn('Your skeleton/ folder differs from python_skeleton/skeleton. Keep it unchanged.')

    # 2. Size
    size = folder_size_mb(bot_dir)
    if size > SIZE_LIMIT_MB:
        fail('Folder is {:.1f} MB; the limit is {} MB.'.format(size, SIZE_LIMIT_MB))
        problems += 1
    else:
        ok('Size: {:.1f} MB of {} MB'.format(size, SIZE_LIMIT_MB))

    # 3. Libraries
    extra = unapproved_imports(bot_dir)
    if extra:
        warn('Imports libraries that aren\'t approved: {}. Request them by the end of week 1, '
             'or they won\'t be on the official machine.'.format(', '.join(extra)))
    else:
        ok('Imports: only the standard library, eval7, and NumPy')

    # 4. Play a game
    work = tempfile.mkdtemp(prefix='check_bot-logs-')
    bot_copy = read_only_copy(bot_dir)
    name = 'your_bot'
    try:
        result = engine.Game((name, bot_copy), ('house_bot', opponent_dir), num_rounds=args.hands,
                             official=True, launcher=HostLauncher(), log_dir=work, quiet=True).run()
    finally:
        make_writable(os.path.dirname(bot_copy))
        shutil.rmtree(os.path.dirname(bot_copy), ignore_errors=True)
    me = result['players'][0]
    ev = me['events']
    bot_log = os.path.join(work, name + '.txt')

    if not ev['connected']:
        fail('Your bot never connected to the engine. It probably crashed while starting.')
        problems += 1
    else:
        ok('Connected to the engine')
        if ev['disconnected']:
            fail('Your bot crashed or disconnected on hand {}. The engine checked or folded '
                 'for it after that.'.format(ev['disconnected']))
            problems += 1
        elif ev['ran_out_of_time']:
            fail('Your bot ran out of time on hand {}.'.format(ev['ran_out_of_time']))
            problems += 1
        else:
            ok('No crashes or disconnects')
        bad = ev['illegal'] + ev['misformatted']
        if bad:
            fail('{} illegal or garbled actions. Search the game log for "attempted illegal" '
                 'or "misformatted".'.format(bad))
            problems += 1
        else:
            ok('No illegal or garbled actions')
        projected = me['clock_used'] * OFFICIAL_HANDS / args.hands
        clock_msg = 'Clock: {:.2f} s used in {} hands, about {:.0f} s per {:,}-hand game (limit {:.0f} s)'.format(
            me['clock_used'], args.hands, projected, OFFICIAL_HANDS, OFFICIAL_CLOCK)
        if projected > OFFICIAL_CLOCK:
            fail(clock_msg + '. You would run out of time.')
            problems += 1
        elif projected > 0.8 * OFFICIAL_CLOCK:
            warn(clock_msg + '. That\'s cutting it close, and the official machine may be slower.')
        else:
            ok(clock_msg)
        print('\n  Result: {:+d} chips against {} over {} hands (short games are mostly luck)'.format(
            me['bankroll'], os.path.basename(opponent_dir), args.hands))

    if problems and tail(bot_log):
        printed = tail(bot_log)
        if any('PermissionError' in line or 'Read-only file system' in line for line in printed):
            print('\n  Your bot tried to write a file. Bot folders are read-only on the official '
                  'machine, so keep notes in memory.')
        print('\n  Last lines your bot printed (full output in {}):'.format(bot_log))
        for line in printed:
            print('    ' + line)
    print('\n  Game log: {}'.format(os.path.join(work, engine.GAME_LOG_FILENAME + '.txt')))

    if problems:
        print('\nFAIL: fix the problems above before submitting.')
        sys.exit(1)
    print('\nPASS: your bot is ready to submit.')


if __name__ == '__main__':
    main()
