#include <skeleton/actions.h>
#include <skeleton/constants.h>
#include <skeleton/runner.h>
#include <skeleton/states.h>

using namespace pokerbots::skeleton;

struct Bot {
  void handleNewRound(GameInfoPtr gameState, RoundStatePtr roundState, int active) {}

  void handleRoundOver(GameInfoPtr gameState, TerminalStatePtr terminalState, int active) {}
  
  Action getAction(GameInfoPtr gameState, RoundStatePtr roundState, int active) {
    auto legalActions = roundState->legalActions();
    if (legalActions.find(Action::Type::CHECK) != legalActions.end()) {
      return {Action::Type::CHECK};
    }
    return {Action::Type::CALL};
  }
};

int main(int argc, char *argv[]) {
  auto [host, port] = parseArgs(argc, argv);
  runBot<Bot>(host, port);
  return 0;
}
