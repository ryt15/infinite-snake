#!/usr/bin/python3
"""snake - a game to be run in a Linux or UNIX terminal.
For synopsis, see function usage(), or execute with the -h switch.

The main purpose of this program is not to play it, but to learn Python.
Start by studying it, then try to improve it. Some suggestions:
    0. Fix a bug
    1. Make the code more compact
    2. Implement new features from Python 3.10 or later
    3. Add a log file, allowing replay of earlier logged session
    4. Add colors and grapcial symbols
    5. Move all texts to separate text files (try Chinese, 中文!)
    6. Add more snakes
    7. Split the program into a client and a server (TCP or UDP)
    8. Add sound
    9. Create an API and read configuration from it
   10. Show several playgrounds on the same screen
   11. Add a dimension so the snake can also move in depth
   12. Rewrite the program into PHP, Kotlin, JavaScript, Go, C or C++
   13. Convert the program to a mobile app
   14. Make it possible for snakes to move between playgrounds
   15. Train a neural network (AI) to play the game
   16. Implement automated tests
   17. Implement revision control via Git
   18. Implement Docker

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
# import pdb

# Exit codes
EXIT_OK = 0     # All is well
EXIT_SYNTAX = 1 # Invalid command-line syntax
EXIT_ARGS = 2   # Invalid arguments
EXIT_SIGNAL = 3 # Termination signal received
EXIT_PROG = 4   # Program error - debugging required!

# Configuration CLI switches, config file keys and defaults
CNFKEY_ROWS = ['r', 'rows', 10]      # Playground size - rows
CNFKEY_COLS = ['c', 'cols', 20]      # Playground size - columns
CNFKEY_SLEN = ['l', 'snakelen', 3]   # Initial snake length
CNFKEY_TIMO = ['t', 'timeout', 300]  # Time in ms between snake moves



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
        self.pg = [[self.OBJ_EMPTY for cc in range(self.cols)] \
            for rr in range(self.rows)]
        self.display = Display(self.rows, self.cols, self.timo)
        self.win = self.display.win
        self.postoclean = [] # Positions needed to be cleaned
        # Mark borders
        # horizontal borders
        for cc in range(self.cols):
            self.pg[0][cc] = self.OBJ_BORDER
            self.pg[self.rows - 1][cc] = self.OBJ_BORDER
        # vertical borders
        for rr in range(self.rows):
            self.pg[rr][0] = self.OBJ_BORDER
            self.pg[rr][self.cols - 1] = self.OBJ_BORDER


    def feed(self):
        """ Place food at random coordinate """
        while True:
            foodpos = [random.randint(1, self.rows - 2), \
                    random.randint(1, self.cols - 2)]
            cell = self.atpos(foodpos[0], foodpos[1])
            if self.OBJ_EMPTY == cell & \
                (self.OBJ_FOOD | self.OBJ_BOMB | self.OBJ_SNAKE):
                break
        self.markpos(foodpos[0], foodpos[1], self.OBJ_FOOD)
        self.win.addch(foodpos[0], foodpos[1], self.VIS_FOOD)
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
        for pp in range(0, len(self.postoclean)):
            self.win.addch(int(self.postoclean[pp][0]), \
                int(self.postoclean[pp][1]), self.VIS_CLEANER)
        if need_refresh:
            self.win.refresh()


    def atpos(self, row, col):
        """ Returns what is at the given position, an OBJ_-mnemonic. """
        return self.pg[int(row)][int(col)]


    def markpos(self, row, col, what=OBJ_EMPTY) -> int:
        """ Mark this playground position as occupied by something
            indicated by what, which must be an OBJ_-mnemonic.
            If what is OBJ_EMPTY, all marks are reset at this position.
            Returns previous value.
        """
        was = self.atpos(int(row), int(col))
        self.pg[int(row)][int(col)] |= what
        if self.OBJ_EMPTY == what:
            self.pg[int(row)][int(col)] = self.OBJ_EMPTY
        return was


    def unmarkpos(self, row, col, what) -> int:
        """ Removes a mark from given position.
            Mark shall be an OBJ_-menmonic (set by markpos()).
            Returns previous value.
        """
        was = self.atpos(int(row), int(col))
        self.pg[int(row)][int(col)] &= ~what
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
        self.pg = playground    # Current playground
        self.cnf = cnf          # Configuration
        self.length = cnf.getconf(CNFKEY_SLEN[1])    # Expected length
        self.curlen = 1         # Current length including head
        # Set initial moving direction
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE
        # Set initial head position
        self.poss = [[row if row is not None else pg.rows / 2, \
                      col if col is not None else pg.cols / 2]]
        self.score = 0              # Score counter
        self.fail = self.FAIL_NONE  # Reason for Game Over

    def inclen(self):
        """ Increment length of snake """
        self.length += self.cnf.getconf(CNFKEY_SLEN[1])


    def draw(self):
        """ Draw the Snake visually """
        self.pg.cleanpos(False)
        self.pg.win.addch(int(self.poss[0][0]), int(self.poss[0][1]), self.HEAD)
        for tail in range(1, len(self.poss)):
            self.pg.win.addch(int(self.poss[tail][0]), \
                              int(self.poss[tail][1]), self.BODY)
        self.pg.win.refresh()


    def step(self):
        """ Move the Snake in current direction """
        if self.STEP_IDLE == self.rowstep and self.STEP_IDLE == self.colstep:
            # Snake is sleeping
            return self.FAIL_NONE
        newhead = [self.poss[0][0] + self.rowstep, \
                   self.poss[0][1] + self.colstep]
        cell = self.pg.atpos(newhead[0], newhead[1])
        if cell:
            self.pg.win.refresh()
        if cell & pg.OBJ_SNAKE:
            return self.FAIL_HITSNAKE
        if cell & pg.OBJ_BOMB:
            return self.FAIL_HITBOMB
        if cell & pg.OBJ_FOOD:
            pg.unmarkpos(self.poss[0][0], self.poss[0][1], pg.OBJ_FOOD)
            pg.feed()
            self.inclen()
        pg.markpos(self.poss[0][0], self.poss[0][1], pg.OBJ_SNAKE)
        self.poss.insert(0, newhead)
        if len(self.poss) > self.length:
            l = len(self.poss) - 1
            pg.setcleanpos(self.poss[l])
            pg.unmarkpos(self.poss[l][0], self.poss[l][1], pg.OBJ_SNAKE)
            self.poss.pop(l)
        # Check that snake is still inside the playground.
        # Actually we can also check if (cell & pg.BORDER)
        if self.poss[0][0] < 1: # Hit top
            return self.FAIL_HITHIGH
        if self.poss[0][1] < 1: # Hit left
            return self.FAIL_HITLEFT
        if self.poss[0][0] >= pg.rows - 1: # Hit bottom
            return self.FAIL_HITLOW
        if self.poss[0][1] >= pg.cols - 1: # Hit right
            return self.FAIL_HITRIGHT
        return self.FAIL_NONE


    def turn(self, rstep=None, cstep=None):
        """ Change current direction """
        self.rowstep = rstep if rstep is not None else self.STEP_IDLE
        self.colstep = cstep if cstep is not None else self.STEP_IDLE


    def getscore(self):
        """ Return current score """
        return self.score


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
            key = self.pg.win.getch()
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
        res_row = int(self.cnf.getconf(CNFKEY_ROWS[1])) - 1
        pg.win.addstr(res_row, 1, " Score: " + str(self.score) + " ")
        self.draw()
        return self.fail


class Help:
    """ Show help """
    usage_message = '''Usage: snake [-h] [-C cfile] [r rows] [-c cols] [-t to]
       -h: Show this help and exit
       -C: Read configuration from cfile
       -c: Set playground height (including borders)
       -r: Set playground width (including borders)
       -t: Set time in ms between snake steps
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
        if conffile is not None:
            self.readconf(conffile)

    def readconf(self, conffile=None):
        """ Process configuration file """
        self.conffile = conffile if conffile is not None else "snake.cnf"

        try:
            fp = open(self.conffile)
            cnf = fp.readlines()
            fp.close()
        except FileNotFoundError:
            errprint("Non-existing configuration file: " + self.conffile)
            sys.exit(EXIT_ARGS)
        except PermissionError:
            errprint("Unreadable configuration file: " + self.conffile)
            sys.exit(EXIT_ARGS)
        except IsADirectoryError:
            errprint("Configuration file is a directory: " + self.conffile)
            sys.exit(EXIT_ARGS)

        kv = re.compile('^[a-z]+: [a-zA-Z0-9]+')
        for line in cnf:
            if not kv.match(line):
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
        errprint("Invalid getconf(key=" + key + ")!")
        sys.exit(EXIT_PROG)


# Command line options and switches

conf = Config()
gotconf = False

try:
    for arg in range(1, len(sys.argv)):
        if '-h' == sys.argv[arg]:
            # Show help and exit
            Help.usage()
            sys.exit(EXIT_OK)
        if '-C' == sys.argv[arg]:
            # Read configuration from file
            if gotconf:
                errprint("-C can only be used once!")
                sys.exit(EXIT_SYNTAX)
            arg += 1
            conf.readconf(sys.argv[arg])
            gotconf = True
        if '-' + CNFKEY_ROWS[0] == sys.argv[arg]:
            # Set number of rows on playground
            arg += 1
            conf.setconf(CNFKEY_ROWS[1], sys.argv[arg])
        if '-' + CNFKEY_COLS[0] == sys.argv[arg]:
            # Set number of columns on playground
            arg += 1
            conf.setconf(CNFKEY_COLS[1], sys.argv[arg])
        if '-' + CNFKEY_SLEN[0] == sys.argv[arg]:
            # Set initial snake length
            arg += 1
            conf.setconf(CNFKEY_SLEN[1], sys.argv[arg])
        if '-' + CNFKEY_TIMO[0] == sys.argv[arg]:
            # Timeout in ms between movements
            arg += 1
            conf.setconf(CNFKEY_TIMO[1], sys.argv[arg])
except IndexError:
    errprint("Invalid arguments!")
    Help.usage()
    sys.exit(EXIT_SYNTAX)
except ValueError:
    errprint("Invalid argument or config value!")
    Help.usage()
    sys.exit(EXIT_SYNTAX)


# Initialize display and playground
pg = Playground(conf)


# Cleanup

def exithand():
    """ Cleanup environment before exiting """
    pg.display.graphact()

atexit.register(exithand)


# Signal trapping

def sighand(signum, frame):
    """ Signal handler callback """
    pg.display.graphact()
    errprint("Interrupted")
    sys.exit(EXIT_SIGNAL)

signal.signal(signal.SIGINT, sighand)
signal.signal(signal.SIGHUP, sighand)
signal.signal(signal.SIGQUIT, sighand)
signal.signal(signal.SIGTERM, sighand)


pg.feed()   # First piece of food
pg.bomb()   # First bomb
pg.draw()   # Draw complete playground


# Create one snake
worm = Worm(pg, conf)
# Determine initial moving direction
worm.turn(worm.STEP_UP, worm.STEP_IDLE)
# Draw the snake initially
worm.draw()

# Start playing
worm.play()

pg.keypause()

# Display score
pg.display.graphact()
print("Score:   " + str(worm.getscore()))
print("Failure: " + worm.getfailtext())

sys.exit(EXIT_OK)
