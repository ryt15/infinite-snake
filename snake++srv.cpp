/* snake++srv.cpp
 * This C++ program is intended to be run as a daemon where it serves
 * as a server to Snake game clients who wish to play net based,
 * allowing several players to participate on the same tournament.
 *
 * The main purpose of this program is just to demonstrate some C++.
 *
 * This variant is not a RESTful API! It uses standard TCP/IP client-
 * server connectivity.
 *
 * By Rein Ytterberg 2022-03-19
 */

#include <iostream>
#include <string>
#include <csignal>
#include <cstring>
#include <unistd.h>
#include <fcntl.h>

#include <stdarg.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <arpa/inet.h>

using namespace std;

/* Debugging and verbosity */
#define VERBOSE

/* Default values */
#define DEF_PORT    8888    /* Default port */


/* Exit and return codes */
class Exit {
    public:
        static const int OK =   0;  /* Success */
        static const int USER = 1;  /* Wrong syntax/user error */
        static const int ERR =  2;  /* Unrecoverable program error */
        static const int SIG =  3;  /* Terminated due to signal reception */
        static const int PROG = 4;  /* Source code error */
};


/* socker(action) values */
#define SOCKACT_START   0   /* Create socket */
#define SOCKACT_END     1   /* Destroy socket */


/* socker()
 * Creates or destroys the initial socket from which we shall accept
 * calls from clients. The socket is of TCP/IP stream type.
 * To create the socket, call with action=SOCKACT_START and port
 * set to a free and valid port number to listen to.
 * To destroy the socket, call with action=SOCKACT_END.
 * Successive calls with action=SOCKACT_END is permitted.
 * Successive calls with action=SOCKACT_START is permitted and
 * will result in a destruction of existing socket (if any) and
 * creation of a new (even if the port numbers don't change).
 * Returns the socket as a positive integer or -1 on failure and
 * after destroying the socket.
 */

class Socker {
    private:
        int sock = -1;
        int port = -1;
        struct sockaddr_in bound;

    public:
        Socker(int prt) {
            port = prt;
            start();
        }

        ~Socker() {
#ifdef VERBOSE
            cout << "~Socker()\n";
#endif
            end();
        }

        int getsock(void) {
            return sock;
        }

        int getport(void) {
            return port;
        }

        int active(void) {
            return sock >= 0;
        }

        int validport(void) {
            return port > 0;
        }

        int start() {
            if (active()) {
                end();
            }
            if (!validport()) {
                return -1;
            }
            if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
                cerr << "socket() error: " << strerror(errno) << "\n";
                return (sock = -1);
            }
            bound.sin_family = AF_INET;
            bound.sin_addr.s_addr = INADDR_ANY;
            bound.sin_port = htons(port);
            if ((bind(sock, (struct sockaddr *) &bound, sizeof(bound))) < 0) {
                end();
                cerr << "bind() error: " << strerror(errno) << "\n";
                return -1;
            }
            if (listen(sock, 5) != 0) {
                end();
                cerr << "listen() error: " << strerror(errno) << "\n";
                return -1;
            }
            return sock;
        }

        void end(void) {
#ifdef VERBOSE
            cout << "Socker.end()\n";
#endif
            if (active()) {
                close(sock);
                sock = -1;
            }
        }
};


/* session()
 * Handles a client session.
 * The client must be connected via the clisock socket.
 * The client parameter contains information about the client in
 * a record of size addrlen.
 * The client socket (clisock) is always closed on return.
 * Returns an Exit-constant indicating the result.
 */

