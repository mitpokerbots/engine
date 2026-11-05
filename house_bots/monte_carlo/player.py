'''
House bot 3: Monte Carlo.

The strongest house bot. Each time it acts, it estimates its equity (its chance
of winning at showdown) by dealing out the unknown cards many times with eval7,
then compares that equity with the pot odds. It budgets its simulations so it
never runs out of clock, and it does a little opponent modeling: it counts how
often the opponent folds to its bets, and bluffs more on the river if that
number is high.

Its simulations assume the opponent could hold any two cards. To correct for
that, it discounts its equity when facing a bet, more for bigger bets. That's a
crude stand-in for real hand reading, and it's the easiest thing to improve.
'''
import random
import time

import eval7

from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction
from skeleton.states import GameState, TerminalState, RoundState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

FULL_DECK = [str(card) for card in eval7.Deck().cards]
MAX_SIMULATIONS = 600
MIN_SIMULATIONS = 60


def estimate_equity(my_cards, board, time_budget):
    '''Fraction of random run-outs this hand wins against a random opponent hand.'''
    known = set(my_cards) | set(board)
    deck = [eval7.Card(c) for c in FULL_DECK if c not in known]
    hole = [eval7.Card(c) for c in my_cards]
    shared = [eval7.Card(c) for c in board]
    to_deal = 5 - len(shared)
    deadline = time.perf_counter() + time_budget
    score, trials = 0.0, 0
    while trials < MAX_SIMULATIONS and (trials < MIN_SIMULATIONS or time.perf_counter() < deadline):
        sample = random.sample(deck, 2 + to_deal)
        full_board = shared + sample[2:]
        mine = eval7.evaluate(hole + full_board)
        theirs = eval7.evaluate(sample[:2] + full_board)
        score += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0
        trials += 1
    return score / trials


class Player(Bot):

    def __init__(self):
        self.bets_made = 0         # hands where we bet or raised
        self.folds_to_our_bets = 0  # ... and the opponent folded
        self.bet_this_hand = False

    def handle_new_round(self, game_state, round_state, active):
        self.bet_this_hand = False

    def handle_round_over(self, game_state, terminal_state, active):
        if self.bet_this_hand:
            self.bets_made += 1
            opp_cards = terminal_state.previous_state.hands[1 - active]
            if terminal_state.deltas[active] > 0 and not opp_cards:
                self.folds_to_our_bets += 1  # we won without a showdown

    def opponent_fold_rate(self):
        # start from a neutral guess so a few hands don't swing it too far
        return (self.folds_to_our_bets + 3) / (self.bets_made + 10)

    def time_budget(self, game_state):
        '''Seconds to spend on this decision, leaving a safety margin.'''
        hands_left = max(1, NUM_ROUNDS - game_state.round_num + 1)
        return 0.6 * game_state.game_clock / (hands_left * 3)

    def bet(self, round_state, active, fraction):
        legal = round_state.legal_actions()
        if RaiseAction not in legal:
            return CallAction() if CallAction in legal else CheckAction()
        min_raise, max_raise = round_state.raise_bounds()
        my_pip = round_state.pips[active]
        continue_cost = round_state.pips[1 - active] - my_pip
        pot = sum(STARTING_STACK - stack for stack in round_state.stacks)
        target = my_pip + continue_cost + int(fraction * (pot + continue_cost))
        self.bet_this_hand = True
        return RaiseAction(max(min_raise, min(max_raise, target)))

    def get_action(self, game_state, round_state, active):
        legal = round_state.legal_actions()
        street = round_state.street
        my_cards = round_state.hands[active]
        board = round_state.deck[:street]
        continue_cost = round_state.pips[1 - active] - round_state.pips[active]
        pot = sum(STARTING_STACK - stack for stack in round_state.stacks)

        equity = estimate_equity(my_cards, board, self.time_budget(game_state))
        if continue_cost > BIG_BLIND:
            # A bet usually means a stronger hand than "any two cards", so the bigger
            # the bet compared with the pot, the more we discount our equity.
            bet_size = continue_cost / max(1, pot - continue_cost)
            weight = 0.5 if street == 0 else 1.0
            equity = equity ** (1 + weight * min(1.5, bet_size))
        pot_odds = continue_cost / (pot + continue_cost) if continue_cost > 0 else 0.0

        if equity > 0.80:
            return self.bet(round_state, active, 1.0)
        if equity > 0.65 and continue_cost <= pot:
            return self.bet(round_state, active, 0.5)
        if continue_cost > 0 and equity > pot_odds + 0.05:
            return CallAction()
        if CheckAction in legal:
            # river bluff against an opponent who folds a lot
            if street == 5 and self.opponent_fold_rate() > 0.55 and RaiseAction in legal:
                return self.bet(round_state, active, 0.75)
            return CheckAction()
        return FoldAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
