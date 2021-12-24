#include <skeleton/actions.h>
#include <skeleton/constants.h>
#include <skeleton/runner.h>
#include <skeleton/states.h>

using namespace pokerbots::skeleton;

struct Bot {
  void handleNewRound(GameInfoPtr gameState, RoundStatePtr roundState,
                      int active) {}
  void handleRoundOver(GameInfoPtr gameState, TerminalStatePtr terminalState,
                       int active) {}
  std::vector<Action> getActions(GameInfoPtr gameState,
                                 RoundStatePtr roundState, int active) {
    auto legalActions = roundState->legalActions();
    auto myCards = roundState->hands[active];
    std::vector<Action> myActions;
    for (int i = 0; i < NUM_BOARDS; ++i) {
      if (legalActions[i].find(Action::Type::ASSIGN) != legalActions[i].end()) {
        myActions.emplace_back(
            Action::Type::ASSIGN,
            std::array<Card, 2>{myCards[2 * i], myCards[2 * i + 1]});
      } else if (legalActions[i].find(Action::Type::CHECK) !=
                 legalActions[i].end()) {
        myActions.emplace_back(Action::Type::CHECK);
      } else {
        myActions.emplace_back(Action::Type::CALL);
      }
    }
    return myActions;
  }
};

int main(int argc, char *argv[]) {
  auto [host, port] = parseArgs(argc, argv);
  runBot<Bot>(host, port);
  return 0;
}
