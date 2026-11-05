'''
Tournament runner (for the organizer).

Plays a round-robin of duplicate matches between every bot in a folder and
ranks them by matchups won, then net chips.

    python3 organizer/tournament.py BOTS_DIR [options]

BOTS_DIR holds one folder per team, each a bot folder with player.py and
skeleton/. Folder names become team names in the logs and standings.

Each matchup is two games with the same secret seed and the seats swapped.
Seeds come from secrets.token_hex and are saved in results.json so you can
publish them after the final, or rerun a matchup with the same cards.

Options:
    --out results            where logs, results.json, and standings.txt go
    --hands 3000             hands per game (default: config.py's NUM_ROUNDS)
    --sandbox podman         run bots in containers (podman or docker); see
                             organizer/README.md. Without it, bots run directly
                             on this machine, which is only safe for testing.
    --image devnet-pokerbots the container image built from organizer/Containerfile
    --selinux                relabel mounts; needed on SELinux hosts like Fedora
    --reuse-seeds FILE       take seeds from an earlier results.json
    --only A_vs_B            run only these matchups (repeatable), e.g. for reruns
'''
import argparse
import itertools
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START_DIR = os.getcwd()
sys.path.insert(0, REPO)
os.chdir(REPO)  # the engine reads config.py from the current folder

import engine  # noqa: E402
from launchers import HostLauncher, ContainerLauncher  # noqa: E402

BUY_IN = 10000


def find_bots(bots_dir):
    bots = {}
    for entry in sorted(os.listdir(bots_dir)):
        path = os.path.join(bots_dir, entry)
        if os.path.isfile(os.path.join(path, 'player.py')):
            name = re.sub(r'[^A-Za-z0-9_-]', '_', entry)
            if name in bots:
                sys.exit('Two bot folders map to the same name: ' + name)
            bots[name] = os.path.abspath(path)
    return bots


def play_game(p1, p2, bots, seed, hands, log_dir, args, game_id):
    socket_dir = None
    if args.sandbox:
        socket_dir = tempfile.mkdtemp(prefix='pb-')
        os.chmod(socket_dir, 0o755)
        launcher = ContainerLauncher(runtime=args.sandbox, image=args.image, python=args.python,
                                     game_id=game_id, extra_mounts=args.extra_mount,
                                     selinux=args.selinux)
    else:
        launcher = HostLauncher()
    try:
        return engine.Game((p1, bots[p1]), (p2, bots[p2]), num_rounds=hands, seed=seed,
                           official=True, launcher=launcher, socket_dir=socket_dir,
                           log_dir=log_dir, quiet=True).run()
    finally:
        if socket_dir:
            shutil.rmtree(socket_dir, ignore_errors=True)


def problems(game, label):
    notes = []
    for p in game['players']:
        ev = p['events']
        if not ev['connected']:
            notes.append('{}: {} never connected'.format(label, p['name']))
        if ev['disconnected']:
            notes.append('{}: {} disconnected on hand {}'.format(label, p['name'], ev['disconnected']))
        if ev['ran_out_of_time']:
            notes.append('{}: {} ran out of time on hand {}'.format(label, p['name'], ev['ran_out_of_time']))
        if ev['illegal'] or ev['misformatted']:
            notes.append('{}: {} made {} illegal/garbled actions'.format(label, p['name'], ev['illegal'] + ev['misformatted']))
    return notes


def standings(bots, matchups):
    table = {name: {'team': name, 'won': 0, 'lost': 0, 'tied': 0, 'net': 0, 'vs': {}} for name in bots}
    for m in matchups:
        a, b, score = m['a'], m['b'], m['score_a']
        table[a]['net'] += score
        table[b]['net'] -= score
        table[a]['vs'][b] = score
        table[b]['vs'][a] = -score
        if score > 0:
            table[a]['won'] += 1
            table[b]['lost'] += 1
        elif score < 0:
            table[b]['won'] += 1
            table[a]['lost'] += 1
        else:
            table[a]['tied'] += 1
            table[b]['tied'] += 1
    ranked = sorted(table.values(), key=lambda row: (-row['won'], -row['net']))
    for i, row in enumerate(ranked, 1):
        row['rank'] = i
        row['bankroll'] = BUY_IN + row['net']
    return ranked


