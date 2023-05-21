#!/usr/bin/env python3.11
"""snake - a game to be run in a Linux or UNIX terminal.
Call the program with --help or do python3.11 -m pydoc snake.

The main purpose of this program is not to play it, but to learn Python.
Start by studying it, then try to improve it. See README.md.
"""

__author__ = "Rein Ytterberg"
__version__ = "1.2.0"

import sys
import signal
import random
import curses
import atexit
import re
import traceback
import logging
import os
import socket
import time
import hashlib
from datetime import datetime
import argparse

# Version (as presented to server)
CLIVER = "0.3"

# Exit codes
EXIT_OK = 0         # All is well
EXIT_SYNTAX = 1     # Invalid command-line syntax
EXIT_ARGS = 2       # Invalid arguments
EXIT_SIGNAL = 3     # Termination signal received
EXIT_PROG = 4       # Program error - debugging required!
EXIT_ERR = 5        # Execution error

# Configuration CLI switches, config file keys and defaults
CNFKEY_ROWS = ['r', 'rows', 10]      # Playground size - rows
CNFKEY_COLS = ['c', 'cols', 20]      # Playground size - columns
CNFKEY_SLEN = ['l', 'snakelen', 3]   # Initial snake length
CNFKEY_TIMO = ['t', 'timeout', 300]  # Time in ms between snake moves
CNFKEY_PORT = ['P', 'port', 0]       # Server port
CNFKEY_HOST = ['H', 'host', '']      # Server host
CNFKEY_USER = ['u', 'user', '']      # User's nickname

# Maximum allowed length of user name (-u)
USERML = 16

# Server client/message maximum size
MSGSIZE = 1024


def errprint(*args, **kargs):
    """Print to stderr."""
    print(*args, file=sys.stderr, **kargs)


class Display:
    """Set up and restore the entire display."""
    graphics_active = False     # Graphics initialized?

    def __init__(self, rows, cols, timo=0):
        self.rows = rows
        self.cols = cols
        self.timo = timo
        self.win = self.graphact(rows, cols, timo)

    def getwin(self):
        """Return window handler."""
        return self.win

    def graphact(self, rows=0, cols=0, timo=0):
        """Switch terminal into graphics mode, or resume from it.
        This function is assumed to be called once at startup to
        initialize the entire display and set the playground size
        at the same time. This is done by assigning proper values
        to rows and cols.
        The function shall also be called once before ending the
        program, to restore the display. This is done by calling
        without parameters.
        """
        mode = bool(rows > 0 and cols > 0)
        if not mode:
            # Deactivate curses
            if self.graphics_active:
                curses.endwin()
                self.graphics_active = False
            return None

        # Activate curses
        if self.graphics_active:
            return self.win

        # Playground too small?
        if rows < 3:
            errprint(f"Can't make playground with only {rows} rows.")
            errprint("Minimum row size is 3.")
            sys.exit(EXIT_ARGS)
        if cols < 3:
            errprint(f"Can't make playground with only {cols} columns.")
            errprint("Minimum column size is 3.")
            sys.exit(EXIT_ARGS)
        # Initialize display
        scr = curses.initscr()
        curses.curs_set(0)
        srows, scols = scr.getmaxyx()
        # Playground too large?
        if rows > srows:
            curses.endwin()
            errprint(f"Can't make playground with {rows} rows.")
            errprint(f"Maximum row size is {srows}.")
            sys.exit(EXIT_ARGS)
        if cols > scols:
            curses.endwin()
            errprint(f"Can't make playground with {cols} columns.")
            errprint(f"Maximum column size is {scols}.")
            sys.exit(EXIT_ARGS)
        # Create the playground on the display
        win = curses.newwin(rows, cols, 0, 0)
        win.keypad(1)
        win.timeout(timo)
        self.graphics_active = True
        return win


