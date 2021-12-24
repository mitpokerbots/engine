#pragma once

#include <charconv>
#include <iostream>
#include <optional>
#include <string>
#include <utility>

#include <boost/algorithm/string.hpp>
#include <boost/asio/ip/tcp.hpp>

#include <fmt/format.h>
#include <fmt/ostream.h>

#include "actions.h"
#include "constants.h"
#include "game.h"
#include "states.h"

namespace pokerbots::skeleton {

template <typename BotType> class Runner {
private:
  BotType pokerbot;
  boost::asio::ip::tcp::iostream &stream;

  StatePtr parseMultiCode(const std::string &clause, StatePtr roundState,
                          int active) {
    std::vector<std::string> subclauses;
    boost::split(subclauses, clause, boost::is_any_of(";"));

    auto contains = [](const std::string &s, const std::string &sub) -> bool {
      return s.find(sub) != std::string::npos;
    };

    if (contains(clause, "B")) {
      std::array<StatePtr, NUM_BOARDS> newBoardStates;
      for (auto i = 0; i < NUM_BOARDS; ++i) {
        auto leftover = subclauses[i].substr(2);

        std::vector<Card> cards;
        boost::split(cards, leftover, boost::is_any_of(","));

        std::array<Card, 5> revisedDeck;
        for (auto j = 0; j < cards.size(); ++j) {
          revisedDeck[j] = cards[j];
        }

        if (auto maker = std::dynamic_pointer_cast<const BoardState>(
                std::static_pointer_cast<const RoundState>(roundState)
                    ->boardStates[i])) {
          newBoardStates[i] = std::make_shared<BoardState>(
              maker->pot, maker->pips, maker->hands, revisedDeck,
              maker->previousState);
        } else {
          auto terminal = std::static_pointer_cast<const TerminalState>(
              std::static_pointer_cast<const RoundState>(roundState)
                  ->boardStates[i]);

          auto newMaker = std::static_pointer_cast<const BoardState>(
              terminal->previousState);

          newBoardStates[i] = std::make_shared<TerminalState>(
              terminal->deltas,
              std::make_shared<BoardState>(
                  newMaker->pot, newMaker->pips, newMaker->hands, revisedDeck,
                  newMaker->previousState, newMaker->settled));
        }
      }
      auto maker = std::static_pointer_cast<const RoundState>(roundState);
      return std::make_shared<RoundState>(
          maker->button, maker->street, maker->stacks, maker->hands,
          std::move(newBoardStates), maker->previousState);
    } else if (contains(clause, "O")) {
      std::array<StatePtr, NUM_BOARDS> newBoardStates;

      roundState = std::static_pointer_cast<const TerminalState>(roundState)
                       ->previousState;
      for (auto i = 0; i < NUM_BOARDS; ++i) {
        auto leftover = subclauses[i].substr(2);

        if (leftover.empty()) {
          newBoardStates[i] =
              std::static_pointer_cast<const RoundState>(roundState)
                  ->boardStates[i];
        } else {
          std::vector<Card> cards;
          boost::split(cards, leftover, boost::is_any_of(","));
          auto terminal = std::static_pointer_cast<const TerminalState>(
              std::static_pointer_cast<const RoundState>(roundState)
                  ->boardStates[i]);
          auto maker = std::static_pointer_cast<const BoardState>(
              terminal->previousState);

          auto revisedHands = maker->hands;
          revisedHands[1 - active] = {cards[0], cards[1]};
          newBoardStates[i] = std::make_shared<TerminalState>(
              terminal->deltas,
              std::make_shared<BoardState>(
                  maker->pot, maker->pips, revisedHands, maker->deck,
                  maker->previousState, maker->settled));
        }
      }

      auto maker = std::static_pointer_cast<const RoundState>(roundState);
      return std::make_shared<TerminalState>(
          Deltas{0, 0},
          std::make_shared<RoundState>(
              maker->button, maker->street, maker->stacks, maker->hands,
              std::move(newBoardStates), maker->previousState));
    } else {
      std::array<Action, NUM_BOARDS> actions;
      for (int i = 0; i < subclauses.size(); ++i) {
        auto &subclause = subclauses[i];
        auto leftover = subclause.substr(2);
        switch (subclause[1]) {
        case 'F':
          actions[i] = {Action::Type::FOLD};
          break;
        case 'C':
          actions[i] = {Action::Type::CALL};
          break;
        case 'K':
          actions[i] = {Action::Type::CHECK};
          break;
        case 'R':
          actions[i] = {Action::Type::RAISE, std::stoi(leftover)};
          break;
        case 'A': {
          std::vector<Card> cards;
          boost::split(cards, leftover, boost::is_any_of(","));

          if (leftover.empty()) {
            actions[i] = {Action::Type::ASSIGN, std::array<Card, 2>{"", ""}};
          } else {
            actions[i] = {Action::Type::ASSIGN, {cards[0], cards[1]}};
          }
          break;
        }
        default:
          break;
        }
      }
      return std::static_pointer_cast<const RoundState>(roundState)
          ->proceed(actions);
    }
  }

  template <typename Container> void send(Container &&actions) {
    std::vector<std::string> codes;
    auto it = actions.begin();
    for (auto i = 0; it != actions.end(); ++i) {
      codes.push_back(fmt::format(FMT_STRING("{}{}"), i + 1, *it));
      ++it;
    }
    stream << fmt::format(FMT_STRING("{}"), fmt::join(codes, ";")) << '\n';
  }

  std::vector<std::string> receive() {
    std::string line;
    std::getline(stream, line);
    boost::algorithm::trim(line);

    std::vector<std::string> packet;
    boost::split(packet, line, boost::is_any_of(" "));
    return packet;
  }

public:
  template <typename... Args>
  Runner(boost::asio::ip::tcp::iostream &stream, Args... args)
      : pokerbot(std::forward<Args>(args)...), stream(stream) {}

  ~Runner() { stream.close(); }

  void run() {
    GameInfoPtr gameInfo = std::make_shared<GameInfo>(0, 0, 0.0, 1);
    std::array<StatePtr, NUM_BOARDS> boardStates;
    for (int i = 0; i < NUM_BOARDS; i++) {
      boardStates[i] = std::make_shared<BoardState>(
          (i + 1) * BIG_BLIND, std::array<int, 2>{0},
          std::array<std::array<std::string, 2>, 2>{}, std::array<Card, 5>{},
          nullptr);
    }
    StatePtr roundState = std::make_shared<RoundState>(
        -2, 0, std::array<int, 2>{0},
        std::array<std::array<Card, 2 * NUM_BOARDS>, 2>{}, boardStates,
        nullptr);

    int active = 0;
    bool roundFlag = true;

    while (true) {
      auto packets = receive();

      for (const auto &clause : packets) {
        auto leftovers = clause.substr(1);
        switch (clause[0]) {
        case 'T':
          gameInfo = std::make_shared<GameInfo>(
              gameInfo->bankroll, gameInfo->oppBankroll, std::stof(leftovers),
              gameInfo->roundNum);
          break;
        case 'P':
          active = std::stoi(leftovers);
          break;
        case 'H': {
          std::vector<Card> cards;
          boost::split(cards, leftovers, boost::is_any_of(","));

          std::array<std::array<Card, 2 * NUM_BOARDS>, 2> hands;
          for (int i = 0; i < cards.size(); ++i)
            hands[active][i] = cards[i];

          std::array<Card, 5> deck;
          std::array<Pip, 2> pips = {SMALL_BLIND, BIG_BLIND};

          for (auto i = 0; i < NUM_BOARDS; ++i) {
            boardStates[i] = std::make_shared<BoardState>(
                (i + 1) * BIG_BLIND, pips, std::array<std::array<Card, 2>, 2>{},
                deck, nullptr);
          }

          std::array<int, 2> stacks = {
              STARTING_STACK - (SMALL_BLIND * NUM_BOARDS),
              STARTING_STACK - (BIG_BLIND * NUM_BOARDS)};
          roundState = std::make_shared<RoundState>(
              -2, 0, std::move(stacks), std::move(hands), boardStates, nullptr);

          if (roundFlag) {
            pokerbot.handleNewRound(
                gameInfo,
                std::static_pointer_cast<const RoundState>(roundState), active);
            roundFlag = false;
          }
          break;
        }
        case 'D': {
          std::vector<std::string> subclauses;
          boost::split(subclauses, clause, boost::is_any_of(";"));

          auto delta = std::stoi(subclauses[0].substr(1));
          int oppDelta = std::stoi(subclauses[1].substr(1));

          std::array<int, 2> deltas;
          deltas[active] = delta;
          deltas[1 - active] = oppDelta;

          roundState = std::make_shared<TerminalState>(
              std::move(deltas),
              std::static_pointer_cast<const TerminalState>(roundState)
                  ->previousState);
          gameInfo = std::make_shared<GameInfo>(
              gameInfo->bankroll + delta, gameInfo->oppBankroll + oppDelta,
              gameInfo->gameClock, gameInfo->roundNum);
          pokerbot.handleRoundOver(
              gameInfo,
              std::static_pointer_cast<const TerminalState>(roundState),
              active);
          gameInfo = std::make_shared<GameInfo>(
              gameInfo->bankroll, gameInfo->oppBankroll, gameInfo->gameClock,
              gameInfo->roundNum + 1);
          roundFlag = true;
          break;
        }
        case 'Q':
          return;
        case '1':
          roundState = parseMultiCode(clause, roundState, active);
          break;
        default:
          break;
        }
      }
      if (roundFlag) {
        std::array<Action, NUM_BOARDS> acks;
        for (auto j = 0; j < NUM_BOARDS; ++j) {
          acks[j] = {Action::Type::CHECK};
        }
        send(acks);
      } else {
        send(pokerbot.getActions(
            gameInfo, std::static_pointer_cast<const RoundState>(roundState),
            active));
      }
    }
  }
};

template <typename BotType, typename... Args>
void runBot(std::string &host, std::string &port, Args... args) {
  boost::asio::ip::tcp::iostream stream;
  stream.connect(host, port);
  // set TCP_NODELAY on the stream
  boost::asio::ip::tcp::no_delay option(true);
  stream.rdbuf()->set_option(option);
  if (!stream) {
    fmt::print(std::cerr, FMT_STRING("Unable to connect to {}:{}"), host, port);
    return;
  }

  auto r = Runner<BotType>(stream, std::forward<Args>(args)...);
  r.run();
}

inline std::array<std::string, 2> parseArgs(int argc, char *argv[]) {
  std::string host = "localhost";
  int port;

  bool host_flag = false;
  for (int i = 1; i < argc; i++) {
    std::string arg(argv[i]);
    if ((arg == "-h") | (arg == "--host")) {
      host_flag = true;
    } else if (arg == "--port") {
      // nothing to do
    } else if (host_flag) {
      host = arg;
      host_flag = false;
    } else {
      port = std::stoi(arg);
    }
  }

  return {host, std::to_string(port)};
}

} // namespace pokerbots::skeleton
