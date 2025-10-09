#!/usr/bin/env python3.12
# pylint: disable=too-many-lines
"""snake - a game to be run in a Linux or UNIX terminal.
Call the program with --help or do python3.11 -m pydoc snake.

The main purpose of this program is not to play it, but to learn Python.
Start by studying it, then try to improve it. See README.md.
"""

__author__ = "Rein Ytterberg"
__version__ = "1.3.0"

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
    """Print a message to stderr.

    Args:
        *args: Positional arguments forwarded to ``print``.
        **kargs: Keyword arguments forwarded to ``print``.
    """
    print(*args, file=sys.stderr, **kargs)


class Display:
    """Set up and restore the entire display.

    Args:
        rows (int): Number of rows for the playground.
        cols (int): Number of columns for the playground.
        timo (int): Timeout in milliseconds between key reads.

    Attributes:
        rows (int): Number of playground rows.
        cols (int): Number of playground columns.
        timo (int): Keyboard timeout in milliseconds.
        win: Curses window handle for the playground.
        graphics_active (bool): True when curses mode is active.
    """
    graphics_active = False     # Graphics initialized?

    def __init__(self, rows, cols, timo=0):
        self.rows = rows
        self.cols = cols
        self.timo = timo
        self.win = self.graphact(rows, cols, timo)

    def getwin(self):
        """Return the curses window handle.

        Returns:
            Any: The curses window created by ``curses.newwin``.
        """
        return self.win

    def graphact(self, rows=0, cols=0, timo=0):
        """Switch terminal into graphics mode, or restore from it.

        When called with positive ``rows`` and ``cols``, initializes
        curses and creates the playground window. When called with
        default values, restores the terminal to normal mode.

        Args:
            rows (int): Playground rows (>0 to activate, 0 to restore).
            cols (int): Playground cols (>0 to activate, 0 to restore).
            timo (int): Keyboard timeout in milliseconds.

        Returns:
            Any | None: The curses window handle when activating,
            otherwise ``None`` when restoring.
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
        try:
            scr = curses.initscr()
            try:
                curses.curs_set(0)
            except curses.error:
                logging.debug('curses.curs_set not supported')
            srows, scols = scr.getmaxyx()
        except curses.error as e:
            errprint("ERROR: Failed to initialize curses display")
            logging.error("curses init error: %s", e, exc_info=True)
            sys.exit(EXIT_ERR)
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
        try:
            win = curses.newwin(rows, cols, 0, 0)
            win.keypad(1)
            win.timeout(timo)
        except curses.error as e:
            curses.endwin()
            errprint("ERROR: Failed to create curses window")
            logging.error("newwin error: %s", e, exc_info=True)
            sys.exit(EXIT_ERR)
        self.graphics_active = True
        return win


class Playground:
    """The visible area where the snake(s) move, including borders.

    Each ``Playground`` handles the 2D grid and its visual representation
    via curses, but does not implement the snake logic itself beyond
    marking/unmarking cells.

    Args:
        cnf (Config): Configuration provider for sizing and timing.
        server (Server | None): Optional server connection used to
            report gameplay events.

    Attributes:
        rows (int): Number of rows including borders.
        cols (int): Number of columns including borders.
        timo (int): Keyboard timeout in milliseconds.
        win: Curses window handle.
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

    # pylint: disable=too-many-instance-attributes
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

    def _random_empty_position(self):
        """Return a random empty (row, col) position inside borders.

        Returns:
            list[int, int]: A suitable row/col coordinate.
        """
        while True:
            pos = [random.randint(1, self.rows - 2),
                   random.randint(1, self.cols - 2)]
            cell = self.atpos(pos[0], pos[1])
            if self.OBJ_EMPTY == (cell &
               (self.OBJ_FOOD | self.OBJ_BOMB | self.OBJ_SNAKE)):
                return pos

    def __report(self, text):
        """Report an event to the server if connected.

        Args:
            text (str): The message to send (ASCII string).
        """
        if not self.server:
            return
        self.server.send(text.encode())
        self.server.recv(MSGSIZE)

    def feed(self):
        """Place food at a random empty coordinate.

        Side Effects:
            Updates the internal grid, updates the display, and may log.
        """
        foodpos = self._random_empty_position()
        cell = self.atpos(foodpos[0], foodpos[1])
        logging.debug('feed %s, %s, %s',
                      str(foodpos[0]), str(foodpos[1]), str(cell))
        self.markpos(foodpos[0], foodpos[1], self.OBJ_FOOD)
        self.win.addch(foodpos[0], foodpos[1], self.VIS_FOOD)
        self.win.addstr(0, 2, f"  Food: {int(foodpos[0])} {int(foodpos[1])}  ")
        self.win.refresh()

    def bomb(self):
        """Place a bomb at a random empty coordinate.

        Side Effects:
            Updates the internal grid and updates the display.
        """
        bombpos = self._random_empty_position()
        self.markpos(bombpos[0], bombpos[1], self.OBJ_BOMB)
        self.win.addch(bombpos[0], bombpos[1], self.VIS_BOMB)
        self.win.refresh()

    def setcleanpos(self, pos):
        """Save a coordinate that should be visually cleaned.

        Args:
            pos (list[int, int]): Row/column pair to blank on next draw.
        """
        self.postoclean.insert(0, pos)

    def cleanpos(self, need_refresh=False):
        """Visibly clean previously marked positions.

        Args:
            need_refresh (bool): If True, refresh the window after cleanup.
        """
        # Blank positions that were marked by call to setcleanpos()
        for pos in self.postoclean:
            self.win.addch(int(pos[0]), int(pos[1]), self.VIS_CLEANER)
        if need_refresh:
            self.win.refresh()

    def atpos(self, row, col):
        """Return what is at the given position.

        Args:
            row (int): Row index.
            col (int): Column index.

        Returns:
            int: Bitmask containing OBJ_-mnemonics for the cell.
        """
        return self.pgr[int(row)][int(col)]

    def markpos(self, row, col, what=OBJ_EMPTY) -> int:
        """Set a mark on a playground position.

        If ``what`` is ``OBJ_EMPTY``, all marks are cleared at the position.

        Args:
            row (int): Row index.
            col (int): Column index.
            what (int): Bitmask of OBJ_-mnemonics to set.

        Returns:
            int: Previous bitmask at the position.
        """
        was = self.atpos(int(row), int(col))
        self.pgr[int(row)][int(col)] |= what
        if self.OBJ_EMPTY == what:
            self.pgr[int(row)][int(col)] = self.OBJ_EMPTY
        logging.debug('mark %d, %d, %s', int(row), int(col), what)
        self.__report("G>MRK,ROW:" + str(int(row)) + ",COL:" + str(int(col))
                      + ",WAT:" + str(what))
        return was

    def unmarkpos(self, row, col, what) -> int:
        """Remove a mark from a position.

        Args:
            row (int): Row index.
            col (int): Column index.
            what (int): Bitmask of OBJ_-mnemonics to clear.

        Returns:
            int: Previous bitmask at the position.
        """
        was = self.atpos(int(row), int(col))
        self.pgr[int(row)][int(col)] &= ~what
        logging.debug('umrk %d, %d, %s', int(row), int(col), what)
        self.__report("G>UNM,ROW:" + str(int(row)) + ",COL:" + str(int(col))
                      + ",WAT:" + str(what))
        return was

    def draw(self):
        """Draw the playground border and refresh the window."""
        self.win.border(curses.ACS_VLINE)
        self.win.refresh()

    def keypause(self):
        """Deactivate keyboard timeout and block until a key is pressed."""
        self.win.timeout(-1)
        self.win.getch()