class Playground:
    """The visible area where the snake(s) move, including borders.
    Each Playground object handles the area where snakes are running,
    but the snakes themselves are not handled except for some
    cleanup of snake tails.
    Positioning of snakes and food is strictly separated from
    visualization and steering input.
    """
    # Visible components
    VIS_CLEANER = ' '   # Character to clean up with
    VIS_BOMB = 'B'      # Character showing bomb position
    VIS_FOOD = 'F'      # Character showing food position
    # Bits indicating playground objects
    OBJ_EMPTY = 0   # Square without content
    OBJ_BORDER = 1  # Playground frame
    OBJ_FOOD = 2    # When eaten, the Snake/Worm grows
    OBJ_BOMB = 4    # When the snake/Worm hits it, it's killed
    OBJ_CLEAR = 8   # This position should be cleaned visibly, and reset
    OBJ_SNAKE = 16  # There's a snake (head or body) here

    def __init__(self, cnf, server=None):
        self.server = server
        self.rows = cnf.getconf(CNFKEY_ROWS[1])
        self.cols = cnf.getconf(CNFKEY_COLS[1])
        self.timo = cnf.getconf(CNFKEY_TIMO[1])
        self.pgr = [[self.OBJ_EMPTY for _ in range(self.cols)]
                    for _ in range(self.rows)]
        self.display = Display(self.rows, self.cols, self.timo)
        self.win = self.display.getwin()
        self.postoclean = []    # Positions needed to be cleaned
        # Mark borders
        # horizontal borders
        for _ in range(self.cols):
            self.pgr[0][_] = self.OBJ_BORDER
            self.pgr[self.rows - 1][_] = self.OBJ_BORDER
        # vertical borders
        for _ in range(self.rows):
            self.pgr[_][0] = self.OBJ_BORDER
            self.pgr[_][self.cols - 1] = self.OBJ_BORDER

    def __report(self, text):
        """Report event to server, if connected."""
        if not self.server:
            return
        self.server.send(text.encode())
        self.server.recv(MSGSIZE)

    def feed(self):
        """Place food at random coordinate."""
        while True:
            foodpos = [random.randint(1, self.rows - 2),
                       random.randint(1, self.cols - 2)]
            cell = self.atpos(foodpos[0], foodpos[1])
            if self.OBJ_EMPTY == (cell &
               (self.OBJ_FOOD | self.OBJ_BOMB | self.OBJ_SNAKE)):
                break
        logging.debug('feed %s, %s, %s',
                      str(foodpos[0]), str(foodpos[1]), str(cell))
        self.markpos(foodpos[0], foodpos[1], self.OBJ_FOOD)
        self.win.addch(foodpos[0], foodpos[1], self.VIS_FOOD)
        self.win.addstr(0, 2, "  Food: " + str(int(foodpos[0]))
                        + " " + str(int(foodpos[1])) + "  ")
        self.win.refresh()

    def bomb(self):
        """Place bomb at random coordinate."""
        while True:
            bombpos = [random.randint(1, self.rows - 2),
                       random.randint(1, self.cols - 2)]
            cell = self.atpos(bombpos[0], bombpos[1])
            if self.OBJ_EMPTY == (cell &
               (self.OBJ_FOOD | self.OBJ_BOMB | self.OBJ_SNAKE)):
                break
        self.markpos(bombpos[0], bombpos[1], self.OBJ_BOMB)
        self.win.addch(bombpos[0], bombpos[1], self.VIS_BOMB)
        self.win.refresh()

    def setcleanpos(self, pos):
        """Save coordinates for a position that needs to be cleaned."""
        self.postoclean.insert(0, pos)

    def cleanpos(self, need_refresh=False):
        """Visibly clean up the Playground."""
        # Blank positions that were marked by call to setcleanpos()
        for _ in range(0, len(self.postoclean)):
            self.win.addch(int(self.postoclean[_][0]),
                           int(self.postoclean[_][1]),
                           self.VIS_CLEANER)
        if need_refresh:
            self.win.refresh()

    def atpos(self, row, col):
        """Return what is at the given position, an OBJ_-mnemonic."""
        return self.pgr[int(row)][int(col)]

    def markpos(self, row, col, what=OBJ_EMPTY) -> int:
        """Mark this playground position as occupied by something
        indicated by what, which must be an OBJ_-mnemonic.
        If what is OBJ_EMPTY, all marks are reset at this position.
        Returns previous value.
        """
        was = self.atpos(int(row), int(col))
        self.pgr[int(row)][int(col)] |= what
        if self.OBJ_EMPTY == what:
            self.pgr[int(row)][int(col)] = self.OBJ_EMPTY
        logging.debug('mark %s, %s, %s',
                      str(int(row)), str(int(col)), str(what))
        self.__report("G>MRK,ROW:" + str(int(row)) + ",COL:" + str(int(col))
                      + ",WAT:" + str(what))
        return was

    def unmarkpos(self, row, col, what) -> int:
        """Remove a mark from given position.
        Mark shall be an OBJ_-menmonic (set by markpos()).
        Returns previous value.
        """
        was = self.atpos(int(row), int(col))
        self.pgr[int(row)][int(col)] &= ~what
        logging.debug('umrk %s, %s, %s',
                      str(int(row)), str(int(col)), str(what))
        self.__report("G>UNM,ROW:" + str(int(row)) + ",COL:" + str(int(col))
                      + ",WAT:" + str(what))
        return was

    def draw(self):
        """Draw the playground."""
        self.win.border(curses.ACS_VLINE)
        self.win.refresh()

    def keypause(self):
        """Deactivate keyboard timeout and wait for keypress."""
        self.win.timeout(-1)
        self.win.getch()


