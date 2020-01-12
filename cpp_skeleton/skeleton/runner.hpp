#ifndef __SKELETON_RUNNER_HPP__
#define __SKELETON_RUNNER_HPP__

#include <iostream>
#include <vector>
#include <array>
#include <string>
#include <boost/algorithm/string.hpp>
#include <boost/asio/ip/tcp.hpp>
#include "actions.hpp"
#include "states.hpp"
#include "bot.hpp"

using std::vector;
using std::array;
using std::string;
using boost::asio::ip::tcp;


/**
 * Interacts with the engine.
 */
class Runner
{
    private:
        Bot* pokerbot;
        tcp::iostream* stream;

    public:
        Runner(Bot* pokerbot, tcp::iostream* stream);

        /**
         * Returns an incoming message from the engine.
         */
        vector<string> receive();

        /**
         * Encodes an action and sends it to the engine.
         */
        void send(Action action);

        /**
         * Reconstructs the game tree based on the action history received from the engine.
         */
        void run();
};


/**
 * Parses arguments corresponding to socket connection information.
 */
vector<string> parse_args(int argc, char* argv[]);

/**
 * Runs the pokerbot.
 */
void run_bot(Bot* pokerbot, vector<string> args);

#endif  // __SKELETON_RUNNER_HPP__