#include "skeleton/states.h"

#include <algorithm>
#include <numeric>

#include <fmt/format.h>
#include <fmt/ostream.h>

#include "skeleton/util.h"

namespace pokerbots::skeleton {

StatePtr BoardState::showdown() const {
  return std::make_shared<TerminalState>(Deltas{}, getShared());
}

std::unordered_set<Action::Type>
BoardState::legalActions(int button, const std::array<int, 2> &stacks) const {
  auto active = getActive(button);

  if (isEmpty(hands[active]))
    return {Action::Type::ASSIGN};
  else if (settled)
    return {Action::Type::CHECK};

  auto continueCost = pips[1 - active] - pips[active];
  if (continueCost == 0) {
    auto betsForbidden = stacks[0] == 0 || stacks[1] == 0;
    return betsForbidden ? std::unordered_set<Action::Type>{Action::Type::CHECK}
                         : std::unordered_set<Action::Type>{
                               Action::Type::CHECK, Action::Type::RAISE};
  }

  auto raisesForbidden = continueCost == stacks[0] || continueCost == stacks[1];
  return raisesForbidden
             ? std::unordered_set<Action::Type>{Action::Type::FOLD,
                                                Action::Type::CALL}
             : std::unordered_set<Action::Type>{
                   Action::Type::FOLD, Action::Type::CALL, Action::Type::RAISE};
}

RaiseBounds BoardState::raiseBounds(int button,
                                    const std::array<int, 2> &stacks) const {
  auto active = getActive(button);

  auto continueCost = pips[1 - active] - pips[active];
  auto maxContribution =
      std::min(stacks[active], stacks[1 - active] + continueCost);
  auto minContribution = std::min(
      maxContribution, continueCost + std::max(continueCost, BIG_BLIND));
  return {pips[active] + minContribution, pips[active] + maxContribution};
}

StatePtr BoardState::proceed(Action action, int button, int street) const {
  auto active = getActive(button);

  switch (action.actionType) {
  case Action::Type::ASSIGN: {
    std::array<std::array<Card, 2>, 2> newHands;
    newHands[active] = action.cards;
    if (!isEmpty(hands[1-active])) {
      newHands[1-active] = hands[1-active];
    }
    return std::make_shared<BoardState>(pot, pips, std::move(newHands), deck,
                                        getShared());
  }
  case Action::Type::FOLD: {
    auto newPot = pot + std::accumulate(pips.begin(), pips.end(), 0);
    Deltas winnings = {active == 0 ? 0 : newPot, active == 0 ? newPot : 0};
    return std::make_shared<TerminalState>(
        std::move(winnings),
        std::make_shared<BoardState>(newPot, std::array<Pip, 2>(), hands, deck,
                                     getShared(), true));
  }
  case Action::Type::CALL: {
    if (button == 0)
      return std::make_shared<BoardState>(
          pot, std::array<Pip, 2>{BIG_BLIND, BIG_BLIND}, hands, deck,
          getShared());

    auto newPips = pips;
    auto contribution = newPips[1 - active] - newPips[active];
    newPips[active] = newPips[active] + contribution;
    return std::make_shared<BoardState>(pot, std::move(newPips), hands, deck,
                                        getShared(), true);
  }
  case Action::Type::CHECK:
    if ((street == 0 && button > 0) || button > 1)
      return std::make_shared<BoardState>(pot, pips, hands, deck, getShared(),
                                          true);
    return std::make_shared<BoardState>(pot, pips, hands, deck, getShared(),
                                        settled);
  default: {
    auto newPips = pips;
    auto contribution = action.amount - newPips[active];
    newPips[active] = newPips[active] + contribution;
    return std::make_shared<BoardState>(pot, std::move(newPips), hands, deck,
                                        getShared());
  }
  }
}

std::ostream &BoardState::doFormat(std::ostream &os) const {
  std::array<std::string, 2> formattedHands = {
      fmt::format(FMT_STRING("{}"),
                  fmt::join(hands[0].begin(), hands[0].end(), "")),
      fmt::format(FMT_STRING("{}"),
                  fmt::join(hands[1].begin(), hands[1].end(), ""))};

  fmt::print(os,
             FMT_STRING("board(pot={}, pips=[{}], hands=[{}], deck=[{}], "
                        "settled={})"),
             pot, fmt::join(pips.begin(), pips.end(), ", "),
             fmt::join(formattedHands.begin(), formattedHands.end(), ", "),
             fmt::join(deck.begin(), deck.end(), ", "), settled);
  return os;
}

StatePtr RoundState::showdown() const {
  std::array<StatePtr, NUM_BOARDS> terminalBoardStates;
  for (auto i = 0; i < boardStates.size(); ++i) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(boardStates[i]))
      terminalBoardStates[i] = bs->showdown();
    else
      terminalBoardStates[i] = boardStates[i];
  }
  return std::make_shared<TerminalState>(
      Deltas{}, std::make_shared<RoundState>(button, street, stacks, hands,
                                             std::move(terminalBoardStates),
                                             getShared()));
}