static int session(int clisock, struct sockaddr_in client, socklen_t addrlen)
{
    int     retval;
    // struct timeval tv;
    char    message[1024];
    fd_set  rfds;
    int     done = 0;
    int     reads;

    if (clisock < 0) {
        return Exit::ERR;
    }

    if (fcntl(clisock, F_SETFL, O_NONBLOCK) < 0) {
        close(clisock);
        cerr << "fcntl() error: " << strerror(errno) << "\n";
        return Exit::ERR;
    }

    while (!done) {
        FD_ZERO(&rfds);
        FD_SET(clisock, &rfds);
        // tv.tv_sec = 10;
        // tv.tv_usec = 0;

        retval = select(clisock + 1, &rfds, NULL, NULL, NULL);

        if (retval) {
            sprintf(message, "200 OK\n");
            write(clisock, message, strlen(message));
        } else if (-1 == retval) {
            close(clisock);
            cerr << "select() error: " << strerror(errno) << "\n";
            return Exit::ERR;
        } else {
#ifdef VERBOSE
            cout << "Timeout!\n";
#endif
            done = 1;
            continue;
        }

        if ((reads = read(clisock, message, 1024)) > 0) {
            message[reads] = '\0';
#ifdef VERBOSE
            cout << "Read: " << message << "\n";
#endif
        }
        if (reads < 0) {
            cerr << "read() error: " << strerror(errno) << "\n";
            close(clisock);
            return Exit::ERR;
        }
    }

    close(clisock);
    return Exit::OK;
}


/* clients()
 * Accepts incoming clients and spawns a background process for
 * each ow them, to be further handled by the session() function.
 * Input parameter "sock" is the listener socket, returned from
 * function socker().
 * Returns an Exit-constant indicating success or failure.
 */

static int  clients(Socker *sock) {
    int                 clisock = -1;   // Socket to client
    socklen_t           addrlen;        // Address data size of client
    struct sockaddr_in  client;         // Client address data
    int                 retval;         // Arbitary return value

    if (!sock->active()) {
        return Exit::PROG;
    }

    addrlen = sizeof(struct sockaddr_in);

    for (;;) {
#ifdef VERBOSE
        cout << "Waiting for client at port " << sock->getport() << "\n";
#endif

        clisock = accept(sock->getsock(), (struct sockaddr *) &client,
            (socklen_t *) &addrlen);
        if (clisock < 0) {
            cerr << "accept() failed! " << strerror(errno) << "\n";
            return Exit::ERR;
        }
#ifdef VERBOSE
        cout << "Got client at port " << ntohs(client.sin_port) << "\n";
#endif

        switch (fork()) {
            case -1:
                cerr << "fork() failed! " << strerror(errno) << "\n";
                close(clisock);
                return Exit::ERR;
            case 0:
                close(clisock);
                break;
            default:
                retval = session(clisock, client, addrlen);
                if (Exit::OK != retval) {
                    return retval;
                }
        }
    }

    return Exit::OK;
}


/* usage()
 * Prints syntax help to given output.
 */

static void usage(ostream& ofd) {
    ofd << "Usage: snake++srv [-p port] [-h]\n";
    ofd << "       Starts the snake server.\n";
    ofd << "    -p port: Port to listen to. Default " << DEF_PORT << ".\n";
    ofd << "    -h Show this help and exit.\n";
}


/* termsig()
 * Terminates the program (and sub process) on reception of signals.
 */

static void termsig(int sig) {
    cerr << "Terminated by signal " << sig << ".\n";
    exit(Exit::SIG);
}


int main(int argc, char **argv) {
    Socker *sock;
    int port = DEF_PORT;
    int ret = Exit::OK;
    int opt;
    long lport = -1L;


    /* Trap termination signals */
    signal(SIGINT, termsig);
    signal(SIGTERM, termsig);

    /* Handle command line options */
    while ((opt = getopt(argc, argv, "p:h")) != -1) {
        switch (opt) {
            case 'p':   // Listening port
                errno = 0;
                lport = strtol(optarg, NULL, 0);
                if (errno || ((unsigned long) lport > 65535) || lport < 1) {
                    cerr << "Port number (-p) must be numeric!\n";
                    usage(cerr);
                    return Exit::USER;
                }
#ifdef VERBOSE
                cout << "Listening port: " << lport << "\n";
#endif
                port = atoi(optarg);
                break;

            case 'h':   // Help
                usage(cout);
                return Exit::OK;

            default:
                usage(cerr);
                return Exit::USER;
        }
    }

    /* Create listener socket */
    if ((sock = new Socker(port)) < 0) {
        cerr << "socket() failed (errno " << errno << ") " <<
            strerror(errno) << "\n";
        return Exit::ERR;
    }

    /* Handle calling clients */
    ret = clients(sock);

    sock->end();

    return Exit::OK;
}