class Worm:
    """A Snake/Worm that crawls across the Playground.

    Args:
        playground (Playground): The playground to move within.
        cnf (Config): Configuration used for initial size and timing.
        row (int | None): Optional initial head row (defaults to center).
        col (int | None): Optional initial head column (defaults to center).
        rstep (int | None): Initial row step (direction).
        cstep (int | None): Initial column step (direction).
    """
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

    # pylint: disable=too-many-instance-attributes,too-many-arguments
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
        """Increment the target length of the snake."""
        self.length += self.cnf.getconf(CNFKEY_SLEN[1])

    def draw(self):
        """Draw the snake's head and body, and refresh the window."""
        self.pgr.cleanpos(False)
        # Head
        self.pgr.win.addch(int(self.poss[0][0]),
                           int(self.poss[0][1]),
                           self.HEAD)
        # Tail
        for idx, _ in enumerate(self.poss[1:], start=1):
            self.pgr.win.addch(int(self.poss[idx][0]),
                               int(self.poss[idx][1]), self.BODY)
        self.pgr.win.refresh()

    def __step(self):
        """Advance the snake one step in the current direction.

        Returns:
            int: A FAIL_-code indicating collision, or ``FAIL_NONE``.
        """
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
        fail = self.__check_bounds()
        if fail != self.FAIL_NONE:
            return fail
        return self.FAIL_NONE

    def __check_bounds(self):
        """Check if head is inside borders.

        Returns:
            int: ``FAIL_NONE`` if inside, otherwise a boundary FAIL code.
        """
        head_row = self.poss[0][0]
        head_col = self.poss[0][1]
        if head_row < 1:
            return self.FAIL_HITHIGH
        if head_col < 1:
            return self.FAIL_HITLEFT
        if head_row >= self.pgr.rows - 1:
            return self.FAIL_HITLOW
        if head_col >= self.pgr.cols - 1:
            return self.FAIL_HITRIGHT
        return self.FAIL_NONE

    def turn(self, rstep=None, cstep=None):
        """Change current snake direction.

        Args:
            rstep (int | None): New row step (use ``None`` to keep).
            cstep (int | None): New column step (use ``None`` to keep).
        """
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE

    def getscore(self):
        """Return the current score.

        Returns:
            int: The current score value.
        """
        return self.score

    def getfailcode(self):
        """Return the numerical reason for game over.

        Returns:
            int: One of the ``FAIL_*`` constants.
        """
        return self.fail

    def getfailtext(self, fail=-1) -> str:
        """Translate a failure code to human-readable text.

        Args:
            fail (int): Optional ``FAIL_*`` code. If ``-1``, use
                the object's current failure.

        Returns:
            str: A descriptive failure string.
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
        """Run the main gameplay loop.

        Returns:
            int: Failure as a ``FAIL_*`` mnemonic.
        """
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
    """User-facing help texts and messages."""
    _usage_intromsg = \
        """A Linux/UNIX Snake game to play in the terminal and learn from.
        Use arrow-keys to change snake direction.
        Try to hit food, marked {}, but avoid bombs, marked {}!"""\
        .format(Playground.VIS_FOOD, Playground.VIS_BOMB)

    @classmethod
    def intro(cls):
        """Return an introductory summary for CLI help.

        Returns:
            str: Short description of the game and controls.
        """
        return cls._usage_intromsg


# Configuration

class Config:
    """Configuration for a single game instance.

    Args:
        conffile (str | None): Optional path to a configuration file.
    """

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
        """Read and apply configuration values from a file.

        Args:
            conffile (str | None): Path to configuration file. If
                ``None``, defaults to ``"snake.cnf"``.
        """
        self.conffile = conffile if conffile is not None else "snake.cnf"

        try:
            with open(self.conffile, encoding="utf-8") as conff:
                cnf = conff.readlines()
        except FileNotFoundError as e:
            errprint("Non-existing configuration file: " + self.conffile)
            logging.error("Config read error: %s", e, exc_info=True)
            sys.exit(EXIT_ERR)
        except PermissionError as e:
            errprint("Unreadable configuration file: " + self.conffile)
            logging.error("Config permission error: %s", e, exc_info=True)
            sys.exit(EXIT_ERR)
        except IsADirectoryError as e:
            errprint("Configuration file is a directory: " + self.conffile)
            logging.error("Config path is directory: %s", e, exc_info=True)
            sys.exit(EXIT_ERR)
        except Exception as e:
            logging.error("Config file error: %s", e, exc_info=True)
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
        """Assign a configuration value to a key.

        Args:
            key (str): Configuration key (e.g., ``rows``, ``cols``).
            val (str | int): Value to assign; type depends on key.
        """
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
        except ValueError as exc:
            errprint("Invalid argument or config value!")
            raise SystemExit(EXIT_SYNTAX) from exc

    def getconf(self, key):
        """Return a configuration value by key.

        Args:
            key (str): Configuration parameter name
                (e.g., ``rows``, ``timeout``).

        Returns:
            int | str: The configured value for the key.
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
    """Handle connection to the optional Snake server.

    Establishes a TCP/IP connection when both host and port are provided.

    Args:
        cnf (Config | None): Configuration providing host/port and user.
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
            logging.error("Connection refused to %s:%s", host, port,
                          exc_info=True)
            try:
                self.sock.close()
            except Exception:
                pass
            sys.exit(EXIT_ERR)
        except OSError as e:
            self.use = False
            errprint("Network error connecting to server.")
            logging.error("Socket connect error: %s", e, exc_info=True)
            try:
                self.sock.close()
            except Exception:
                pass
            sys.exit(EXIT_ERR)

    def send(self, data):
        """Send a byte sequence to the server if connected.

        Args:
            data (bytes): Raw bytes to send.
        """
        if not self.use:
            return
        try:
            self.sock.sendall(data)
        except OSError as e:
            logging.error("Socket send error: %s", e, exc_info=True)
            self.use = False

    def recv(self, maxlen=1024) -> str:
        """Receive a string from the server if connected.

        Args:
            maxlen (int): Maximum number of bytes to receive.

        Returns:
            str | None: Decoded response or ``None`` if not connected.
        """
        if not self.use:
            return None
        try:
            ret = self.sock.recv(maxlen).decode()
        except OSError as e:
            logging.error("Socket recv error: %s", e, exc_info=True)
            self.use = False
            return None
        return ret

    def __srvhead(self, tag, score=None, failcode=None, sig=None):
        """Create and send a protocol header to the server.

        Args:
            tag (str): One of ``'BEG'``, ``'END'``, ``'MRK'``, ``'UNM'``.
            score (int | None): Score to report (for ``END``).
            failcode (int | None): Failure code (for ``END``).
            sig (int | None): Signal number (for ``END``).
        """
        if not self.use:
            return
        ownport = self._safe_own_port()
        if "END" == tag:
            head = (
                f"G>END,SCR:{score},SIG:{sig},FAI:{failcode}"
                f",PID:{os.getpid()},PRT:{ownport}"
            )
        elif "BEG" == tag:
            head = (
                f"G>{tag},VER:{CLIVER},PID:{os.getpid()},PRT:{ownport}"
                f",RWS:{self.cnf.getconf(CNFKEY_ROWS[1])}"
                f",CLS:{self.cnf.getconf(CNFKEY_COLS[1])}"
                f",LEN:{self.cnf.getconf(CNFKEY_SLEN[1])}"
                f",TIO:{self.cnf.getconf(CNFKEY_TIMO[1])}"
            )
        else:
            head = f"G>{tag}"

        head = head + f",USR:{self.user}"
        head = head + f",HSH:{self.hash}"
        head = head.encode()
        self._send_and_ack(head)

    def newgame(self):
        """Report the start of a new game session to the server."""
        if self.use:
            hash_ = self.sock.getsockname()[0]
            hash_ = hash_ + ':' + str(self.sock.getsockname()[1])
            hash_ = hash_ + ':' + self.user + ':' + str(time.time())
            self.hash = hashlib.shake_256(hash_.encode()).hexdigest(8)
        self.__srvhead('BEG')

    def _safe_own_port(self):
        """Return local socket port or -1 on error."""
        try:
            return self.sock.getsockname()[1]
        except OSError as e:
            logging.error("getsockname error: %s", e, exc_info=True)
            return -1

    def _send_and_ack(self, payload: bytes) -> None:
        """Send payload and attempt to read an ACK, logging errors only.

        Args:
            payload (bytes): Encoded message to send.
        """
        try:
            self.send(payload)
            self.recv(1024)
        except Exception as e:
            logging.error("Server header send/recv error: %s",
                          e, exc_info=True)

    def endgame(self, score, failcode, sig=-1):
        """Report the end of a game session to the server.

        Args:
            score (int): Final score.
            failcode (int): ``FAIL_*`` reason for game over.
            sig (int): Signal received, or ``-1`` if none.
        """
        self.__srvhead('END', score, failcode, sig)

    def stop(self):
        """Close the server connection, if connected."""
        if self.use:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

    def trap(self, sig):
        """Terminate server connection on signal reception.

        Args:
            sig (int): Signal number received.
        """
        if self.use:
            self.endgame(-1, -1, sig)
            self.stop()


def make_exithand(server, playground):
    """Create an exit handler that cleans up resources.

    Args:
        server (Server): Server instance to stop.
        playground (Playground): Playground whose display to restore.

    Returns:
        Callable[[], None]: A zero-argument function for ``atexit``.
    """
    def _exithand():
        server.stop()
        playground.display.graphact()
    return _exithand


def make_sighand(server, playground):
    """Create a signal handler that preserves curses and informs server.

    Args:
        server (Server): Server instance to notify.
        playground (Playground): Playground whose display to restore.

    Returns:
        Callable[[int, Any], None]: A signal handler function.
    """
    def _sighand(signum, frame):
        del frame
        playground.display.graphact()
        errprint("Interrupted")
        server.trap(signum)
        sys.exit(EXIT_SIGNAL)
    return _sighand


def _determine_log_level(args) -> int:
    """Translate CLI flags to a logging level.

    Args:
        args: Parsed argparse namespace with ``verbose``/``quiet``.

    Returns:
        int: One of logging.DEBUG/INFO/WARNING.
    """
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    return log_level


def _configure_logging(args, log_level: int, logfile: str | None) -> None:
    """Configure root logger to stderr and optional file.

    Args:
        args: Parsed argparse namespace with ``logfile``.
        log_level (int): Logging level to use.
        logfile (str | None): Path to logfile if provided.
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-3.3s %(message)s",
        datefmt='%y%m%d %H:%M:%S'
    )

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(log_level)
    root_logger.addHandler(stderr_handler)

    if args.logfile:
        logfile = args.logfile
        if os.path.exists(logfile):
            mystat = os.stat(sys.argv[0])
            lfstat = os.stat(logfile)
            if mystat.st_dev == lfstat.st_dev and \
               mystat.st_ino == lfstat.st_ino:
                errprint("ERROR: Log file (-L) same as program file!")
                raise SystemExit(EXIT_ARGS)
        try:
            file_handler = logging.FileHandler(logfile)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        except PermissionError as exc:
            errprint(f"ERROR: Can't log to file \"{logfile}\". "
                     + "Check permissions!")
            raise SystemExit(EXIT_ERR) from exc
    logging.info('Started')


