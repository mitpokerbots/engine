"""6.176 MIT POKERBOTS GAME ENGINE"""

# DO NOT REMOVE, RENAME, OR EDIT THIS FILE
from collections import namedtuple
import time
import json
import subprocess
import socket
import eval7

from config import *

FoldAction = namedtuple('FoldAction', [])
CallAction = namedtuple('CallAction', [])
CheckAction = namedtuple('CheckAction', [])
# we coalesce BetAction and RaiseAction for convenience
RaiseAction = namedtuple('RaiseAction', ['amount'])
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])

STREET_NAMES = ['Flop', 'Turn', 'River']
DECODE = {'F': FoldAction, 'C': CallAction, 'K': CheckAction, 'R': RaiseAction}


def c_cards(code, cards):
    return code + ','.join(map(str, cards))


def p_cards(cards):
    return '[{}]'.format(' '.join(map(str, cards)))


def p_value(name, value):
    return ', {} ({})'.format(name, value)


def status(players):
    return ''.join([p_value(p.name, p.bankroll) for p in players])


class RoundState(namedtuple('_RoundState',
                            ['button', 'street', 'pips', 'stacks',
                             'hands', 'deck', 'previous_state'])):
    """
    Round state class.
    """

    def showdown(self):
        """ Return the showdown result.
        :return: TerminalState([player_1_delta, player_2_delta], self)
        """
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
        """
        :return: set of legal actions
        """
        active = self.button % 2
        continue_cost = self.pips[1 - active] - self.pips[active]
        if continue_cost == 0:
            # we can only raise the stakes if both players can afford it
            bets_forbidden = (self.stacks[0] == 0 or self.stacks[1] == 0)
            return {CheckAction} if bets_forbidden else {
                CheckAction, RaiseAction}

        # continue_cost > 0
        # similarly, re-raising is only allowed if both players can afford it
        raises_forbidden = (
            continue_cost == self.stacks[active] or self.stacks[1 - active] == 0)
        return {FoldAction, CallAction} if raises_forbidden else \
            {FoldAction, CallAction, RaiseAction}

    def raise_bounds(self):
        """
        :return: bounds for raises
        """

        active = self.button % 2
        continue_cost = self.pips[1 - active] - self.pips[active]
        max_contribution = min(
            self.stacks[active], self.stacks[1 - active] + continue_cost)
        min_contribution = min(
            max_contribution, self.pips[1 - active] + max(continue_cost, BIG_BLIND))
        return (
            self.pips[active] +
            min_contribution,
            self.pips[active] +
            max_contribution)

    def proceed_street(self):
        """
        :return: round state with the next street
        """

        if self.street == 5:
            return self.showdown()


        new_street = 3 if self.street == 0 else self.street + 1
        return RoundState(
            1, new_street, [
                0, 0], self.stacks, self.hands, self.deck, self)

    def proceed(self, action):
        """
        :param action: player action
        :return: next round state given current action
        """

        active = self.button % 2
        if isinstance(action, FoldAction):
            delta = self.stacks[0] - \
                STARTING_STACK if active == 0 else STARTING_STACK - self.stacks[1]
            return TerminalState([delta, -delta], self)

        if isinstance(action, CallAction):
            if self.button == 0:  # sb calls bb
                return RoundState(1,
                                  0,
                                  [BIG_BLIND] * 2,
                                  [STARTING_STACK - BIG_BLIND] * 2,
                                  self.hands,
                                  self.deck,
                                  self)

            # both players acted
            new_pips = list(self.pips)
            new_stacks = list(self.stacks)
            contribution = new_pips[1 - active] - new_pips[active]
            new_stacks[active] -= contribution
            new_pips[active] += contribution
            state = RoundState(
                self.button + 1,
                self.street,
                new_pips,
                new_stacks,
                self.hands,
                self.deck,
                self)
            return state.proceed_street()

        if isinstance(action, CheckAction):
            if (self.street == 0 and self.button >
                    0) or self.button > 1:  # both players acted
                return self.proceed_street()

            # let opponent act
            return RoundState(
                self.button + 1,
                self.street,
                self.pips,
                self.stacks,
                self.hands,
                self.deck,
                self)
        new_pips = list(self.pips)
        new_stacks = list(self.stacks)
        contribution = action.amount - new_pips[active]
        new_stacks[active] -= contribution
        new_pips[active] += contribution
        return RoundState(
            self.button + 1,
            self.street,
            new_pips,
            new_stacks,
            self.hands,
            self.deck,
            self)


