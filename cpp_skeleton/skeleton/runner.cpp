/**
 * The infrastructure for interacting with the engine.
 */
#include "runner.hpp"

Runner::Runner(Bot* pokerbot, tcp::iostream* stream)
{
    this->pokerbot = pokerbot;
    this->stream = stream;
}

/**
 * Returns an incoming message from the engine.
 */
vector<string> Runner::receive()
{
    string line;
    std::getline(*(this->stream), line);
    boost::algorithm::trim(line);
    vector<string> packet;
    boost::split(packet, line, boost::is_any_of(" "));
    return packet;
}

/**
 * Encodes an action and sends it to the engine.
 */
void Runner::send(Action action)
{
    string code;
    switch (action.action_type)
    {
        case FOLD_ACTION_TYPE:
        {
            code = "F";
            break;
        }
        case CALL_ACTION_TYPE:
        {
            code = "C";
            break;
        }
        case CHECK_ACTION_TYPE:
        {
            code = "K";
            break;
        }
        default:  // RAISE_ACTION_TYPE
        {
            code = "R" + std::to_string(action.amount);
            break;
        }
    }
    *(this->stream) << code << "\n";
}

/**
 * Reconstructs the game tree based on the action history received from the engine.
 */
void Runner::run()
{
    GameState* game_state = new GameState(0, 0., 1);
    State* round_state;
    int active = 0;
    bool round_flag = true;
    while (true)
    {
        vector<string> packet = this->receive();
        for (string clause : packet)
        {
            string leftover = clause.substr(1, clause.size() - 1);
            switch (clause.at(0))
            {
                case 'T':
                {
                    GameState* freed_game_state = game_state;
                    game_state = new GameState(game_state->bankroll, std::stof(leftover), game_state->round_num);
                    delete freed_game_state;
                    break;
                }
                case 'P':
                {
                    active = std::stoi(leftover);
                    break;
                }
                case 'H':
                {
                    vector<string> cards;
                    boost::split(cards, leftover, boost::is_any_of(","));
                    array< array<string, 2>, 2> hands = { "" };
                    hands[active] = (array<string, 2>) { cards[0], cards[1] };
                    array<string, 5> deck = { "" };
                    array<int, 2> pips = { SMALL_BLIND, BIG_BLIND };
                    array<int, 2> stacks = { STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND };
                    round_state = new RoundState(0, 0, pips, stacks, hands, deck, NULL);
                    if (round_flag)
                    {
                        this->pokerbot->handle_new_round(game_state, (RoundState*) round_state, active);
                        round_flag = false;
                    }
                    break;
                }
                case 'F':
                {
                    round_state = ((RoundState*) round_state)->proceed(FoldAction());
                    break;
                }
                case 'C':
                {
                    round_state = ((RoundState*) round_state)->proceed(CallAction());
                    break;
                }
                case 'K':
                {
                    round_state = ((RoundState*) round_state)->proceed(CheckAction());
                    break;
                }
                case 'R':
                {
                    round_state = ((RoundState*) round_state)->proceed(RaiseAction(std::stoi(leftover)));
                    break;
                }
                case 'B':
                {
                    vector<string> cards;
                    boost::split(cards, leftover, boost::is_any_of(","));
                    array<string, 5> revised_deck = { "" };
                    for (unsigned int i = 0; i < cards.size(); i++)
                    {
                        revised_deck[i] = cards[i];
                    }
                    RoundState* maker = (RoundState*) round_state;
                    round_state = new RoundState(maker->button, maker->street, maker->pips, maker->stacks,
                                                 maker->hands, revised_deck, maker->previous_state);
                    delete maker;
                    break;
                }
                case 'O':
                {
                    // backtrack
                    vector<string> cards;
                    boost::split(cards, leftover, boost::is_any_of(","));
                    TerminalState* freed_terminal_state = (TerminalState*) round_state;
                    round_state = freed_terminal_state->previous_state;
                    delete freed_terminal_state;
                    RoundState* maker = (RoundState*) round_state;
                    array< array<string, 2>, 2> revised_hands = maker->hands;
                    revised_hands[1-active] = (array<string, 2>) { cards[0], cards[1] };
                    // rebuild history
                    round_state = new RoundState(maker->button, maker->street, maker->pips, maker->stacks,
                                                 revised_hands, maker->deck, maker->previous_state);
                    delete maker;
                    round_state = new TerminalState((array<int, 2>) { 0, 0 }, round_state);
                    break;
                }
                case 'D':
                {
                    int delta = std::stoi(leftover);
                    array<int, 2> deltas = { -1 * delta, -1 * delta };
                    deltas[active] = delta;
                    TerminalState* freed_terminal_state = (TerminalState*) round_state;
                    round_state = new TerminalState(deltas, freed_terminal_state->previous_state);
                    delete freed_terminal_state;
                    GameState* freed_game_state = game_state;
                    game_state = new GameState(game_state->bankroll + delta, game_state->game_clock, game_state->round_num);
                    delete freed_game_state;
                    this->pokerbot->handle_round_over(game_state, (TerminalState*) round_state, active);
                    freed_game_state = game_state;
                    game_state = new GameState(game_state->bankroll, game_state->game_clock, game_state->round_num + 1);
                    delete freed_game_state;
                    freed_terminal_state = (TerminalState*) round_state;
                    round_state = freed_terminal_state->previous_state;
                    delete freed_terminal_state;
                    // delete all the RoundState objects
                    while (round_state != NULL)
                    {
                        RoundState* freed_round_state = (RoundState*) round_state;
                        round_state = freed_round_state->previous_state;
                        delete freed_round_state;
                    }
                    round_flag = true;
                    break;
                }
                case 'Q':
                {
                    delete game_state;
                    return;
                }
                default:
                {
                    break;
                }
            }
        }
        if (round_flag)  // ack the engine
        {
            this->send(CheckAction());
        }
        else
        {
            Action action = this->pokerbot->get_action(game_state, (RoundState*) round_state, active);
            this->send(action);
        }
    }
}

/**
 * Parses arguments corresponding to socket connection information.
 */
vector<string> parse_args(int argc, char* argv[])
{
    string host = "localhost";
    int port;

    bool host_flag = false;
    for (int i = 1; i < argc; i++)
    {
        string arg(argv[i]);
        if ((arg == "-h") | (arg == "--host"))
        {
            host_flag = true;
        }
        else if (arg == "--port")
        {
            // nothing to do
        }
        else if (host_flag)
        {
            host = arg;
            host_flag = false;
        }
        else
        {
            port = std::stoi(arg);
        }
    }

    return (vector<string>) { host, std::to_string(port) };
}

/**
 * Runs the pokerbot.
 */
void run_bot(Bot* pokerbot, vector<string> args)
{
    string host = args[0];
    string port = args[1];
    // connect to the engine
    tcp::iostream stream;
    stream.connect(host, port);
    // set TCP_NODELAY on the stream
    tcp::no_delay option(true);
    stream.rdbuf()->set_option(option);
    if (!stream) {
        std::cout << "Could not connect to " << host << ":" << port << "\n";
        return;
    }
    Runner runner(pokerbot, &stream);
    runner.run();
    stream.close();
}