std::array<std::unordered_set<Action::Type>, NUM_BOARDS>
RoundState::legalActions() const {
  std::array<std::unordered_set<Action::Type>, NUM_BOARDS> output;
  for (auto i = 0; i < boardStates.size(); ++i) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(boardStates[i]))
      output[i] = bs->legalActions(button, stacks);
    else
      output[i] = {Action::Type::CHECK};
  }
  return output;
}

RaiseBounds RoundState::raiseBounds() const {
  auto active = getActive(button);

  auto netContinueCost = 0;
  auto netPipsUnsettled = 0;

  for (auto &s : boardStates) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(s))
      if (!bs->settled) {
        netContinueCost += bs->pips[1 - active] - bs->pips[active];
        netPipsUnsettled += bs->pips[active];
      }
  }

  return {0, netPipsUnsettled + std::min(stacks[active],
                                         stacks[1 - active] + netContinueCost)};
}

StatePtr RoundState::proceedStreet() const {
  std::array<int, NUM_BOARDS> newPots = {0};
  for (auto i = 0; i < NUM_BOARDS; ++i) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(boardStates[i])) {
      newPots[i] =
          bs->pot + std::accumulate(bs->pips.begin(), bs->pips.end(), 0);
    }
  }

  std::array<StatePtr, NUM_BOARDS> newBoardStates;
  for (auto i = 0; i < NUM_BOARDS; ++i) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(boardStates[i])) {
      newBoardStates[i] =
          std::make_shared<BoardState>(newPots[i], std::array<int, 2>(),
                                       bs->hands, bs->deck, boardStates[i]);
    } else {
      newBoardStates[i] = boardStates[i];
    }
  }

  bool allTerminal =
      std::all_of(newBoardStates.begin(), newBoardStates.end(), [](auto &v) {
        return bool(std::dynamic_pointer_cast<const TerminalState>(v));
      });

  if (street == 5 || allTerminal)
    return std::make_shared<RoundState>(button, 5, stacks, hands,
                                        std::move(newBoardStates), getShared())
        ->showdown();

  auto newStreet = street == 0 ? 3 : street + 1;
  return std::make_shared<RoundState>(1, newStreet, stacks, hands,
                                      std::move(newBoardStates), getShared());
}

StatePtr
RoundState::proceed(const std::array<Action, NUM_BOARDS> &actions) const {
  std::array<StatePtr, NUM_BOARDS> newBoardStates;
  for (auto i = 0; i < NUM_BOARDS; ++i) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(boardStates[i])) {
      newBoardStates[i] = bs->proceed(actions[i], button, street);
    } else {
      newBoardStates[i] = boardStates[i];
    }
  }

  auto active = getActive(button);

  auto newStacks = stacks;
  auto contribution = 0;

  for (auto i = 0; i < NUM_BOARDS; ++i)
    if (auto bs =
            std::dynamic_pointer_cast<const BoardState>(newBoardStates[i]))
      if (auto s = std::dynamic_pointer_cast<const BoardState>(boardStates[i]))
        contribution += bs->pips[active] - s->pips[active];

  newStacks[active] = newStacks[active] - contribution;

  std::array<bool, NUM_BOARDS> settled = {};
  for (auto i = 0; i < NUM_BOARDS; ++i) {
    if (auto bs = std::dynamic_pointer_cast<const BoardState>(newBoardStates[i]))
      settled[i] = bs->settled;
    else
      settled[i] = true;
  }

  auto state = std::make_shared<RoundState>(
      button + 1, street, std::move(newStacks), hands,
      std::move(newBoardStates), getShared());

  if (std::all_of(settled.begin(), settled.end(), [](auto v) { return v; })) {
    return state->proceedStreet();
  } else {
    return state;
  }
}

std::ostream &RoundState::doFormat(std::ostream &os) const {
  std::array<std::string, NUM_BOARDS> formattedBoards;
  for (auto i = 0; i < NUM_BOARDS; ++i)
    formattedBoards[i] = fmt::format(FMT_STRING("{}"), *boardStates[i]);

  std::array<std::string, 2> formattedHands = {
      fmt::format(FMT_STRING("{}"),
                  fmt::join(hands[0].begin(), hands[0].end(), "")),
      fmt::format(FMT_STRING("{}"),
                  fmt::join(hands[1].begin(), hands[1].end(), ""))};

  fmt::print(os,
             FMT_STRING("round(button={}, street={}, stacks=[{}], hands=[{}], "
                        "boardStates=[{}])"),
             button, street, fmt::join(stacks.begin(), stacks.end(), ", "),
             fmt::join(formattedHands.begin(), formattedHands.end(), ","),
             fmt::join(formattedBoards.begin(), formattedBoards.end(), ", "));
  return os;
}

std::ostream &TerminalState::doFormat(std::ostream &os) const {
  fmt::print(os, FMT_STRING("terminal(deltas=[{}])"),
             fmt::join(deltas.begin(), deltas.end(), ", "));
  return os;
}

} // namespace pokerbots::skeleton
