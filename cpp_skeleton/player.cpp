/**
 * Simple example pokerbot, written in C++.
 */
#include "player.hpp"

/**
 * Called when a new game starts. Called exactly once.
 */
Player::Player()
{
}

/**
 * Called when a new round starts. Called NUM_ROUNDS times.
 *
 * @param game_state Pointer to the GameState object.
 * @param round_state Pointer to the RoundState object.
 * @param active Your player's index.
 */
void Player::handle_new_round(GameState* game_state, RoundState* round_state, int active)
{
    //int my_bankroll = game_state->bankroll;  // the total number of chips you've gained or lost from the beginning of the game to the start of this round
    //float game_clock = game_state->game_clock;  // the total number of seconds your bot has left to play this game
    //int round_num = game_state->round_num;  // the round number from 1 to NUM_ROUNDS
    //std::array<std::string, 2> my_cards = round_state->hands[active];  // your cards
    //bool big_blind = (bool) active;  // true if you are the big blind
}

/**
 * Called when a round ends. Called NUM_ROUNDS times.
 *
 * @param game_state Pointer to the GameState object.
 * @param terminal_state Pointer to the TerminalState object.
 * @param active Your player's index.
 */
void Player::handle_round_over(GameState* game_state, TerminalState* terminal_state, int active)
{
    //int my_delta = terminal_state->deltas[active];  // your bankroll change from this round
    //RoundState* previous_state = (RoundState*) terminal_state->previous_state;  // RoundState before payoffs
    //int street = previous_state->street;  // 0, 3, 4, or 5 representing when this round ended
    //std::array<std::string, 2> my_cards = previous_state->hands[active];  // your cards
    //std::array<std::string, 2> opp_cards = previous_state->hands[1-active];  // opponent's cards or "" if not revealed
}

/**
 * Where the magic happens - your code should implement this function.
 * Called any time the engine needs an action from your bot.
 *
 * @param game_state Pointer to the GameState object.
 * @param round_state Pointer to the RoundState object.
 * @param active Your player's index.
 * @return Your action.
 */
Action Player::get_action(GameState* game_state, RoundState* round_state, int active)
{
    int legal_actions = round_state->legal_actions();  // mask representing the actions you are allowed to take
    //int street = round_state->street;  // 0, 3, 4, or 5 representing pre-flop, flop, turn, or river respectively
    //std::array<std::string, 2> my_cards = round_state->hands[active];  // your cards
    //std::array<std::string, 5> board_cards = round_state->deck;  // the board cards
    //int my_pip = round_state->pips[active];  // the number of chips you have contributed to the pot this round of betting
    //int opp_pip = round_state->pips[1-active];  // the number of chips your opponent has contributed to the pot this round of betting
    //int my_stack = round_state->stacks[active];  // the number of chips you have remaining
    //int opp_stack = round_state->stacks[1-active];  // the number of chips your opponent has remaining
    //int continue_cost = opp_pip - my_pip;  // the number of chips needed to stay in the pot
    //int my_contribution = STARTING_STACK - my_stack;  // the number of chips you have contributed to the pot
    //int opp_contribution = STARTING_STACK - opp_stack;  // the number of chips your opponent has contributed to the pot
    //if (RAISE_ACTION_TYPE & legal_actions)
    //{
    //    std::array<int, 2> raise_bounds = round_state->raise_bounds();  // the smallest and largest numbers of chips for a legal bet/raise
    //    int min_cost = raise_bounds[0] - my_pip;  // the cost of a minimum bet/raise
    //    int max_cost = raise_bounds[1] - my_pip;  // the cost of a maximum bet/raise
    //}
    if (CHECK_ACTION_TYPE & legal_actions)  // check-call
    {
        return CheckAction();
    }
    return CallAction();
}