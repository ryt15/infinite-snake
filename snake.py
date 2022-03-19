#!/usr/bin/python3
"""snake - a game to be run in a Linux or UNIX terminal.
For synopsis, see function usage(), or execute with the -h switch.

The main purpose of this program is not to play it, but to learn Python.
Start by studying it, then try to improve it. See README.md.

By Rein Ytterberg 2020.
For Python version 3.8
"""

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
from datetime import datetime
# import pdb

# Version (as presented to server)
CLIVER = "0.1"

# Exit codes
EXIT_OK = 0     # All is well
EXIT_SYNTAX = 1 # Invalid command-line syntax
EXIT_ARGS = 2   # Invalid arguments
EXIT_SIGNAL = 3 # Termination signal received
EXIT_PROG = 4   # Program error - debugging required!
EXIT_ERR = 5    # Execution error

# Configuration CLI switches, config file keys and defaults
CNFKEY_ROWS = ['r', 'rows', 10]      # Playground size - rows
CNFKEY_COLS = ['c', 'cols', 20]      # Playground size - columns
CNFKEY_SLEN = ['l', 'snakelen', 3]   # Initial snake length
CNFKEY_TIMO = ['t', 'timeout', 300]  # Time in ms between snake moves
CNFKEY_PORT = ['P', 'port', 0]       # Server port
CNFKEY_HOST = ['H', 'host', '']      # Server host



def errprint(*args, **kargs):
    """ Print to stderr """
    print(*args, file=sys.stderr, **kargs)