def format_standings(ranked):
    names = [row['team'] for row in ranked]
    width = max(8, max(len(n) for n in names) + 2)
    head = '{:<5}{:<{w}}{:>5}{:>5}{:>5}{:>11}{:>11}'.format('Rank', 'Team', 'W', 'L', 'T', 'Net', 'Bankroll', w=width)
    lines = [head, '-' * len(head)]
    for row in ranked:
        lines.append('{:<5}{:<{w}}{:>5}{:>5}{:>5}{:>+11,}{:>11,}'.format(
            row['rank'], row['team'], row['won'], row['lost'], row['tied'], row['net'], row['bankroll'], w=width))
    lines += ['', 'Head to head (row team\'s chips against column team):']
    lines.append(' ' * width + ''.join('{:>12}'.format(n[:11]) for n in names))
    for row in ranked:
        cells = ''.join('{:>12}'.format('-' if n == row['team'] else '{:+,}'.format(row['vs'].get(n, 0)))
                        for n in names)
        lines.append('{:<{w}}'.format(row['team'], w=width) + cells)
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Run the DevNet.CSU Pokerbots tournament.')
    parser.add_argument('bots_dir')
    parser.add_argument('--out', default='results')
    parser.add_argument('--hands', type=int, default=engine.NUM_ROUNDS)
    parser.add_argument('--sandbox', choices=['podman', 'docker'])
    parser.add_argument('--image', default='devnet-pokerbots')
    parser.add_argument('--python', default='python3', help='Python command inside the container')
    parser.add_argument('--selinux', action='store_true', help='relabel mounts (needed on SELinux hosts)')
    parser.add_argument('--extra-mount', action='append', default=[], help=argparse.SUPPRESS)
    parser.add_argument('--reuse-seeds')
    parser.add_argument('--only', action='append', default=[])
    args = parser.parse_args()

    bots_dir = os.path.join(START_DIR, args.bots_dir)
    out = os.path.join(START_DIR, args.out)
    bots = find_bots(bots_dir)
    if len(bots) < 2:
        sys.exit('Need at least two bot folders in ' + bots_dir)
    os.makedirs(out, exist_ok=True)
    old_seeds = {}
    if args.reuse_seeds:
        with open(os.path.join(START_DIR, args.reuse_seeds)) as fh:
            old_seeds = {m['id']: m['seed'] for m in json.load(fh)['matchups']}

    pairs = list(itertools.combinations(bots, 2))
    if not args.sandbox:
        print('Note: no --sandbox, so bots run directly on this machine. Use this only for testing.\n')
    print('{} bots, {} matchups, {} hands per game\n'.format(len(bots), len(pairs), args.hands))

    matchups = []
    for a, b in pairs:
        mid = '{}_vs_{}'.format(a, b)
        if args.only and mid not in args.only:
            continue
        seed = old_seeds.get(mid) or secrets.token_hex(16)
        started = time.time()
        g1 = play_game(a, b, bots, seed, args.hands, os.path.join(out, mid, 'game1'), args, mid + '-1')
        g2 = play_game(b, a, bots, seed, args.hands, os.path.join(out, mid, 'game2'), args, mid + '-2')
        score_a = g1['players'][0]['bankroll'] + g2['players'][1]['bankroll']
        notes = problems(g1, 'game 1') + problems(g2, 'game 2')
        matchups.append({'id': mid, 'a': a, 'b': b, 'seed': seed, 'score_a': score_a,
                         'games': [g1, g2], 'notes': notes})
        winner = a if score_a > 0 else b if score_a < 0 else 'tie'
        print('{:<40} {:>+8,}  winner: {:<16} ({:.0f} s)'.format(mid, score_a, winner, time.time() - started))
        for note in notes:
            print('    ! ' + note)

    if args.only:
        print('\nRan only the requested matchups; standings below cover just those.')
    ranked = standings(bots, matchups)
    report = format_standings(ranked)
    print('\n' + report)
    with open(os.path.join(out, 'standings.txt'), 'w') as fh:
        fh.write(report + '\n')
    with open(os.path.join(out, 'results.json'), 'w') as fh:
        json.dump({'hands_per_game': args.hands, 'sandbox': args.sandbox, 'matchups': matchups,
                   'standings': ranked}, fh, indent=2)
    print('\nSaved logs, results.json (includes the seeds - keep it private until after the final), '
          'and standings.txt in ' + out)


if __name__ == '__main__':
    main()