class Worm:
    """A Snake/Worm that crawls across the Playground."""
    # Movement directions
    STEP_UP = -1            # Row movement direction - up
    STEP_DOWN = 1           # Row movement direction - down
    STEP_LEFT = -1          # Column movement direction - left
    STEP_RIGHT = 1          # Column movement direction - right
    STEP_IDLE = 0           # Row/Column movement direction - idle
    # Visible components
    BODY = 'o'              # Snake body element
    HEAD = 'Ö'              # Snake head element
    # Errors
    FAIL_NONE = 0           # Successful move
    FAIL_HITHIGH = 1        # Hit top border
    FAIL_HITLOW = 2         # Hit bottom border
    FAIL_HITLEFT = 3        # Hit left border
    FAIL_HITRIGHT = 4       # Hit right border
    FAIL_HITSNAKE = 5       # Hit a snake
    FAIL_HITBOMB = 6        # Hit a bomb
    # Fail texts
    FAILTEXT = {
        FAIL_NONE:     "Success",
        FAIL_HITHIGH:  "Hit top border",
        FAIL_HITLOW:   "Hit lower border",
        FAIL_HITLEFT:  "Hit left border",
        FAIL_HITRIGHT: "Hit right border",
        FAIL_HITSNAKE: "Hit a snake",
        FAIL_HITBOMB:  "Hit a bomb"
    }

    def __init__(self, playground, cnf,
                 row=None, col=None, rstep=None, cstep=None):
        self.pgr = playground   # Current playground
        self.cnf = cnf          # Configuration
        self.length = cnf.getconf(CNFKEY_SLEN[1])    # Expected length
        self.curlen = 1         # Current length including head
        # Set initial moving direction
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE
        # Set initial head position
        self.poss = [[row if row is not None else self.pgr.rows / 2,
                      col if col is not None else self.pgr.cols / 2]]
        self.score = 0              # Score counter
        self.fail = self.FAIL_NONE  # Reason for Game Over

    def __inclen(self):
        """Increment length of snake."""
        self.length += self.cnf.getconf(CNFKEY_SLEN[1])

    def draw(self):
        """Draw the Snake visually."""
        self.pgr.cleanpos(False)
        # Head
        self.pgr.win.addch(int(self.poss[0][0]),
                           int(self.poss[0][1]),
                           self.HEAD)
        # Tail
        for _ in range(1, len(self.poss)):
            self.pgr.win.addch(int(self.poss[_][0]),
                               int(self.poss[_][1]), self.BODY)
        self.pgr.win.refresh()

    def __step(self):
        """Move the Snake in current direction."""
        needfood = False
        if self.STEP_IDLE == self.rowstep and self.STEP_IDLE == self.colstep:
            # Snake is sleeping
            return self.FAIL_NONE
        # Calculate next position for snake's head
        newhead = [self.poss[0][0] + self.rowstep,
                   self.poss[0][1] + self.colstep]
        # Find out what's at the new position
        cell = self.pgr.atpos(newhead[0], newhead[1])
        if cell:
            self.pgr.win.refresh()
        if cell & self.pgr.OBJ_SNAKE:
            return self.FAIL_HITSNAKE
        if cell & self.pgr.OBJ_BOMB:
            return self.FAIL_HITBOMB
        if cell & self.pgr.OBJ_FOOD:
            logging.debug('step %s, %s',
                          str(int(newhead[0])), str(int(newhead[1])))
            self.pgr.unmarkpos(newhead[0], newhead[1], self.pgr.OBJ_FOOD)
            needfood = True
            self.__inclen()
        self.pgr.markpos(newhead[0], newhead[1], self.pgr.OBJ_SNAKE)
        if needfood:
            self.pgr.feed()
        self.poss.insert(0, newhead)
        if len(self.poss) > self.length:
            last = len(self.poss) - 1
            self.pgr.setcleanpos(self.poss[last])
            self.pgr.unmarkpos(self.poss[last][0],
                               self.poss[last][1],
                               self.pgr.OBJ_SNAKE)
            self.poss.pop(last)
        # Check that snake is still inside the playground.
        # Actually we can also check if (cell & self.pgr.BORDER)
        if self.poss[0][0] < 1:     # Hit top
            return self.FAIL_HITHIGH
        if self.poss[0][1] < 1:     # Hit left
            return self.FAIL_HITLEFT
        if self.poss[0][0] >= self.pgr.rows - 1:    # Hit bottom
            return self.FAIL_HITLOW
        if self.poss[0][1] >= self.pgr.cols - 1:    # Hit right
            return self.FAIL_HITRIGHT
        return self.FAIL_NONE

    def turn(self, rstep=None, cstep=None):
        """Change current snake direction."""
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE

    def getscore(self):
        """Return current score."""
        return self.score

    def getfailcode(self):
        """Return numerical reason for failed game."""
        return self.fail

    def getfailtext(self, fail=-1) -> str:
        """Convert fail code (FAIL_-mnemonic) to text.
        Without parameter, the object's failure text is returned.
        With parameter, requested code is converted to text.
        """
        if -1 == fail:
            return self.FAILTEXT[self.fail]
        try:
            return self.FAILTEXT[fail]
        except KeyError:
            errprint("Program error - illegal index (" + str(fail) + ")")
            line = traceback.format_stack()[0]
            errprint(line.strip())
            sys.exit(EXIT_PROG)

    def play(self):
        """ Main loop. Returns failure as FAIL_-mnemonic """
        while self.FAIL_NONE == self.fail:
            key = self.pgr.win.getch()
            match key:
                case curses.KEY_DOWN:
                    self.turn(self.STEP_DOWN)
                case curses.KEY_LEFT:
                    self.turn(None, self.STEP_LEFT)
                case curses.KEY_RIGHT:
                    self.turn(None, self.STEP_RIGHT)
                case curses.KEY_UP:
                    self.turn(self.STEP_UP)
            self.fail = self.__step()
            if not self.fail:
                self.score += 1
                self.draw()

        # Show the score
        score_row = int(self.cnf.getconf(CNFKEY_ROWS[1])) - 1
        self.pgr.win.addstr(score_row, 2, " Score: " + str(self.score) + " ")
        self.draw()
        return self.fail


