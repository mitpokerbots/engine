#pragma once

#include <memory>

namespace pokerbots::skeleton {

struct GameInfo {
  int bankroll;
  int oppBankroll;
  double gameClock;
  int roundNum;

  GameInfo(int bankroll, int oppBankroll, double gameClock, int roundNum)
      : bankroll(bankroll), oppBankroll(oppBankroll), gameClock(gameClock),
        roundNum(roundNum) {}
};

using GameInfoPtr = std::shared_ptr<const GameInfo>;

} // namespace pokerbots::skeleton
