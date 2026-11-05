'''
DevNet.CSU Pokerbots game engine.

Based on the MIT Pokerbots reference engine (github.com/mitpokerbots/engine),
with changes for the DevNet.CSU tournament: duplicate (seeded) deals, a hidden
deck seed, a fixed run command for official games, capped bot output, and an
optional Unix-socket connection so bots can run in containers with no network.

Teams: you don't need to edit this file. Run it with `python3 engine.py`
after setting the player paths in config.py.
'''
from collections import namedtuple
from threading import Thread
from queue import Queue
import time
import json
import subprocess
import socket
import eval7
import sys
import os
import random
import secrets

sys.path.append(os.getcwd())
from config import *

# Official games ignore each team's commands.json and use this fixed command.
FIXED_COMMANDS = {'build': [], 'run': ['python3', 'player.py']}

FoldAction = namedtuple('FoldAction', [])
CallAction = namedtuple('CallAction', [])
CheckAction = namedtuple('CheckAction', [])
# we coalesce BetAction and RaiseAction for convenience
RaiseAction = namedtuple('RaiseAction', ['amount'])
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])

STREET_NAMES = ['Flop', 'Turn', 'River']
DECODE = {'F': FoldAction, 'C': CallAction, 'K': CheckAction, 'R': RaiseAction}
CCARDS = lambda cards: ','.join(map(str, cards))
PCARDS = lambda cards: '[{}]'.format(' '.join(map(str, cards)))
PVALUE = lambda name, value: ', {} ({})'.format(name, value)
STATUS = lambda players: ''.join([PVALUE(p.name, p.bankroll) for p in players])

# Socket encoding scheme:
#
# T#.### the player's game clock
# P# the player's index
# H**,** the player's hand in common format
# F a fold action in the round history
# C a call action in the round history
# K a check action in the round history
# R### a raise action in the round history
# B**,**,**,**,** the board cards in common format
# O**,** the opponent's hand in common format
# D### the player's bankroll delta from the round
# Q game over
#
# Clauses are separated by spaces
# Messages end with '\n'
# The engine expects a response of K at the end of the round as an ack,
# otherwise a response which encodes the player's action
# Action history is sent once, including the player's actions


class RoundState(namedtuple('_RoundState', ['button', 'street', 'pips', 'stacks', 'hands', 'deck', 'previous_state'])):
    '''
    Encodes the game tree for one round of poker.
    '''

    def showdown(self):
        '''
        Compares the players' hands and computes payoffs.
        '''
        score0 = eval7.evaluate(self.deck.peek(5) + self.hands[0])
        score1 = eval7.evaluate(self.deck.peek(5) + self.hands[1])
        if score0 > score1:
            delta = STARTING_STACK - self.stacks[1]
        elif score0 < score1:
            delta = self.stacks[0] - STARTING_STACK
        else:  # split the pot
            delta = (self.stacks[0] - self.stacks[1]) // 2
        return TerminalState([delta, -delta], self)

    def legal_actions(self):
        '''
        Returns a set which corresponds to the active player's legal moves.
        '''
        active = self.button % 2
        continue_cost = self.pips[1-active] - self.pips[active]
        if continue_cost == 0:
            # we can only raise the stakes if both players can afford it
            bets_forbidden = (self.stacks[0] == 0 or self.stacks[1] == 0)
            return {CheckAction} if bets_forbidden else {CheckAction, RaiseAction}
        # continue_cost > 0
        # similarly, re-raising is only allowed if both players can afford it
        raises_forbidden = (continue_cost == self.stacks[active] or self.stacks[1-active] == 0)
        return {FoldAction, CallAction} if raises_forbidden else {FoldAction, CallAction, RaiseAction}

    def raise_bounds(self):
        '''
        Returns a tuple of the minimum and maximum legal raises.
        '''
        active = self.button % 2
        continue_cost = self.pips[1-active] - self.pips[active]
        max_contribution = min(self.stacks[active], self.stacks[1-active] + continue_cost)
        min_contribution = min(max_contribution, continue_cost + max(continue_cost, BIG_BLIND))
        return (self.pips[active] + min_contribution, self.pips[active] + max_contribution)

    def proceed_street(self):
        '''
        Resets the players' pips and advances the game tree to the next round of betting.
        '''
        if self.street == 5:
            return self.showdown()
        new_street = 3 if self.street == 0 else self.street + 1
        return RoundState(1, new_street, [0, 0], self.stacks, self.hands, self.deck, self)

    def proceed(self, action):
        '''
        Advances the game tree by one action performed by the active player.
        '''
        active = self.button % 2
        if isinstance(action, FoldAction):
            delta = self.stacks[0] - STARTING_STACK if active == 0 else STARTING_STACK - self.stacks[1]
            return TerminalState([delta, -delta], self)
        if isinstance(action, CallAction):
            if self.button == 0:  # sb calls bb
                return RoundState(1, 0, [BIG_BLIND] * 2, [STARTING_STACK - BIG_BLIND] * 2, self.hands, self.deck, self)
            # both players acted
            new_pips = list(self.pips)
            new_stacks = list(self.stacks)
            contribution = new_pips[1-active] - new_pips[active]
            new_stacks[active] -= contribution
            new_pips[active] += contribution
            state = RoundState(self.button + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self)
            return state.proceed_street()
        if isinstance(action, CheckAction):
            if (self.street == 0 and self.button > 0) or self.button > 1:  # both players acted
                return self.proceed_street()
            # let opponent act
            return RoundState(self.button + 1, self.street, self.pips, self.stacks, self.hands, self.deck, self)
        # isinstance(action, RaiseAction)
        new_pips = list(self.pips)
        new_stacks = list(self.stacks)
        contribution = action.amount - new_pips[active]
        new_stacks[active] -= contribution
        new_pips[active] += contribution
        return RoundState(self.button + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self)


