# infinite-snake

## Purpose

This is the standard, boring, Snake program that everyone knows.
The intention is not to play it,
but to use it as an example to learn programming from.

## Recommended Actions for snake.py

I suggest you start by playing it a few times.
The basic version is written in Python but it uses the semi-graphic
library _curses_, so it's intended to be used on a UNIX or Linux machine.
If you don't have any and are stuck with Windows, try to install a
virtual machine with Linux on it and run it from there.

After some playing, you'll soon get bored and it's time to take real action!

- Have a look at the source code, just to get an initial idea of its structure.
- If you found any bugs, try to fix them.
- Update the program to the latest version of the programming language.
- Make the source code more compact.
- Improve logging. Perhaps add a switch allowing the user to set the log level.
- Extend the configuration file and/or arguments.
- Add colors and/or fancier graphical symbols.
- Add sound.
- Separate all texts from the source code. Make it possible to select language with a command-line switch.
- Add more snakes on the playground, reading steering input from the net or named pipes etc.
- Add more playgrounds on the display.
- Make it possible for snakes to move between playgrounds.
- Build a real-time high score table in HTML5, CSS3, JavaScript on a separate web page.
- Add a depth dimension so the snakes move in a box of several levels.
- Rewrite the entire program into some other programming language like Kotlin, Go, PHP, C, C++ or JavaScript.
- Convert a the program so it can run on a web page and a smartphone.
- Try some AI - Train a neural network to steer a snake.
- Add autometed tests.
- Implement Docker.
- Make the game public. Allow users to play and charge them some Satoshis via Lightning Network each time.

### Hints

- Since the program enters graphics mode, errors won't be visible. But since they are written to stderr you can redirect them into a separate file. How?
- Analyze the source code with _pylint_ and make that a habit. Start by fixing some of the existing complaints.


## Synopsis

```
./snake.py [-h] [-C cfile] [r rows] [-c cols] [-t to] [-L lf]
           [-P port -H host] [-u user]
           -h: Show this help and exit
           -C: Read configuration from cfile
           -c: Set playground height (including borders)
           -r: Set playground width (including borders)
           -t: Set time in ms between snake steps
           -L: Log to file lf
           -P, -H Connect to server host at given port
           -u: Assign a user nickname (max 16 chars) for score table
```

## Configuration file

With switch `-C` (upper-case C!) you can mention a configuration file from
which `snake.py` shall read its parameters.
Note that if a parameter is given both in the configuration file and as
a CLI option, the last (from left to right) mentioned will take effect.

### Configuration File Syntax

The configuration file must contain one key-value pair per line, which must
begin in the first (leftmost) column. Each key-value pair must be
separated by a colon and a blank. All values are case sensitive.
Empty lines are allowed. A line starting with `#` is considered a comment.
Unknown keys are ignored.

Here follows a mapping table between CLI switches and key values:

| CLI | Config   |
| --- | -------- |
| r   | rows     |
| c   | cols     |
| l   | snakelen |
| t   | timeout  |
| P   | port     |
| H   | host     |
| u   | user     |

Not all CLI switches have a corresponding config file key!

### Config File Example

```
# Playground height (including borders)
rows: 20
# Playground width (including borders)
cols: 30
# Initial snake length
snakelen: 6
# Number of milliseconds until snake moves even if no key is pressed
timeout: 300
# User name
user: Nesbitt
```

### Command to Start snake.py Using Config File Example

```
./snake.py -H localhost -P 8888 -C snake.cnf -u Pyton
```

Note that the user name reported to the server will be _Pyton_, not
_Nesbitt_, since the `-u` switch appears _after_ the `-C` switch!



## Server

A server written in C has now been added. It doesn't do much yet, just
recieves some information from the client and respons with `200 OK` for
each line it receives from the client.

Feel free to study and update the server's source code (`snakesrv.c`),
extend it do do something useful.

To make the client and server communicate, you need to start the server
first, like this:

```
./snakesrv
```

Then start the client (the game), on another terminal, like this:

```
./snake.py -H localhost -P 8888
```

You can use the `-h` switch in both programs to get help.

You can stop the server like this:

```
killall snakesrv
```

The above won't show any difference. But by setting the pre-processor
switch VERBOSE and recompiling, the server will show some output next
time it's run.

To set the switch temporarily, just recompile like this:

```
cc -DVERBOSE snakesrv.c -o snakesrv
```

To add it permanently, change this `makefile` line

```
CC=cc -Wall
```
to
```
CC=cc -Wall -DVERBOSE
```

## Recommended Actions for snake.py and snakesrv.c

- Add a database or file to the server, to save high-score to.
- Let `snake.py` read its configuration from the server.
- Save all steps to the server, and make it possible to replay a game.
- Let two or more players compete on the same playground, using the server to monitor the game.


## Protocol

The current client/server protocol (version 0.3) is very simple.

The client always initiates transmission by sending a byte encoded
message of maximum 1024 ASCII bytes, without any CR or LF termination.

The server always responds with the ASCII byte sequence `200 OK`.

All messages from client start with `G>`. This `G` stands for _Game_, meaning
that the message is related to what happens on the playground.
After this comes a three-letter upper-case tag, that tells what the rest
of the sequence contains. The tags may be one of the following:

- BEG - Tells that a new game is started.
- END - Tells that a game ended.
- MRK - Tells that a cell on the playground has been marked.
- UNM - Tells that a cell on the playground has been cleared.

Now follows a comma and a sequence of comma-separated key-value-pairs,
separated by colon. The keys are always three-letter-uppercase ASCII.

Syntax for the various tags are as follows (shown with example values):

```
G>BEG,VER:0.2,PID:5288,PRT:43344,RWS:10,CLS:20,LEN:3,TIO:300,USR:Moltas,HSH:e3382993b5877b79
```

- VER is the protocol version
- PID is the client's process ID
- PRT is the client's port number
- RWS is the number of rows on the playground, including borders
- CLS is the number of columns on the playground, including borders
- LEN is the initial size of the snake
- TIO is the timeout in ms between snake moves
- USR is user's nickname, if given (via parameter `-u`)
- HSH is a 16-byte hash unique for the current game session

You can use either HSH, PID or PRT to keep track of an individual game.
The USR value (if assigned) can be used for building score tables.

```
G>END,SCR:11,SIG:-1,FAI:1,PID:5288,PRT:43344,USR:,HSH:e3382993b5877b79
```

- SCR is the score
- SIG is termination signal, if any. If none received, the value is `-1`
- FAI is the reason for failure (see constants `FAIL`... in `snake.py`)
- PID same as for BEG above
- PRT same as for BEG above
- USR same as for BEG above (in this example, no user name is assigned)
- HSH same as for BEG above

```
G>MRK,ROW:5,COL:7,WAT:2
```

- ROW is the row that was marked
- COL is the column that was marked
- WAT is the code identifying what kind of mark was set

```
G>UNM,ROW:1,COL:16,WAT:2
```

As MRK above.


## C++ Server Variant

There's also a snake server variant written in C++ in the making, with
most of the code taken from the C variant. More work is needed to make it
proper C++, but it seems to work well. You can start it like this:

```
./snake++srv
```

It takes the same options as the C variant (`snakesrv`).
