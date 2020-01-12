#ifndef __SKELETON_STATES_HPP__
#define __SKELETON_STATES_HPP__

#include <array>
#include <string>
#include "actions.hpp"

using std::array;
using std::string;

const int NUM_ROUNDS     = 1000;
const int STARTING_STACK = 200;
const int BIG_BLIND      = 2;
const int SMALL_BLIND    = 1;


/**
 * Stores higher state information across many rounds of poker.
 */
class GameState
{
    public:
        const int bankroll;
        const float game_clock;
        const int round_num;

        GameState(int bankroll, float game_clock, int round_num):
            bankroll(bankroll),
            game_clock(game_clock),
            round_num(round_num)
        {}
};


/**
 * The base class for the current state of one round of poker.
 */
class State
{
};


/**
 * Final state of a poker round corresponding to payoffs.
 */
class TerminalState : public State
{
    public:
        const array<int, 2> deltas;
        State* const previous_state;

        TerminalState(array<int, 2> deltas, State* previous_state):
            deltas(deltas),
            previous_state(previous_state)
        {}
};


/**
 * Encodes the game tree for one round of poker.
 */
class RoundState : public State
{
    public:
        const int button;
        const int street;
        const array<int, 2> pips;
        const array<int, 2> stacks;
        const array< array<string, 2>, 2 > hands;
        const array<string, 5> deck;
        State* const previous_state;

        RoundState(int button,
                   int street,
                   array<int, 2> pips,
                   array<int, 2> stacks,
                   array< array<string, 2>, 2 > hands,
                   array<string, 5> deck,
                   State* previous_state):
            button(button),
            street(street),
            pips(pips),
            stacks(stacks),
            hands(hands),
            deck(deck),
            previous_state(previous_state)
        {}

        /**
         * Compares the players' hands and computes payoffs.
         */
        State* showdown();

        /**
         * Returns a mask which corresponds to the active player's legal moves.
         */
        int legal_actions();

        /**
         * Returns an array of the minimum and maximum legal raises.
         */
        array<int, 2> raise_bounds();

        /**
         * Resets the players' pips and advances the game tree to the next round of betting.
         */
        State* proceed_street();

        /**
         * Advances the game tree by one action performed by the active player.
         */
        State* proceed(Action action);
};


#endif  // __SKELETON_STATES_HPP__