class Display:
    """ Sets up and restores the entire display """
    graphics_active = False     # Graphics initialized?

    def __init__(self, rows, cols, timo=0):
        self.rows = rows
        self.cols = cols
        self.timo = timo
        self.win = self.graphact(rows, cols, timo)

    def getwin(self):
        """ Return window handler """
        return self.win

    def graphact(self, rows=0, cols=0, timo=0):
        """ Switch terminal into graphics mode, or resume from it.
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
            errprint("Can't make playground " + str(rows) + " rows.")
            errprint("Minimum row size is 3.")
            sys.exit(EXIT_ARGS)
        if cols < 3:
            errprint("Can't make playground " + str(cols) + " columns.")
            errprint("Minimum column size is 3.")
            sys.exit(EXIT_ARGS)
        # Initialize display
        scr = curses.initscr()
        curses.curs_set(0)
        srows, scols = scr.getmaxyx()
        # Playground too large?
        if rows > srows:
            curses.endwin()
            errprint("Can't make playground " + str(rows) + " rows.")
            errprint("Maximum row size is " + str(srows) + ".")
            sys.exit(EXIT_ARGS)
        if cols > scols:
            curses.endwin()
            errprint("Can't make playground " + str(cols) + " columns.")
            errprint("Maximum column size is " + str(scols) + ".")
            sys.exit(EXIT_ARGS)
        # Create the playground on the display
        win = curses.newwin(rows, cols, 0, 0)
        win.keypad(1)
        win.timeout(timo)
        self.graphics_active = True
        return win


class Playground:
    """ The visible area where the snake(s) move, including borders.
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


    def __init__(self, cnf):
        self.rows = cnf.getconf(CNFKEY_ROWS[1])
        self.cols = cnf.getconf(CNFKEY_COLS[1])
        self.timo = cnf.getconf(CNFKEY_TIMO[1])
        self.pgr = [[self.OBJ_EMPTY for cc in range(self.cols)] \
            for rr in range(self.rows)]
        self.display = Display(self.rows, self.cols, self.timo)
        self.win = self.display.getwin()
        self.postoclean = [] # Positions needed to be cleaned
        # Mark borders
        # horizontal borders
        for col in range(self.cols):
            self.pgr[0][col] = self.OBJ_BORDER
            self.pgr[self.rows - 1][col] = self.OBJ_BORDER
        # vertical borders
        for row in range(self.rows):
            self.pgr[row][0] = self.OBJ_BORDER
            self.pgr[row][self.cols - 1] = self.OBJ_BORDER


    def feed(self):
        """ Place food at random coordinate """
        while True:
            foodpos = [random.randint(1, self.rows - 2), \
                    random.randint(1, self.cols - 2)]
            cell = self.atpos(foodpos[0], foodpos[1])
            if self.OBJ_EMPTY == cell & \
                (self.OBJ_FOOD | self.OBJ_BOMB | self.OBJ_SNAKE):
                break
        logging.debug('feed %s %s, %s, %s', \
            datetime.now().strftime('%H:%M:%S %f'), \
            str(foodpos[0]), str(foodpos[1]), str(cell))
        self.markpos(foodpos[0], foodpos[1], self.OBJ_FOOD)
        self.win.addch(foodpos[0], foodpos[1], self.VIS_FOOD)
        self.win.addstr(0, 2, "  Food: " + str(int(foodpos[0])) + \
            " " + str(int(foodpos[1])) + "  ")
        self.win.refresh()


    def bomb(self):
        """ Place bomb at random coordinate """
        while True:
            bombpos = [random.randint(1, self.rows - 2), \
                    random.randint(1, self.cols - 2)]
            cell = self.atpos(bombpos[0], bombpos[1])
            if self.OBJ_EMPTY == cell & \
                (self.OBJ_FOOD | self.OBJ_BOMB | self.OBJ_SNAKE):
                break
        self.markpos(bombpos[0], bombpos[1], self.OBJ_BOMB)
        self.win.addch(bombpos[0], bombpos[1], self.VIS_BOMB)
        self.win.refresh()


    def setcleanpos(self, pos):
        """ Save coordinates for a position that needs to be cleaned """
        self.postoclean.insert(0, pos)


    def cleanpos(self, need_refresh=False):
        """ Visibly cleans up the Playground """
        # Blank positions that were marked by call to setcleanpos()
        for pos in range(0, len(self.postoclean)):
            self.win.addch(int(self.postoclean[pos][0]), \
                int(self.postoclean[pos][1]), self.VIS_CLEANER)
        if need_refresh:
            self.win.refresh()


    def atpos(self, row, col):
        """ Returns what is at the given position, an OBJ_-mnemonic. """
        return self.pgr[int(row)][int(col)]


    def markpos(self, row, col, what=OBJ_EMPTY) -> int:
        """ Mark this playground position as occupied by something
            indicated by what, which must be an OBJ_-mnemonic.
            If what is OBJ_EMPTY, all marks are reset at this position.
            Returns previous value.
        """
        was = self.atpos(int(row), int(col))
        self.pgr[int(row)][int(col)] |= what
        if self.OBJ_EMPTY == what:
            self.pgr[int(row)][int(col)] = self.OBJ_EMPTY
        logging.debug('mark %s %s, %s, %s', \
            datetime.now().strftime('%H:%M:%S %f'), \
	    str(int(row)), str(int(col)), str(what))
        return was


    def unmarkpos(self, row, col, what) -> int:
        """ Removes a mark from given position.
            Mark shall be an OBJ_-menmonic (set by markpos()).
            Returns previous value.
        """
        was = self.atpos(int(row), int(col))
        self.pgr[int(row)][int(col)] &= ~what
        logging.debug('umrk %s %s, %s, %s', \
            datetime.now().strftime('%H:%M:%S %f'), \
	    str(int(row)), str(int(col)), str(what))
        return was


    def draw(self):
        """ Draw the playground """
        self.win.border(curses.ACS_VLINE)
        self.win.refresh()


    def keypause(self):
        """ Deactivates keyboard timeout and waits for keypress """
        self.win.timeout(-1)
        self.win.getch()


