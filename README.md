# DevNet.CSU Pokerbots

Starter kit for the DevNet.CSU Pokerbots tournament. Your team writes a Python bot that plays heads-up No-Limit Texas Hold'em, and bots play each other in duplicate matches of two 3,000-hand games. The full rules, schedule, and scoring are in the [participant guide](docs/participant-guide.pdf).

## Quick start

You need Python 3.12, which is the version the official machine uses. (Use 3.12, not 3.13: eval7 only publishes Windows and macOS installers up to Python 3.12.)

```
git clone https://github.com/kacperm37/devnet-pokerbots.git
cd devnet-pokerbots
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 engine.py
```

That plays a 3,000-hand game between two copies of the starter bot and writes `gamelog.txt`. On Windows, create the environment with `py -3.12 -m venv .venv`, and use `python` wherever this README says `python3`.

## Make your bot

1. Copy `python_skeleton/` to a new folder, for example `my_bot/`.
2. Write your strategy in `my_bot/player.py`. Leave `my_bot/skeleton/` unchanged.
3. In `config.py`, point `PLAYER_1_PATH` at `./my_bot` and `PLAYER_2_PATH` at a house bot, then run `python3 engine.py`.
4. Before every submission, run the self-check:

   ```
   python3 check_bot.py my_bot
   ```

   It plays 100 hands against a house bot under the official settings, from a read-only copy of your folder, and reports crashes, illegal actions, unapproved libraries, and how much of your clock you'd use. Add `--opponent house_bots/monte_carlo` or `--hands 500` to change the test.

## What's here

| Path | What it is |
| --- | --- |
| `engine.py`, `config.py` | The engine. `config.py` is set to the official settings; change them freely while testing. |
| `python_skeleton/` | The starter bot. It always checks or calls. Copy this folder to start your bot. |
| `house_bots/` | Three sample opponents, from weakest to strongest: `calling_station`, `rule_book`, and `monte_carlo`. Read their code for ideas. |
| `check_bot.py` | The self-check. |
| `docs/participant-guide.pdf` | Rules, scoring, schedule, and conduct. |
| `organizer/` | The tournament runner and sandbox, used by the organizer. You don't need it, but you're welcome to read it. |

## Reading `gamelog.txt`

- `Round #12, A (40), B (-40)`: each bot's net chips before hand 12. The button is listed first.
- `Flop [3h 5h Jc], A (6), B (6)`: chips each bot has put into the pot so far this hand.
- `A awarded 6`: what each bot won or lost on the hand.
- `Final, A (812), B (-812)`: net chips for the whole game.

Anything your bot prints goes to `A.txt` or `B.txt`, named after the players in `config.py`.

## On the official machine

Your bot runs in its own container with 1 CPU core, 2 GB of memory, no network, and a read-only copy of your folder. It's started with `python3 player.py` (your `commands.json` is ignored) and gets a 180-second clock for each 3,000-hand game. It can learn about its opponent in memory during a game, but nothing carries over between games.

## Credits

Built on the [MIT Pokerbots](https://github.com/mitpokerbots/engine) reference engine and Python skeleton, with changes for this tournament. Hand evaluation uses [eval7](https://github.com/julianandrews/pyeval7).
