#pragma once

#include <iostream>
#include <memory>
#include <unordered_set>

#include "actions.h"
#include "constants.h"

namespace pokerbots::skeleton {

struct State : public std::enable_shared_from_this<State> {

  virtual ~State() = default;

  friend std::ostream &operator<<(std::ostream &os, const State &s) {
    return s.doFormat(os);
  }

  template <typename Desired = State>
  std::shared_ptr<const Desired> getShared() const {
    return std::static_pointer_cast<const Desired>(shared_from_this());
  }

private:
  virtual std::ostream &doFormat(std::ostream &os) const = 0;
};

using StatePtr = std::shared_ptr<const State>;

struct BoardState : public State {
  int pot;
  std::array<Pip, 2> pips;
  std::array<std::array<Card, 2>, 2> hands;
  std::array<Card, 5> deck;
  StatePtr previousState;
  bool settled;

  BoardState(int pot, std::array<Pip, 2> pips,
             std::array<std::array<Card, 2>, 2> hands, std::array<Card, 5> deck,
             StatePtr previousState, bool settled = false)
      : pot(pot), pips(std::move(pips)), hands(std::move(hands)),
        deck(std::move(deck)), previousState(std::move(previousState)),
        settled(settled) {}

  StatePtr showdown() const;

  std::unordered_set<Action::Type>
  legalActions(int button, const std::array<int, 2> &stacks) const;

  RaiseBounds raiseBounds(int button, const std::array<int, 2> &stacks) const;

  StatePtr proceed(Action action, int button, int street) const;

private:
  std::ostream &doFormat(std::ostream &os) const override;
};

using BoardStatePtr = std::shared_ptr<const BoardState>;

struct RoundState : public State {
  int button;
  int street;
  std::array<int, 2> stacks;
  std::array<std::array<Card, 2 * NUM_BOARDS>, 2> hands;
  std::array<StatePtr, NUM_BOARDS> boardStates;
  StatePtr previousState;

  RoundState(int button, int street, std::array<int, 2> stacks,
             std::array<std::array<Card, 2 * NUM_BOARDS>, 2> hands,
             std::array<StatePtr, NUM_BOARDS> boardStates,
             StatePtr previousState)
      : button(button), street(street), stacks(std::move(stacks)),
        hands(std::move(hands)), boardStates(std::move(boardStates)),
        previousState(std::move(previousState)) {}

  StatePtr showdown() const;

  std::array<std::unordered_set<Action::Type>, NUM_BOARDS> legalActions() const;

  RaiseBounds raiseBounds() const;

  StatePtr proceedStreet() const;

  StatePtr proceed(const std::array<Action, NUM_BOARDS> &actions) const;

private:
  std::ostream &doFormat(std::ostream &os) const override;
};

using RoundStatePtr = std::shared_ptr<const RoundState>;

struct TerminalState : public State {
  Deltas deltas;
  StatePtr previousState;

  TerminalState(Deltas deltas, StatePtr previousState)
      : deltas(std::move(deltas)), previousState(std::move(previousState)) {}

private:
  std::ostream &doFormat(std::ostream &os) const override;
};

using TerminalStatePtr = std::shared_ptr<const TerminalState>;

inline int getActive(int a) {
  auto active = a % 2;
  return active < 0 ? active + 2 : active;
}

} // namespace pokerbots::skeleton