class Worm:
    """ A Snake/Worm that crawls across the Playground """
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


    def __init__(self, playground, cnf, \
        row=None, col=None, rstep=None, cstep=None):
        self.pgr = playground    # Current playground
        self.cnf = cnf          # Configuration
        self.length = cnf.getconf(CNFKEY_SLEN[1])    # Expected length
        self.curlen = 1         # Current length including head
        # Set initial moving direction
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE
        # Set initial head position
        self.poss = [[row if row is not None else self.pgr.rows / 2, \
                      col if col is not None else self.pgr.cols / 2]]
        self.score = 0              # Score counter
        self.fail = self.FAIL_NONE  # Reason for Game Over

    def inclen(self):
        """ Increment length of snake """
        self.length += self.cnf.getconf(CNFKEY_SLEN[1])


    def draw(self):
        """ Draw the Snake visually """
        self.pgr.cleanpos(False)
        self.pgr.win.addch(int(self.poss[0][0]), int(self.poss[0][1]), \
            self.HEAD)
        for tail in range(1, len(self.poss)):
            self.pgr.win.addch(int(self.poss[tail][0]), \
                              int(self.poss[tail][1]), self.BODY)
        self.pgr.win.refresh()


    def step(self):
        """ Move the Snake in current direction """
        needfood = False
        if self.STEP_IDLE == self.rowstep and self.STEP_IDLE == self.colstep:
            # Snake is sleeping
            return self.FAIL_NONE
        # Calculate next position for snake's head
        newhead = [self.poss[0][0] + self.rowstep, \
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
            logging.debug('step %s %s, %s', \
                datetime.now().strftime('%H:%M:%S %f'), \
                str(int(newhead[0])), str(int(newhead[1])))
            self.pgr.unmarkpos(newhead[0], newhead[1], self.pgr.OBJ_FOOD)
            needfood = True
            self.inclen()
        self.pgr.markpos(newhead[0], newhead[1], self.pgr.OBJ_SNAKE)
        if needfood:
            self.pgr.feed()
        self.poss.insert(0, newhead)
        if len(self.poss) > self.length:
            last = len(self.poss) - 1
            self.pgr.setcleanpos(self.poss[last])
            self.pgr.unmarkpos(self.poss[last][0], self.poss[last][1], \
                self.pgr.OBJ_SNAKE)
            self.poss.pop(last)
        # Check that snake is still inside the playground.
        # Actually we can also check if (cell & self.pgr.BORDER)
        if self.poss[0][0] < 1: # Hit top
            return self.FAIL_HITHIGH
        if self.poss[0][1] < 1: # Hit left
            return self.FAIL_HITLEFT
        if self.poss[0][0] >= self.pgr.rows - 1: # Hit bottom
            return self.FAIL_HITLOW
        if self.poss[0][1] >= self.pgr.cols - 1: # Hit right
            return self.FAIL_HITRIGHT
        return self.FAIL_NONE


    def turn(self, rstep=None, cstep=None):
        """ Change current direction """
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE


    def getscore(self):
        """ Return current score """
        return self.score


    def getfailcode(self):
        """ Return numerical reason for failed game """
        return self.fail


    def getfailtext(self, fail=-1) -> str:
        """ Convert fail code (FAIL_-mnemonic) to text.
        Without parameter, the object's failure text is returned.
        With parameter, requested code is converted to text.
        """
        if -1 == fail:
            return self.FAILTEXT[self.fail]
        try:
            return self.FAILTEXT[fail]
        except KeyError:
            errprint("Program error - illegal index (" + str(fail) + ")")
            # for line in traceback.format_stack():
            line = traceback.format_stack()[0]
            errprint(line.strip())
            sys.exit(EXIT_PROG)


    def play(self):
        """ Main loop. Returns failure as FAIL_-mnemonic """
        while self.FAIL_NONE == self.fail:
            key = self.pgr.win.getch()
            if curses.KEY_DOWN == key:
                self.turn(self.STEP_DOWN)
            if curses.KEY_LEFT == key:
                self.turn(None, self.STEP_LEFT)
            if curses.KEY_RIGHT == key:
                self.turn(None, self.STEP_RIGHT)
            if curses.KEY_UP == key:
                self.turn(self.STEP_UP)
            self.fail = self.step()
            if not self.fail:
                self.score += 1
                self.draw()

        # Show the score
        score_row = int(self.cnf.getconf(CNFKEY_ROWS[1])) - 1
        self.pgr.win.addstr(score_row, 2, " Score: " + str(self.score) + " ")
        self.draw()
        return self.fail


class Help:
    """ Show help """
    usage_message = \
    '''Usage: snake [-h] [-C cfile] [r rows] [-c cols] [-t to] [-L lf]
                    [-P port -H host]
       -h: Show this help and exit
       -C: Read configuration from cfile
       -c: Set playground height (including borders)
       -r: Set playground width (including borders)
       -t: Set time in ms between snake steps
       -L: Log to file lf
       -P, -H Connect to server host at given port
    '''
    @classmethod
    def usage(cls):
        """ Print usage message """
        print(cls.usage_message)


# Configuration

class Config:
    """ Configuration of one game instance """

    def __init__(self, conffile=None):
        self.conffile = conffile     # Configuration file
        self.cnfval_rows = CNFKEY_ROWS[2]
        self.cnfval_cols = CNFKEY_COLS[2]
        self.cnfval_slen = CNFKEY_SLEN[2]
        self.cnfval_timo = CNFKEY_TIMO[2]
        self.cnfval_port = CNFKEY_PORT[2]
        self.cnfval_host = CNFKEY_HOST[2]
        if conffile is not None:
            self.readconf(conffile)

    def readconf(self, conffile=None):
        """ Process configuration file """
        self.conffile = conffile if conffile is not None else "snake.cnf"

        try:
            conff = open(self.conffile)
            cnf = conff.readlines()
            conff.close()
        except FileNotFoundError:
            errprint("Non-existing configuration file: " + self.conffile)
            sys.exit(EXIT_ARGS)
        except PermissionError:
            errprint("Unreadable configuration file: " + self.conffile)
            sys.exit(EXIT_ARGS)
        except IsADirectoryError:
            errprint("Configuration file is a directory: " + self.conffile)
            sys.exit(EXIT_ARGS)

        keyval = re.compile('^[a-z]+: [a-zA-Z0-9]+')
        for line in cnf:
            if not keyval.match(line):
                continue
            keypos = re.search(r"\s", line).start()
            key = line[:keypos - 1]
            val = line[keypos:].strip()
            self.setconf(key, val)

    def setconf(self, key, val):
        """ Assign configurable value to a key """
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
        errprint("Invalid setconf(key=" + key + ")!")
        sys.exit(EXIT_PROG)

    def getconf(self, key):
        """ Return a configuration value """
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
        errprint("Invalid getconf(key=" + key + ")!")
        sys.exit(EXIT_PROG)


class Server:
    """ Handle connection to Snake server (snakesrv).
    If both a server host name or IP address and a port to it is
    assigned, the program shall connect to it. If none or only one
    of the values is set, server connection will be silently ignored.
    Connection uses TCP/IP sockets.
    The server must be running.
    """

    def __init__(self, cnf=None):
        self.use = False    # True if we're connected to a server
        self.cnf = cnf
        if cnf is None:
            return
        host = cnf.getconf(CNFKEY_HOST[1])
        port = cnf.getconf(CNFKEY_PORT[1])
        if port is None or 0 == port:
            return
        if host is None or '' == host:
            return
        self.use = True
        self.host = host
        self.port = port
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            # self.send(b"Spenatgnebb")
            # ret = self.sock.recv(1024)
            # print(f"Socket ret: {ret!r}")
        except ConnectionRefusedError:
            self.use = False
            errprint("Server " + host + " refuses connection on port " + \
                str(port) + ".")
            self.sock.close()
            sys.exit(EXIT_ERR)

    def send(self, data):
        """ Sends a sequence to the server if connected """
        if self.use is False:
            return
        # print("send: self.sock ", self.sock);
        self.sock.sendall(data)

    def recv(self, maxlen=1024) -> str:
        """ Receives a string from server if connected """
        if self.use is False:
            return None
        ret = self.sock.recv(maxlen).decode()
        return ret

    def newgame(self):
        """ Reports start of a new game to the server, if connected """
        head = ('G>BEG,VER:' + CLIVER).encode()
        self.send(head)
        self.recv(1024)
        head = ('G>R:' + str(self.cnf.getconf(CNFKEY_ROWS[1])) + ',C:' + \
            str(self.cnf.getconf(CNFKEY_COLS[1]))).encode()
        self.send(head)
        self.recv(1024)
        head = ('G>S:' + str(self.cnf.getconf(CNFKEY_SLEN[1])) + ',T:' + \
            str(self.cnf.getconf(CNFKEY_TIMO[1]))).encode()
        self.send(head)
        self.recv(1024)

    def endgame(self, score, failcode, sig=-1):
        """ Reports status about ended game to the server, if connected """
        head = 'G>END,SCR:' + str(score) + ',SIG:' + str(sig) + ',FAI:' + \
            str(failcode)
        self.send(head.encode())
        self.recv(1024)

    def stop(self):
        """ Closes connection to server, if connected """
        if self.use is True:
            self.sock.close()

    def trap(self, sig):
        """ Terminates server connection on signal reception """
        if self.use is True:
            self.endgame(-1, -1, sig)
            self.sock.close()



CONF = Config()
GOTCONF = False




# Command line options and switches

LOGFILE = None  # Name of log file (if set with -L option)

try:
    for arg in range(1, len(sys.argv)):
        if '-h' == sys.argv[arg]:
            # Show help and exit
            Help.usage()
            sys.exit(EXIT_OK)
        if '-L' == sys.argv[arg]:
            # Set log file
            arg += 1
            LOGFILE = sys.argv[arg]
            if os.path.exists(LOGFILE):
                mystat = os.stat(sys.argv[0])
                lfstat = os.stat(LOGFILE)
                if mystat.st_dev == lfstat.st_dev and \
                    mystat.st_ino == lfstat.st_ino:
                    errprint("ERROR: Log file (-L) same as program file!")
                    sys.exit(EXIT_ARGS)
            logging.basicConfig(filename=LOGFILE, level=logging.INFO)
            now = datetime.now()
            logging.info('Started %s', now.strftime('%H:%M:%S %f'))
        if '-C' == sys.argv[arg]:
            # Read configuration from file
            if GOTCONF:
                errprint("-C can only be used once!")
                sys.exit(EXIT_SYNTAX)
            arg += 1
            CONF.readconf(sys.argv[arg])
            GOTCONF = True
        if '-' + CNFKEY_ROWS[0] == sys.argv[arg]:
            # Set number of rows on playground
            arg += 1
            CONF.setconf(CNFKEY_ROWS[1], sys.argv[arg])
        if '-' + CNFKEY_COLS[0] == sys.argv[arg]:
            # Set number of columns on playground
            arg += 1
            CONF.setconf(CNFKEY_COLS[1], sys.argv[arg])
        if '-' + CNFKEY_SLEN[0] == sys.argv[arg]:
            # Set initial snake length
            arg += 1
            CONF.setconf(CNFKEY_SLEN[1], sys.argv[arg])
        if '-' + CNFKEY_TIMO[0] == sys.argv[arg]:
            # Timeout in ms between movements
            arg += 1
            CONF.setconf(CNFKEY_TIMO[1], sys.argv[arg])
        if '-' + CNFKEY_PORT[0] == sys.argv[arg]:
            # Server port
            arg += 1
            CONF.setconf(CNFKEY_PORT[1], sys.argv[arg])
        if '-' + CNFKEY_HOST[0] == sys.argv[arg]:
            # Server host
            arg += 1
            CONF.setconf(CNFKEY_HOST[1], sys.argv[arg])
except IndexError:
    errprint("Invalid arguments!")
    Help.usage()
    sys.exit(EXIT_SYNTAX)
except ValueError:
    errprint("Invalid argument or config value!")
    Help.usage()
    sys.exit(EXIT_SYNTAX)


# Connect to server (if requested)
SERVER = Server(CONF)
SERVER.newgame()


# Initialize display and playground
PGR = Playground(CONF)


# Cleanup handler

def exithand():
    """ Cleanup environment before exiting """
    SERVER.stop()
    PGR.display.graphact()

atexit.register(exithand)


# Signal trapping

def sighand(signum, frame):
    """ Signal handler callback """
    del frame
    PGR.display.graphact()
    errprint("Interrupted")
    SERVER.trap(signum)
    sys.exit(EXIT_SIGNAL)

signal.signal(signal.SIGINT, sighand)
signal.signal(signal.SIGHUP, sighand)
signal.signal(signal.SIGQUIT, sighand)
signal.signal(signal.SIGTERM, sighand)


PGR.feed()   # First piece of food
PGR.bomb()   # First bomb
PGR.draw()   # Draw complete playground


# Create one snake
WORM = Worm(PGR, CONF)
# Determine initial moving direction
WORM.turn(WORM.STEP_UP, WORM.STEP_IDLE)
# Draw the snake initially
WORM.draw()

# Start playing
WORM.play()

# Report to server (if any)
SERVER.endgame(WORM.getscore(), WORM.getfailcode())

PGR.keypause()
PGR.display.graphact()

# Display score
print("Score:   " + str(WORM.getscore()))
print("Failure: " + WORM.getfailtext())

# Log result
NOW = datetime.now()
logging.info('Ended %s. Score %s. Fail %s.', \
    NOW.strftime('%H:%M:%S %f'), str(WORM.getscore()), WORM.getfailtext())

sys.exit(EXIT_OK)