class Help:
    """Show help."""
    _usage_intromsg = \
        """A Linux/UNIX Snake game to play in the terminal and learn from.
        Use arrow-keys to change snake direction.
        Try to hit food, marked {}, but avoid bombs, marked {}!"""\
        .format(Playground.VIS_FOOD, Playground.VIS_BOMB)

    @classmethod
    def intro(cls):
        """Print introductiory summary."""
        return cls._usage_intromsg


# Configuration

class Config:
    """Configuration of one game instance."""

    def __init__(self, conffile=None):
        self.conffile = conffile     # Configuration file
        self.cnfval_rows = CNFKEY_ROWS[2]
        self.cnfval_cols = CNFKEY_COLS[2]
        self.cnfval_slen = CNFKEY_SLEN[2]
        self.cnfval_timo = CNFKEY_TIMO[2]
        self.cnfval_port = CNFKEY_PORT[2]
        self.cnfval_host = CNFKEY_HOST[2]
        self.cnfval_user = CNFKEY_USER[2]
        if conffile:
            self.readconf(conffile)

    def readconf(self, conffile=None):
        """Process configuration file."""
        self.conffile = conffile if conffile is not None else "snake.cnf"

        try:
            conff = open(self.conffile)
            cnf = conff.readlines()
            conff.close()
        except FileNotFoundError:
            errprint("Non-existing configuration file: " + self.conffile)
            sys.exit(EXIT_ERR)
        except PermissionError:
            errprint("Unreadable configuration file: " + self.conffile)
            sys.exit(EXIT_ERR)
        except IsADirectoryError:
            errprint("Configuration file is a directory: " + self.conffile)
            sys.exit(EXIT_ERR)
        except Exception as e:
            logging.debug(f"readconf exception {e}")
            errprint(f"ERROR: Config file error {e}.")
            sys.exit(EXIT_ERR)

        keyval = re.compile('^[a-z]+: [a-zA-Z0-9]+')
        for _ in cnf:
            if not keyval.match(_):
                continue
            keypos = re.search(r"\s", _).start()
            key = _[:keypos - 1]
            val = _[keypos:].strip()
            self.setconf(key, val)

    def setconf(self, key, val):
        """Assign configurable value to a key."""
        try:
            if CNFKEY_ROWS[1] == key:
                self.cnfval_rows = int(val)
                return
            if CNFKEY_COLS[1] == key:
                self.cnfval_cols = int(val)
                return
            if CNFKEY_SLEN[1] == key:
                self.cnfval_slen = int(val)
                return
            if CNFKEY_TIMO[1] == key:
                self.cnfval_timo = int(val)
                return
            if CNFKEY_PORT[1] == key:
                self.cnfval_port = int(val)
                return
            if CNFKEY_HOST[1] == key:
                self.cnfval_host = val
                return
            if CNFKEY_USER[1] == key:
                self.cnfval_user = val
                return
            errprint(f"Invalid setconf(key=\"{key}\")!")
            sys.exit(EXIT_PROG)
        except ValueError:
            errprint("Invalid argument or config value!")
            sys.exit(EXIT_SYNTAX)

    def getconf(self, key):
        """Return a configuration value.
        key -- Configuration parameter name: CNFKEY_...[1]
        """
        if CNFKEY_ROWS[1] == key:
            return self.cnfval_rows
        if CNFKEY_COLS[1] == key:
            return self.cnfval_cols
        if CNFKEY_SLEN[1] == key:
            return self.cnfval_slen
        if CNFKEY_TIMO[1] == key:
            return self.cnfval_timo
        if CNFKEY_PORT[1] == key:
            return self.cnfval_port
        if CNFKEY_HOST[1] == key:
            return self.cnfval_host
        if CNFKEY_USER[1] == key:
            return self.cnfval_user
        errprint("Invalid getconf(key=" + key + ")!")
        sys.exit(EXIT_PROG)