class Player:
    """
    Socket player class.
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, name, path, host, port):
        """
        :param name: player name
        :param path: path to player code
        :param host: host to connect on
        :param port: port to connect on
        """
        self.name = name
        self.path = path
        self.host = host
        self.port = port
        self.game_clock = STARTING_GAME_CLOCK
        self.bankroll = 0
        self.commands = None
        self.bot_subprocess = None
        self.socketfile = None
        self.bytes_log = []

    def build(self):
        """
        Build player bot.
        """

        # load commands file
        try:
            with open(self.path + '/commands.json', 'r') as json_file:
                commands = json.load(json_file)
            if ('build' in commands and 'run' in commands and
                    isinstance(commands['build'], list) and
                    isinstance(commands['run'], list)):
                self.commands = commands
            else:
                print(self.name, 'commands.json missing command')
        except FileNotFoundError:
            print(self.name, 'commands.json not found - check PLAYER_PATH')
        except json.decoder.JSONDecodeError:
            print(self.name, 'commands.json misformatted')

        # build pokerbot
        if self.commands is not None and len(self.commands['build']) > 0:
            try:
                proc = subprocess.run(
                    self.commands['build'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=self.path,
                    timeout=BUILD_TIMEOUT,
                    check=False)
                self.bytes_log.append(proc.stdout)
            except subprocess.TimeoutExpired as exc:
                print('Timed out waiting for', self.name, 'to build')
                self.bytes_log.append(exc.stdout)
            except (TypeError, ValueError):
                print(self.name, 'build command misformatted')
            except OSError:
                print(self.name, 'build failed - check "build" in commands.json')

    def run(self):
        """
        Run player bot.
        """

        # run pokerbot
        if self.commands is not None and len(self.commands['run']) > 0:
            try:
                proc = subprocess.Popen(self.commands['run'] + [str(
                    self.port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.path)
                self.bot_subprocess = proc
            except (TypeError, ValueError):
                print(self.name, 'run command misformatted')
            except OSError:
                print(self.name, 'run failed - check "run" in commands.json')
            # establish client-server connection
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                    server_socket.bind((self.host, self.port))
                    server_socket.settimeout(CONNECT_TIMEOUT)
                    server_socket.listen()
                    client_socket, _ = server_socket.accept()
                    client_socket.settimeout(CONNECT_TIMEOUT)
                    socketfile = client_socket.makefile('rw')
                    self.socketfile = socketfile
                    print(self.name, 'connected successfully')
            except socket.timeout:
                print('Timed out waiting for', self.name, 'to connect')
            except OSError:
                print(self.name, 'connect failed - check PLAYER_PORT')

    def stop(self):
        """
        Stop player.
        """

        if self.socketfile is not None:
            try:
                self.socketfile.write('Q\n')
                self.socketfile.close()
            except socket.timeout:
                print('Timed out waiting for', self.name, 'to disconnect')
            except OSError:
                print('Could not close socket connection with', self.name)

        if self.bot_subprocess is not None:
            try:
                outs, _ = self.bot_subprocess.communicate(
                    timeout=QUIT_TIMEOUT)
                self.bytes_log.append(outs)
            except subprocess.TimeoutExpired:
                print('Timed out waiting for', self.name, 'to quit')
                self.bot_subprocess.kill()
                outs, _ = self.bot_subprocess.communicate()
                self.bytes_log.append(outs)
        with open(self.name + '.txt', 'wb') as log_file:
            for output in self.bytes_log:
                log_file.write(output)

    def query(self, round_state, round_rep, game_log):
        """
        Get player action.
        """

        legal_actions = round_state.legal_actions() if isinstance(
            round_state, RoundState) else {CheckAction}
        if self.socketfile is not None and self.game_clock > 0.:
            try:
                round_rep[0] = 'T{:.3f}'.format(self.game_clock)
                message = ' '.join(round_rep) + '\n'
                start_time = time.perf_counter()
                self.socketfile.write(message)
                self.socketfile.flush()
                clause = self.socketfile.readline().strip()
                end_time = time.perf_counter()
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
                game_log.append(
                    self.name +
                    ' attempted illegal ' +
                    action.__name__)
            except socket.timeout:
                error_message = self.name + ' ran out of time'
                game_log.append(error_message)
                print(error_message)
                self.game_clock = 0.
            except BrokenPipeError:
                error_message = self.name + ' disconnected'
                game_log.append(error_message)
                print(error_message)
                self.game_clock = 0.
            except (IndexError, KeyError, ValueError):
                game_log.append(self.name + ' response misformatted')
        return CheckAction() if CheckAction in legal_actions else FoldAction()


class Game:
    """
    Pokerbots game representation.
    """

    def __init__(self):
        self.log = [
            '6.176 MIT Pokerbots - ' +
            PLAYER_1_NAME +
            ' vs ' +
            PLAYER_2_NAME]
        self.round_reps = [[], []]

    def log_round_state(self, players, round_state):
        """
        Logs the current round state.

        :param players: list of players
        :param round_state: current round state
        """

        if round_state.street == 0 and round_state.button == 0:
            self.log.append(
                '{} posts the blind of {}'.format(
                    players[0].name, SMALL_BLIND))
            self.log.append(
                '{} posts the blind of {}'.format(
                    players[1].name, BIG_BLIND))
            self.log.append(
                '{} dealt {}'.format(
                    players[0].name, p_cards(
                        round_state.hands[0])))
            self.log.append(
                '{} dealt {}'.format(
                    players[1].name, p_cards(
                        round_state.hands[1])))
            self.round_reps[0] = [
                'T0.', 'P0', c_cards(
                    'H', round_state.hands[0])]
            self.round_reps[1] = [
                'T0.', 'P1', c_cards(
                    'H', round_state.hands[1])]

        elif round_state.street > 0 and round_state.button == 1:
            board = round_state.deck.peek(round_state.street)
            self.log.append(STREET_NAMES[round_state.street -
                                         3] +
                            ' ' +
                            p_cards(board) +
                            p_value(players[0].name, STARTING_STACK -
                                    round_state.stacks[0]) +
                            p_value(players[1].name, STARTING_STACK -
                                    round_state.stacks[1]))
            compressed_board = c_cards('B', board)
            self.round_reps[0].append(compressed_board)
            self.round_reps[1].append(compressed_board)

    def log_action(self, name, action, bet_override):
        """
        Logs a game action.

        :param name: player name
        :param action: player action
        :param bet_override: True if raise, False if bet
        """
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
            phrasing = (' bets ' if bet_override else ' raises to ') + \
                str(action.amount)
            code = 'R' + str(action.amount)

        self.log.append(name + phrasing)
        self.round_reps[0].append(code)
        self.round_reps[1].append(code)

    def log_terminal_state(self, players, round_state):
        """
        Logs the terminal state.

        :param players: list of players
        :param round_state: terminal round state
        """

        previous_state = round_state.previous_state

        # if no fold, show hands
        if FoldAction not in previous_state.legal_actions():
            self.log.append(
                '{} shows {}'.format(
                    players[0].name, p_cards(
                        previous_state.hands[0])))
            self.log.append(
                '{} shows {}'.format(
                    players[1].name, p_cards(
                        previous_state.hands[1])))
            self.round_reps[0].append(c_cards('O', previous_state.hands[1]))
            self.round_reps[1].append(c_cards('O', previous_state.hands[0]))

        self.log.append(
            '{} awarded {}'.format(
                players[0].name,
                round_state.deltas[0]))
        self.log.append(
            '{} awarded {}'.format(
                players[1].name,
                round_state.deltas[1]))
        self.round_reps[0].append('D' + str(round_state.deltas[0]))
        self.round_reps[1].append('D' + str(round_state.deltas[1]))

    def run_round(self, players):
        """ Runs a round between players.

        :param players: list of players
        """

        deck = eval7.Deck()
        deck.shuffle()

        # deal two to each player
        hands = [deck.deal(2), deck.deal(2)]
        pips = [SMALL_BLIND, BIG_BLIND]
        stacks = [STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND]
        round_state = RoundState(0, 0, pips, stacks, hands, deck, None)
        while not isinstance(round_state, TerminalState):
            self.log_round_state(players, round_state)
            active = round_state.button % 2
            player = players[active]
            action = player.query(
                round_state, self.round_reps[active], self.log)
            bet_override = (round_state.pips == [0, 0])
            self.log_action(player.name, action, bet_override)
            round_state = round_state.proceed(action)
        self.log_terminal_state(players, round_state)
        for player, round_rep, delta in zip(
                players, self.round_reps, round_state.deltas):
            player.query(round_state, round_rep, self.log)
            player.bankroll += delta

    def run(self):
        """
        Run a game.
        """

        print('   __  _____________  ___       __           __        __    ')
        print('  /  |/  /  _/_  __/ / _ \\___  / /_____ ____/ /  ___  / /____')
        print(' / /|_/ // /  / /   / ___/ _ \\/  \'_/ -_) __/ _ \\/ _ \\/ __(_-<')
        print('/_/  /_/___/ /_/   /_/   \\___/_/\\_\\\\__/_/ /_.__/\\___/\\__/___/')
        print()
        print('Starting the Pokerbots engine...')
        players = [
            Player(PLAYER_1_NAME, PLAYER_1_PATH, PLAYER_1_HOST, PLAYER_1_PORT),
            Player(PLAYER_2_NAME, PLAYER_2_PATH, PLAYER_2_HOST, PLAYER_2_PORT)
        ]
        for player in players:
            player.build()
            player.run()

        for round_num in range(1, ROUNDS + 1):
            self.log.append('')
            self.log.append('Round #' + str(round_num) + status(players))
            self.run_round(players)
            players = players[::-1]

        self.log.append('')
        self.log.append('Final' + status(players))

        for player in players:
            player.stop()

        name = GAME_LOG_FILENAME + '.txt'
        print('Writing', name)

        with open(name, 'w') as log_file:
            log_file.write('\n'.join(self.log))


if __name__ == '__main__':
    Game().run()