class Player():
    '''
    Handles subprocess and socket interactions with one player's pokerbot.

    launcher: optional object with command(name, bot_path, connect_arg) -> (argv, cwd)
              and cleanup(name). Used by check_bot.py and the tournament runner,
              for example to start bots in containers. When it's None, the bot
              runs directly on this machine using its run command.
    socket_dir: if set, the bot connects over a Unix socket in this folder
                instead of a TCP port.
    '''

    def __init__(self, name, path, official=False, launcher=None, socket_dir=None, log_dir='.', quiet=False):
        self.name = name
        self.quiet = quiet
        self.time_used = 0.  # actual thinking time, even if the clock is later zeroed
        self.path = path
        self.official = official
        self.launcher = launcher
        self.socket_dir = socket_dir
        self.log_dir = log_dir
        self.game_clock = STARTING_GAME_CLOCK
        self.bankroll = 0
        self.commands = None
        self.bot_subprocess = None
        self.socketfile = None
        self.bytes_queue = Queue()
        self.round_num = 0
        self.events = {'connected': False, 'illegal': 0, 'misformatted': 0,
                       'ran_out_of_time': None, 'disconnected': None}

    def say(self, *args):
        if not self.quiet:
            print(*args)

    def build(self):
        '''
        Loads the commands file and builds the pokerbot.
        '''
        if self.official:
            self.commands = FIXED_COMMANDS
            return
        try:
            with open(os.path.join(self.path, 'commands.json'), 'r') as json_file:
                commands = json.load(json_file)
            if ('build' in commands and 'run' in commands and
                    isinstance(commands['build'], list) and
                    isinstance(commands['run'], list)):
                self.commands = commands
            else:
                self.say(self.name, 'commands.json missing command')
        except FileNotFoundError:
            self.say(self.name, 'commands.json not found - check PLAYER_PATH')
        except json.decoder.JSONDecodeError:
            self.say(self.name, 'commands.json misformatted')
        if self.commands is not None and len(self.commands['build']) > 0:
            try:
                proc = subprocess.run(self.commands['build'],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      cwd=self.path, timeout=BUILD_TIMEOUT, check=False)
                self.bytes_queue.put(proc.stdout)
            except subprocess.TimeoutExpired as timeout_expired:
                error_message = 'Timed out waiting for ' + self.name + ' to build'
                self.say(error_message)
                self.bytes_queue.put(timeout_expired.stdout)
                self.bytes_queue.put(error_message.encode())
            except (TypeError, ValueError):
                self.say(self.name, 'build command misformatted')
            except OSError:
                self.say(self.name, 'build failed - check "build" in commands.json')

    def _listen(self):
        '''
        Opens the socket the bot will connect to. Returns (server_socket, connect_arg),
        where connect_arg is what the bot receives on its command line.
        '''
        if self.socket_dir:
            bot_dir = os.path.join(self.socket_dir, self.name)
            os.makedirs(bot_dir, exist_ok=True)
            os.chmod(bot_dir, 0o755)
            sock_path = os.path.join(bot_dir, 'engine.sock')
            if os.path.exists(sock_path):
                os.unlink(sock_path)
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.bind(sock_path)
            os.chmod(sock_path, 0o666)  # the bot may run as a different user
            return server_socket, sock_path
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('127.0.0.1', 0))
        return server_socket, str(server_socket.getsockname()[1])

    def run(self):
        '''
        Runs the pokerbot and establishes the socket connection.
        '''
        if self.commands is not None and len(self.commands['run']) > 0:
            try:
                server_socket, connect_arg = self._listen()
                with server_socket:
                    server_socket.settimeout(CONNECT_TIMEOUT)
                    server_socket.listen()
                    if self.launcher is not None:
                        command, cwd = self.launcher.command(self.name, self.path, connect_arg)
                    else:
                        command = self.commands['run'] + [connect_arg]
                        cwd = self.path
                    # never pass the deck seed (or any other engine setting) to a bot
                    bot_env = {k: v for k, v in os.environ.items() if not k.startswith('POKERBOTS_')}
                    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, cwd=cwd, env=bot_env)
                    self.bot_subprocess = proc
                    # function for bot listening
                    def enqueue_output(out, queue):
                        kept = 0
                        try:
                            for line in out:
                                if kept < PLAYER_LOG_SIZE_LIMIT:  # keep draining, but stop storing
                                    kept += len(line)
                                    queue.put(line)
                        except ValueError:
                            pass
                    # start a separate bot listening thread which dies with the program
                    Thread(target=enqueue_output, args=(proc.stdout, self.bytes_queue), daemon=True).start()
                    # block until we timeout or the player connects
                    client_socket, _ = server_socket.accept()
                    with client_socket:
                        client_socket.settimeout(CONNECT_TIMEOUT)
                        sock = client_socket.makefile('rw')
                        self.socketfile = sock
                        self.events['connected'] = True
                        self.say(self.name, 'connected successfully')
            except (TypeError, ValueError):
                self.say(self.name, 'run command misformatted')
            except socket.timeout:
                self.say('Timed out waiting for', self.name, 'to connect')
            except OSError:
                self.say(self.name, 'run failed - check "run" in commands.json')

    def stop(self):
        '''
        Closes the socket connection and stops the pokerbot.
        '''
        if self.socketfile is not None:
            try:
                self.socketfile.write('Q\n')
                self.socketfile.close()
            except socket.timeout:
                self.say('Timed out waiting for', self.name, 'to disconnect')
            except OSError:
                self.say('Could not close socket connection with', self.name)
        if self.bot_subprocess is not None:
            try:
                self.bot_subprocess.communicate(timeout=CONNECT_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.say('Timed out waiting for', self.name, 'to quit')
                self.bot_subprocess.kill()
                self.bot_subprocess.communicate()
        if self.launcher is not None:
            self.launcher.cleanup(self.name)
        with open(os.path.join(self.log_dir, self.name + '.txt'), 'wb') as log_file:
            bytes_written = 0
            for output in self.bytes_queue.queue:
                try:
                    bytes_written += log_file.write(output)
                    if bytes_written >= PLAYER_LOG_SIZE_LIMIT:
                        break
                except TypeError:
                    pass

    def query(self, round_state, player_message, game_log):
        '''
        Requests one action from the pokerbot over the socket connection.
        At the end of the round, we request a CheckAction from the pokerbot.
        '''
        legal_actions = round_state.legal_actions() if isinstance(round_state, RoundState) else {CheckAction}
        if self.socketfile is not None and self.game_clock > 0.:
            clause = ''
            try:
                player_message[0] = 'T{:.3f}'.format(self.game_clock)
                message = ' '.join(player_message) + '\n'
                del player_message[1:]  # do not send redundant action history
                start_time = time.perf_counter()
                self.socketfile.write(message)
                self.socketfile.flush()
                clause = self.socketfile.readline()
                end_time = time.perf_counter()
                self.time_used += end_time - start_time
                if clause == '':  # the bot closed the connection or crashed
                    raise ConnectionError
                clause = clause.strip()
                if ENFORCE_GAME_CLOCK:
                    self.game_clock -= end_time - start_time
                if self.game_clock <= 0.:
                    raise socket.timeout
                action = DECODE[clause[0]]
                if action in legal_actions:
                    if clause[0] == 'R':
                        amount = int(clause[1:])
                        min_raise, max_raise = round_state.raise_bounds()
                        if min_raise <= amount <= max_raise:
                            return action(amount)
                    else:
                        return action()
                game_log.append(self.name + ' attempted illegal ' + action.__name__)
                self.events['illegal'] += 1
            except socket.timeout:
                error_message = self.name + ' ran out of time'
                game_log.append(error_message)
                self.say(error_message)
                self.game_clock = 0.
                self.events['ran_out_of_time'] = self.round_num
            except OSError:
                error_message = self.name + ' disconnected'
                game_log.append(error_message)
                self.say(error_message)
                self.game_clock = 0.
                self.events['disconnected'] = self.round_num
            except (IndexError, KeyError, ValueError):
                game_log.append(self.name + ' response misformatted: ' + str(clause))
                self.events['misformatted'] += 1
        return CheckAction() if CheckAction in legal_actions else FoldAction()


class Game():
    '''
    Manages logging and the high-level game procedure.

    With no arguments, it plays the game described in config.py, like the
    original MIT engine. The tournament runner and check_bot.py pass
    arguments instead.
    '''

    def __init__(self, player_1=None, player_2=None, num_rounds=None, seed=None,
                 official=None, launcher=None, socket_dir=None, log_dir='.', quiet=False):
        self.player_specs = [player_1 or (PLAYER_1_NAME, PLAYER_1_PATH),
                             player_2 or (PLAYER_2_NAME, PLAYER_2_PATH)]
        self.num_rounds = num_rounds or NUM_ROUNDS
        # Duplicate matches: both games of a matchup use the same seed.
        self.seed = seed or os.environ.get('POKERBOTS_SEED') or secrets.token_hex(16)
        self.official = bool(os.environ.get('POKERBOTS_OFFICIAL')) if official is None else official
        self.launcher = launcher
        self.socket_dir = socket_dir
        self.log_dir = log_dir
        self.quiet = quiet
        names = [spec[0] for spec in self.player_specs]
        self.log = ['DevNet.CSU Pokerbots - ' + names[0] + ' vs ' + names[1]]
        self.player_messages = [[], []]

    def log_round_state(self, players, round_state):
        '''
        Incorporates RoundState information into the game log and player messages.
        '''
        if round_state.street == 0 and round_state.button == 0:
            self.log.append('{} posts the blind of {}'.format(players[0].name, SMALL_BLIND))
            self.log.append('{} posts the blind of {}'.format(players[1].name, BIG_BLIND))
            self.log.append('{} dealt {}'.format(players[0].name, PCARDS(round_state.hands[0])))
            self.log.append('{} dealt {}'.format(players[1].name, PCARDS(round_state.hands[1])))
            self.player_messages[0] = ['T0.', 'P0', 'H' + CCARDS(round_state.hands[0])]
            self.player_messages[1] = ['T0.', 'P1', 'H' + CCARDS(round_state.hands[1])]
        elif round_state.street > 0 and round_state.button == 1:
            board = round_state.deck.peek(round_state.street)
            self.log.append(STREET_NAMES[round_state.street - 3] + ' ' + PCARDS(board) +
                            PVALUE(players[0].name, STARTING_STACK-round_state.stacks[0]) +
                            PVALUE(players[1].name, STARTING_STACK-round_state.stacks[1]))
            compressed_board = 'B' + CCARDS(board)
            self.player_messages[0].append(compressed_board)
            self.player_messages[1].append(compressed_board)

    def log_action(self, name, action, bet_override):
        '''
        Incorporates action information into the game log and player messages.
        '''
        if isinstance(action, FoldAction):
            phrasing = ' folds'
            code = 'F'
        elif isinstance(action, CallAction):
            phrasing = ' calls'
            code = 'C'
        elif isinstance(action, CheckAction):
            phrasing = ' checks'
            code = 'K'
        else:  # isinstance(action, RaiseAction)
            phrasing = (' bets ' if bet_override else ' raises to ') + str(action.amount)
            code = 'R' + str(action.amount)
        self.log.append(name + phrasing)
        self.player_messages[0].append(code)
        self.player_messages[1].append(code)

    def log_terminal_state(self, players, round_state):
        '''
        Incorporates TerminalState information into the game log and player messages.
        '''
        previous_state = round_state.previous_state
        if FoldAction not in previous_state.legal_actions():
            self.log.append('{} shows {}'.format(players[0].name, PCARDS(previous_state.hands[0])))
            self.log.append('{} shows {}'.format(players[1].name, PCARDS(previous_state.hands[1])))
            self.player_messages[0].append('O' + CCARDS(previous_state.hands[1]))
            self.player_messages[1].append('O' + CCARDS(previous_state.hands[0]))
        self.log.append('{} awarded {}'.format(players[0].name, round_state.deltas[0]))
        self.log.append('{} awarded {}'.format(players[1].name, round_state.deltas[1]))
        self.player_messages[0].append('D' + str(round_state.deltas[0]))
        self.player_messages[1].append('D' + str(round_state.deltas[1]))

    def run_round(self, players, round_num):
        '''
        Runs one round of poker.
        '''
        deck = eval7.Deck()
        # same seed + same hand number = same cards, so game 2 of a matchup replays game 1
        random.Random('{}:{}'.format(self.seed, round_num)).shuffle(deck.cards)
        hands = [deck.deal(2), deck.deal(2)]
        pips = [SMALL_BLIND, BIG_BLIND]
        stacks = [STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND]
        round_state = RoundState(0, 0, pips, stacks, hands, deck, None)
        while not isinstance(round_state, TerminalState):
            self.log_round_state(players, round_state)
            active = round_state.button % 2
            player = players[active]
            action = player.query(round_state, self.player_messages[active], self.log)
            bet_override = (round_state.pips == [0, 0])
            self.log_action(player.name, action, bet_override)
            round_state = round_state.proceed(action)
        self.log_terminal_state(players, round_state)
        for player, player_message, delta in zip(players, self.player_messages, round_state.deltas):
            player.query(round_state, player_message, self.log)
            player.bankroll += delta

    def run(self):
        '''
        Runs one game of poker and returns a summary of the result.
        '''
        if not self.quiet:
            print('DevNet.CSU Pokerbots engine (based on MIT Pokerbots)')
            print('Starting the engine...')
        os.makedirs(self.log_dir, exist_ok=True)
        players = [Player(name, path, official=self.official, launcher=self.launcher,
                          socket_dir=self.socket_dir, log_dir=self.log_dir, quiet=self.quiet)
                   for name, path in self.player_specs]
        first, second = players
        for player in players:
            player.build()
        for player in players:
            player.run()
        for round_num in range(1, self.num_rounds + 1):
            for player in players:
                player.round_num = round_num
            self.log.append('')
            self.log.append('Round #' + str(round_num) + STATUS(players))
            self.run_round(players, round_num)
            players = players[::-1]
        self.log.append('')
        self.log.append('Final' + STATUS(players))
        for player in players:
            player.stop()
        name = os.path.join(self.log_dir, GAME_LOG_FILENAME + '.txt')
        if not self.quiet:
            print('Writing', name)
        with open(name, 'w') as log_file:
            log_file.write('\n'.join(self.log))
        return {
            'seed': self.seed,
            'num_rounds': self.num_rounds,
            'players': [{
                'name': p.name,
                'bankroll': p.bankroll,
                'clock_used': round(min(p.time_used, STARTING_GAME_CLOCK), 3),
                'events': p.events,
            } for p in (first, second)],
        }


if __name__ == '__main__':
    Game().run()
