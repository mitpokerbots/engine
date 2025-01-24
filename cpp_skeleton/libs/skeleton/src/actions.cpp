#include "skeleton/actions.h"

namespace pokerbots::skeleton {

std::ostream &operator<<(std::ostream &os, const Action &a) {
  switch (a.actionType) {
  case Action::Type::FOLD:
    return os << 'F';
  case Action::Type::CALL:
    return os << 'C';
  case Action::Type::CHECK:
    return os << 'K';
  default:
    return os << 'R' << a.amount;
  }
}

} // namespace pokerbots::skeleton
