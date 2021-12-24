#include "skeleton/actions.h"

#include <fmt/format.h>
#include <fmt/ostream.h>

namespace pokerbots::skeleton {

std::ostream &operator<<(std::ostream &os, const Action &a) {
  switch (a.actionType) {
  case Action::Type::ASSIGN:
    fmt::print(os, FMT_STRING("A{}"),
               fmt::join(a.cards.begin(), a.cards.end(), ","));
    return os;
  case Action::Type::FOLD:
    return os << 'F';
  case Action::Type::CALL:
    return os << 'C';
  case Action::Type::CHECK:
    return os << 'K';
  default:
    fmt::print(os, FMT_STRING("R{}"), a.amount);
    return os;
  }
}

} // namespace pokerbots::skeleton