class Server:
    """Handle connection to Snake server (snakesrv).
    If both a server host name or IP address and a port to it is
    assigned, the program shall connect to it. If none or only one
    of the values is set, server connection will be silently ignored.
    Connection uses TCP/IP sockets.
    The server must be running.
    """

    def __init__(self, cnf=None):
        self.use = False    # True if we're connected to a server
        self.cnf = cnf
        if not cnf:
            return
        host = cnf.getconf(CNFKEY_HOST[1])
        port = cnf.getconf(CNFKEY_PORT[1])
        user = cnf.getconf(CNFKEY_USER[1])
        if not port or 0 == port:
            return
        if not host or '' == host:
            return
        self.use = True
        self.host = host
        self.port = port
        self.user = user
        self.hash = ''
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
        except ConnectionRefusedError:
            self.use = False
            errprint("Server " + host + " refuses connection on port "
                     + str(port) + ".")
            self.sock.close()
            sys.exit(EXIT_ERR)

    def send(self, data):
        """Send a sequence to the server if connected."""
        if not self.use:
            return
        self.sock.sendall(data)

    def recv(self, maxlen=1024) -> str:
        """Receive a string from server if connected."""
        if not self.use:
            return None
        ret = self.sock.recv(maxlen).decode()
        return ret

    def __srvhead(self, tag, score=None, failcode=None, sig=None):
        """Create and send header to server, if connected."""
        if not self.use:
            return
        ownport = self.sock.getsockname()[1]
        if "END" == tag:
            head = 'G>END,SCR:' + str(score) + ',SIG:' + str(sig) + ',FAI:' + \
                str(failcode)
            head = head + ',PID:' + str(os.getpid()) + ",PRT:" + str(ownport)
        elif "BEG" == tag:
            head = 'G>' + tag + ',VER:' + CLIVER + ',PID:' + str(os.getpid()) \
                + ",PRT:" + str(ownport)
            head = head + ',RWS:' + str(self.cnf.getconf(CNFKEY_ROWS[1])) + \
                ',CLS:' + str(self.cnf.getconf(CNFKEY_COLS[1]))
            head = head + ',LEN:' + str(self.cnf.getconf(CNFKEY_SLEN[1])) + \
                ',TIO:' + str(self.cnf.getconf(CNFKEY_TIMO[1]))
        else:
            head = ('G>' + tag).encode()

        head = head + ',USR:' + self.user
        head = head + ',HSH:' + self.hash
        head = head.encode()
        self.send(head)
        self.recv(1024)

    def newgame(self):
        """Report start of a new game to the server, if connected."""
        if self.use:
            hash_ = self.sock.getsockname()[0]
            hash_ = hash_ + ':' + str(self.sock.getsockname()[1])
            hash_ = hash_ + ':' + self.user + ':' + str(time.time())
            self.hash = hashlib.shake_256(hash_.encode()).hexdigest(8)
        self.__srvhead('BEG')

    def endgame(self, score, failcode, sig=-1):
        """Report status about ended game to the server, if connected."""
        self.__srvhead('END', score, failcode, sig)

    def stop(self):
        """Close connection to server, if connected."""
        if self.use:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

    def trap(self, sig):
        """Terminate server connection on signal reception."""
        if self.use:
            self.endgame(-1, -1, sig)
            self.stop()


