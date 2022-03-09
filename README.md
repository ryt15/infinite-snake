# infinite-snake

## Purpose

This is the standard, boring, Snake program that everyone knows. The intention is not to play it,
but to use it as an example to learn programming from.

## Recommended Actions

I suggest you start by playing it a few times. The basic version is written in Python but it uses the semi-graphic
library curses, so it's intended to be used on a UNIX or Linux machine. If you don't have any and are stuck with
Windows, try to install a Virtual Machine with Linux on it and run it from there.

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
- Split the program into a client and a server which communicate via tcp/ip or udp/ip.
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
- Analyze the source code with pylint and make that a habit. Start by fixing some of the existing complaints.


## Synopsis

```
./snake.py [-h] [-C cfile] [r rows] [-c cols] [-t to] [-L lf]
           -h: Show this help and exit
           -C: Read configuration from cfile
           -c: Set playground height (including borders)
           -r: Set playground width (including borders)
           -t: Set time in ms between snake steps
           -L: Log to file lf
```
