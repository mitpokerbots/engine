#pragma once

#include <iostream>

#include "constants.h"

namespace pokerbots::skeleton {

struct Action {
  enum Type { FOLD, CALL, CHECK, RAISE, ASSIGN };

  Type actionType;
  int amount;
  std::array<Card, 2> cards;

  Action(Type t = Type::CHECK, int a = 0) : actionType(t), amount(a) {}

  Action(Type t, std::array<Card, 2> cards)
      : actionType(t), amount(0), cards(std::move(cards)) {}

  friend std::ostream &operator<<(std::ostream &os, const Action &a);
};

} // namespace pokerbots::skeleton