def exithand():
    """Cleanup environment before exiting."""
    _server.stop()
    _pgr.display.graphact()


def sighand(signum, frame):
    """Signal handler callback."""
    del frame
    _pgr.display.graphact()
    errprint("Interrupted")
    _server.trap(signum)
    sys.exit(EXIT_SIGNAL)


# Stop program from being executed when running pydoc.
if __name__ == '__main__':

    _conf = Config()


# Command line options and switches

    _logfile = None  # Name of log file (if set with -L option)

    parser = argparse.ArgumentParser(description=Help.intro())
    parser.add_argument("-L", "--logfile", help="Specify name of log file.")
    parser.add_argument("-C", "--config", help="Read configuration from file.")
    parser.add_argument("-" + CNFKEY_ROWS[0], "--" + CNFKEY_ROWS[1],
                        help="Playground height.")
    parser.add_argument("-" + CNFKEY_COLS[0], "--" + CNFKEY_COLS[1],
                        help="Playground width.")
    parser.add_argument("-" + CNFKEY_SLEN[0], "--" + CNFKEY_SLEN[1],
                        help="Initial snake length.")
    parser.add_argument("-" + CNFKEY_TIMO[0], "--" + CNFKEY_TIMO[1],
                        help="Timeout (ms) between snake steps.")
    parser.add_argument("-" + CNFKEY_PORT[0], "--" + CNFKEY_PORT[1],
                        help="Server port.")
    parser.add_argument("-" + CNFKEY_HOST[0], "--" + CNFKEY_HOST[1],
                        help="Server host.")
    parser.add_argument("-" + CNFKEY_USER[0], "--" + CNFKEY_USER[1],
                        help="Player's user name.")
    args = parser.parse_args()
    if args.logfile:
        # Set log file
        _logfile = args.logfile
        if os.path.exists(_logfile):
            mystat = os.stat(sys.argv[0])
            lfstat = os.stat(_logfile)
            if mystat.st_dev == lfstat.st_dev and \
               mystat.st_ino == lfstat.st_ino:
                errprint("ERROR: Log file (-L) same as program file!")
                sys.exit(EXIT_ARGS)
        try:
            logging.basicConfig(filename=_logfile,
                                format="%(asctime)s %(levelname)-3.3s "
                                + "%(message)s",
                                datefmt='%y%m%d %H:%M:%S',
                                level=logging.INFO)
        except PermissionError:
            errprint(f"ERROR: Can't log to file \"{_logfile}\". "
                     + "Check permissions!")
            sys.exit(EXIT_ERR)
        logging.info('Started')

    if args.config:
        # Read configuration from file
        _conf.readconf(args.config)

    if args.rows:
        # Set number of rows on playground
        _conf.setconf(CNFKEY_ROWS[1], args.rows)

    if args.cols:
        # Set number of columns on playground
        _conf.setconf(CNFKEY_COLS[1], args.cols)

    if args.snakelen:
        # Set initial snake length
        _conf.setconf(CNFKEY_SLEN[1], args.snakelen)

    if args.timeout:
        # Timeout in ms between movements
        _conf.setconf(CNFKEY_TIMO[1], args.timeout)

    if args.port:
        # Server port
        _conf.setconf(CNFKEY_PORT[1], args.port)

    if args.host:
        # Server host
        _conf.setconf(CNFKEY_HOST[1], args.host)

    if args.user:
        # User's nickname
        if str.isascii(args.user) is not True:
            errprint(CNFKEY_USER[0]
                     + ": User name must only contain A-Z, a-z, 0-9!")
            sys.exit(EXIT_SYNTAX)
        if " " in args.user:
            errprint(CNFKEY_USER[0]
                     + ": User name may not contain blanks!")
            sys.exit(EXIT_SYNTAX)
        if len(args.user) < 1 or len(args.user) > USERML:
            errprint(CNFKEY_USER[0]
                     + ": User name must be 1-16 characters in length!")
            sys.exit(EXIT_SYNTAX)
        _conf.setconf(CNFKEY_USER[1], args.user)


