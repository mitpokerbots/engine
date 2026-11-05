'''
House bot 2: Rule Book.

Plays by fixed rules. Before the flop it sorts its two cards into tiers and
raises, calls, or folds by tier. After the flop it asks eval7 what hand it has
made and bets strong hands, calls with medium hands, and gives up on weak ones.
It never bluffs and never adapts to its opponent, so it's predictable.
'''
import eval7

from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction
from skeleton.states import GameState, TerminalState, RoundState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

RANKS = '23456789TJQKA'
CATEGORY = {'High Card': 0, 'Pair': 1, 'Two Pair': 2, 'Trips': 3, 'Straight': 4,
            'Flush': 5, 'Full House': 6, 'Quads': 7, 'Straight Flush': 8}


def preflop_tier(cards):
    '''3 = premium, 2 = good, 1 = playable, 0 = junk.'''
    high, low = sorted((RANKS.index(card[0]) for card in cards), reverse=True)
    suited = cards[0][1] == cards[1][1]
    pair = high == low
    ace = RANKS.index('A')
    if (pair and high >= RANKS.index('T')) or (high == ace and low >= RANKS.index('Q')):
        return 3  # TT+, AK, AQ
    if pair or high == ace or low >= RANKS.index('J') or (suited and high - low == 1 and low >= RANKS.index('5')):
        return 2  # any pair, any ace, two cards J or higher, suited connectors 65s+
    if high >= RANKS.index('Q') or suited:
        return 1
    return 0


def postflop_strength(cards, board):
    '''3 = very strong, 2 = strong, 1 = medium, 0 = weak.'''
    category = CATEGORY[eval7.handtype(eval7.evaluate([eval7.Card(c) for c in cards + board]))]
    board_ranks = [card[0] for card in board]
    board_paired = len(set(board_ranks)) < len(board_ranks)
    if category >= CATEGORY['Straight']:
        return 3
    if category >= CATEGORY['Two Pair']:
        # two pair or trips that are mostly on the board are only medium
        return 1 if board_paired and category == CATEGORY['Two Pair'] else 2
    if category == CATEGORY['Pair']:
        return 0 if board_paired else 1  # a pair on the board belongs to both players
    return 0


class Player(Bot):

    def __init__(self):
        pass

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def bet(self, round_state, active, fraction):
        '''Bets or raises about `fraction` of the pot, clamped to the legal range.'''
        legal = round_state.legal_actions()
        if RaiseAction not in legal:
            return CallAction() if CallAction in legal else CheckAction()
        min_raise, max_raise = round_state.raise_bounds()
        my_pip = round_state.pips[active]
        continue_cost = round_state.pips[1 - active] - my_pip
        pot = sum(STARTING_STACK - stack for stack in round_state.stacks)
        target = my_pip + continue_cost + int(fraction * (pot + continue_cost))
        return RaiseAction(max(min_raise, min(max_raise, target)))

    def passive(self, round_state, call_limit):
        '''Checks if free, calls if the price is at most call_limit, otherwise folds.'''
        legal = round_state.legal_actions()
        if CheckAction in legal:
            return CheckAction()
        active = round_state.button % 2
        continue_cost = round_state.pips[1 - active] - round_state.pips[active]
        return CallAction() if continue_cost <= call_limit else FoldAction()

    def get_action(self, game_state, round_state, active):
        street = round_state.street
        my_cards = round_state.hands[active]
        board = round_state.deck[:street]
        continue_cost = round_state.pips[1 - active] - round_state.pips[active]
        pot = sum(STARTING_STACK - stack for stack in round_state.stacks)

        if street == 0:
            tier = preflop_tier(my_cards)
            if tier == 3:
                return self.bet(round_state, active, 1.0)
            if tier == 2:
                if continue_cost <= BIG_BLIND // 2 and RaiseAction in round_state.legal_actions():
                    return self.bet(round_state, active, 0.75)  # open-raise from the button
                return self.passive(round_state, call_limit=20)
            if tier == 1:
                return self.passive(round_state, call_limit=BIG_BLIND * 2)
            return self.passive(round_state, call_limit=0)

        strength = postflop_strength(my_cards, board)
        if strength == 3:
            return self.bet(round_state, active, 1.0)
        if strength == 2:
            if continue_cost > pot:  # facing a big raise: just call
                return self.passive(round_state, call_limit=STARTING_STACK)
            return self.bet(round_state, active, 0.66)
        if strength == 1:
            if continue_cost == 0:
                return self.bet(round_state, active, 0.5)
            return self.passive(round_state, call_limit=int(0.6 * pot))
        return self.passive(round_state, call_limit=int(0.15 * pot))


if __name__ == '__main__':
    run_bot(Player(), parse_args())