def _apply_cli_to_config(args, conf: Config) -> None:
    """Apply parsed CLI arguments to configuration.

    Args:
        args: Parsed argparse namespace.
        conf (Config): Configuration to mutate.
    """
    if args.config:
        conf.readconf(args.config)

    if args.rows:
        conf.setconf(CNFKEY_ROWS[1], args.rows)

    if args.cols:
        conf.setconf(CNFKEY_COLS[1], args.cols)

    if args.snakelen:
        conf.setconf(CNFKEY_SLEN[1], args.snakelen)

    if args.timeout:
        conf.setconf(CNFKEY_TIMO[1], args.timeout)

    if args.port:
        conf.setconf(CNFKEY_PORT[1], args.port)

    if args.host:
        conf.setconf(CNFKEY_HOST[1], args.host)

    if args.user:
        if str.isascii(args.user) is not True:
            errprint(CNFKEY_USER[0]
                     + ": User name must only contain A-Z, a-z, 0-9!")
            raise SystemExit(EXIT_SYNTAX)
        if " " in args.user:
            errprint(CNFKEY_USER[0]
                     + ": User name may not contain blanks!")
            raise SystemExit(EXIT_SYNTAX)
        if len(args.user) < 1 or len(args.user) > USERML:
            errprint(CNFKEY_USER[0]
                     + ": User name must be 1-16 characters in length!")
            raise SystemExit(EXIT_SYNTAX)
        conf.setconf(CNFKEY_USER[1], args.user)


