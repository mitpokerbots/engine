#include <skeleton/actions.h>
#include <skeleton/constants.h>
#include <skeleton/runner.h>
#include <skeleton/states.h>

using namespace pokerbots::skeleton;

struct Bot {
  void handleNewRound(GameInfoPtr gameState, RoundStatePtr roundState, int active) {}

  void handleRoundOver(GameInfoPtr gameState, TerminalStatePtr terminalState, int active) {}
  
  /*
    Where the magic happens - your code should implement this function.
    Called any time the engine needs an action from your bot.

    @param gameState The GameState object.
    @param roundState The RoundState object.
    @param active Your player's index.
    @return Your action.
  */
  Action getAction(GameInfoPtr gameState, RoundStatePtr roundState, int active) {
    auto legalActions = roundState->legalActions();  // the actions you are allowed to take
    // int street = roundState->street;  // 0, 3, 4, or 5 representing pre-flop, flop, turn, or river respectively
    // auto myCards = roundState->hands[active];  // your cards
    // auto boardCards = roundState->deck;  // the board cards
    // int myPip = roundState->pips[active];  // the number of chips you have contributed to the pot this round of betting
    // int oppPip = roundState->pips[1-active];  // the number of chips your opponent has contributed to the pot this round of betting
    // int myStack = roundState->stacks[active];  // the number of chips you have remaining
    // int oppStack = roundState->stacks[1-active];  // the number of chips your opponent has remaining
    // int continueCost = oppPip - myPip;  // the number of chips needed to stay in the pot
    // int myContribution = STARTING_STACK - myStack;  // the number of chips you have contributed to the pot
    // int oppContribution = STARTING_STACK - oppStack;  // the number of chips your opponent has contributed to the pot
    // if (legalActions.find(Action::Type::RAISE) != legalActions.end()) {
    //   auto raiseBounds = roundState->raiseBounds();  // the smallest and largest numbers of chips for a legal bet/raise
    //   int minCost = raiseBounds[0] - myPip;  // the cost of a minimum bet/raise
    //   int maxCost = raiseBounds[1] - myPip;  // the cost of a maximum bet/raise
    // }
    if (legalActions.find(Action::Type::CHECK) != legalActions.end()) {  // check-call
      return {Action::Type::CHECK};
    }
    return {Action::Type::CALL};
  }
};

/*
  Main program for running a C++ pokerbot.
*/
int main(int argc, char *argv[]) {
  auto [host, port] = parseArgs(argc, argv);
  runBot<Bot>(host, port);
  return 0;
}
