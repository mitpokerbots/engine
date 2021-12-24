#pragma once

#include <array>
#include <string>
#include <utility>

namespace pokerbots::skeleton {

inline constexpr int NUM_ROUNDS = 1000;
inline constexpr int STARTING_STACK = 200;
inline constexpr int BIG_BLIND = 2;
inline constexpr int SMALL_BLIND = 1;
inline constexpr int NUM_BOARDS = 3;

using Card = std::string;
using Pip = int;
using RaiseBounds = std::array<int, 2>;
using Deltas = std::array<int, 2>;

} // namespace pokerbots::skeleton