def main() -> int:
    """Program entry point.

    Parses CLI arguments, configures logging, initializes the server
    connection and curses display, runs a single game, and prints the
    result.

    Returns:
        int: An ``EXIT_*`` code indicating the outcome.
    """
    conf = Config()

    # Command line options and switches
    logfile = None  # Name of log file (if set with -L option)

    parser = argparse.ArgumentParser(description=Help.intro())
    parser.add_argument("-L", "--logfile", help="Specify name of log file.")
    parser.add_argument("-C", "--config", help="Read configuration from file.")
    vgroup = parser.add_mutually_exclusive_group()
    vgroup.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging (DEBUG)")
    vgroup.add_argument("-q", "--quiet", action="store_true",
                        help="Quiet logging (WARNING)")
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

    log_level = _determine_log_level(args)
    _configure_logging(args, log_level, logfile)

    _apply_cli_to_config(args, conf)

    # Connect to server (if requested)
    server = Server(conf)
    server.newgame()

    # Initialize display and playground
    pgr = Playground(conf, server)

    # Cleanup handler
    atexit.register(make_exithand(server, pgr))

    # Trap signals
    sigh = make_sighand(server, pgr)
    signal.signal(signal.SIGINT, sigh)
    signal.signal(signal.SIGHUP, sigh)
    signal.signal(signal.SIGQUIT, sigh)
    signal.signal(signal.SIGTERM, sigh)

    try:
        # Create playground objects
        pgr.feed()   # First piece of food
        pgr.bomb()   # First bomb
        pgr.draw()   # Draw complete playground

        # Create one snake
        worm = Worm(pgr, conf)

        # Determine initial moving direction
        worm.turn(worm.STEP_UP, worm.STEP_IDLE)

        # Draw the snake initially
        worm.draw()

        # Start playing
        worm.play()
    except Exception as e:
        # Ensure curses is restored and server is notified on errors
        logging.error("Runtime error during game: %s", e, exc_info=True)
        pgr.display.graphact()
        server.trap(-1)
        errprint("ERROR: An unexpected error occurred. See logs.")
        return EXIT_ERR

    # Report to server (if any)
    server.endgame(worm.getscore(), worm.getfailcode())

    try:
        pgr.keypause()
    finally:
        pgr.display.graphact()

    # Display score
    print("Score:   " + str(worm.getscore()))
    print("Failure: " + worm.getfailtext())

    # Log result
    logging.info('Ended. Score %s. Fail %s.',
                 str(worm.getscore()), worm.getfailtext())

    return EXIT_OK


# Stop program from being executed when running pydoc.
if __name__ == '__main__':
    sys.exit(main())