# Connect to server (if requested)
    _server = Server(_conf)
    _server.newgame()

# Initialize display and playground
    _pgr = Playground(_conf, _server)

# Cleanup handler
    atexit.register(exithand)

# Trap signals
    signal.signal(signal.SIGINT, sighand)
    signal.signal(signal.SIGHUP, sighand)
    signal.signal(signal.SIGQUIT, sighand)
    signal.signal(signal.SIGTERM, sighand)

# Create playground objects
    _pgr.feed()   # First piece of food
    _pgr.bomb()   # First bomb
    _pgr.draw()   # Draw complete playground

# Create one snake
    _worm = Worm(_pgr, _conf)

# Determine initial moving direction
    _worm.turn(_worm.STEP_UP, _worm.STEP_IDLE)

# Draw the snake initially
    _worm.draw()

# Start playing
    _worm.play()

# Report to server (if any)
    _server.endgame(_worm.getscore(), _worm.getfailcode())

    _pgr.keypause()
    _pgr.display.graphact()

# Display score
    print("Score:   " + str(_worm.getscore()))
    print("Failure: " + _worm.getfailtext())

# Log result
    logging.info('Ended. Score %s. Fail %s.',
                 str(_worm.getscore()), _worm.getfailtext())

    sys.exit(EXIT_OK)
