/* snakesrv.c
 * This is the C variant of the server for the Snake game.
 * By Rein Ytterberg 2022-03-17.
 */

#include <stdio.h>
#include <signal.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <arpa/inet.h>

/* Default values */
#define DEF_PORT    8888    /* Default port */


/* Exit and return codes */
#define EXIT_OK     0   /* Success */
#define EXIT_USER   1   /* Wrong syntax/user error */
#define EXIT_ERR    2   /* Unrecoverable program error */
#define EXIT_SIG    3   /* Terminated due to signal reception */
#define EXIT_PROG   4   /* Source code error */


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

static int socker(int action, ...) {
    static int sock = -1;
    struct sockaddr_in bound;
    va_list args;
    int port = -1;

    switch (action) {
        case SOCKACT_START:
            if (-1 != sock) {
                socker(SOCKACT_END);
            }
            va_start(args, action);
            port = va_arg(args, int);
            va_end(args);
            if (port < 0) {
                return -1;
            }
            if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
                return (sock = -1);
            }
            bound.sin_family = AF_INET;
            bound.sin_addr.s_addr = INADDR_ANY;
            bound.sin_port = htons(port);
            if ((bind(sock, (struct sockaddr *) &bound, sizeof(bound))) < 0) {
                socker(SOCKACT_END);
                return -1;
            }
            if (listen(sock, 5) != 0) {
                socker(SOCKACT_END);
                return -1;
            }
            break;

        case SOCKACT_END:
            if (-1 != sock) {
                close(sock);
                sock = -1;
            }
            break;
    }
    return sock;
}


/* session()
 * Handles a client session.
 * The client must be connected via the clisock socket.
 * The client parameter contains information about the client in
 * a record of size addrlen.
 * The client socket (clisock) is always closed on return.
 * Returns an EXIT_-constant indicating the result.
 */

static int session(int clisock, struct sockaddr_in client, socklen_t addrlen)
{
    int     retval;
    struct timeval tv;
    char    message[1024];
    fd_set  rfds;
    int     done = 0;
    int     reads;

    if (clisock < 0) {
        return EXIT_ERR;
    }

    if (fcntl(clisock, F_SETFL, O_NONBLOCK) < 0) {
        close(clisock);
        return EXIT_ERR;
    }

    printf("Waiting for input.\n");

    while (!done) {
        FD_ZERO(&rfds);
        FD_SET(clisock, &rfds);
        // tv.tv_sec = 10;
        // tv.tv_usec = 0;

        retval = select(clisock + 1, &rfds, NULL, NULL, NULL);

        if (retval) {
            sprintf(message,
                "HTTP/1.1 200 OK\n\n<html><head><title>Test</title>"
                "<body><p>Hello, World!</p></body></html>\n");
            write(clisock, message, strlen(message));
        } else if (-1 == retval) {
            close(clisock);
            printf("select() error.\n");
            return EXIT_ERR;
        } else {
            printf("Timeout!\n");
            done = 1;
            continue;
        }

        if ((reads = read(clisock, message, 1024)) > 0) {
            message[reads] = '\0';
            printf("Read: %s\n", message);
        }
        if (reads < 0) {
            printf("errno %d: %s\n", errno, strerror(errno));
            close(clisock);
            return EXIT_ERR;
        }
    }

    close(clisock);
    return EXIT_OK;
}


/* clients()
 * Accepts incoming clients and spawns a background process for
 * each ow them, to be further handled by the session() function.
 * Input parameter "sock" is the listener socket, returned from
 * function socker().
 * Returns an EXIT_-constant indicating success or failure.
 */

static int  clients(int sock) {
    int                 clisock = -1;   // Socket to client
    socklen_t           addrlen;        // Address data size of client
    struct sockaddr_in  client;         // Client address data
    int                 retval;         // Arbitary return value

    if (sock < 0) {
        return EXIT_PROG;
    }

    addrlen = sizeof(struct sockaddr_in);

    for (;;) {
        printf("Waiting for client!\n");

        clisock = accept(sock, (struct sockaddr *) &client,
            (socklen_t *) &addrlen);
        if (clisock < 0) {
            return EXIT_ERR;
        }
        printf("Got client at port %d.\n", ntohs(client.sin_port));

        switch (fork()) {
            case -1:
                fprintf(stderr, "fork() failed!\n");
                close(clisock);
                return EXIT_ERR;
            case 0:
                close(clisock);
                break;
            default:
                retval = session(clisock, client, addrlen);
                if (EXIT_OK != retval) {
                    return retval;
                }
        }
    }

    return EXIT_OK;
}



/* termsig()
 * Terminates the program (and sub process) on reception of signals.
 */

static void termsig(int sig) {
    socker(SOCKACT_END);
    fprintf(stderr, "Terminated by signal %d.\n", sig);
    exit(EXIT_SIG);
}

/* usage()
 * Prints syntax help to given output.
 */

static void usage(FILE *ofd) {
    fprintf(ofd, "Usage: snakesrv [-p port] [-h]\n");
    fprintf(ofd, "       Starts the snake server.\n");
    fprintf(ofd, "    -p port: Port to listen to. Default %d.\n", DEF_PORT);
    fprintf(ofd, "    -h Show this help and exit.\n");
}


int main(int argc, char **argv) {
    int sock;
    int port = DEF_PORT;
    int ret = EXIT_OK;
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
                    fprintf(stderr, "Port number (-p) must be numeric!\n");
                    usage(stderr);
                    return EXIT_USER;
                }
                printf("lport: %ld\n", lport);
                port = atoi(optarg);
                break;

            case 'h':   // Help
                usage(stdout);
                return EXIT_OK;

            default:
                usage(stderr);
                return EXIT_USER;
        }
    }

    /* Create listener socket */
    if ((sock = socker(SOCKACT_START, port)) < 0) {
        fprintf(stderr, "socket() failed (errno %d) %s.\n",
            errno, strerror(errno));
        return EXIT_ERR;
    }

    /* Handle calling clients */
    ret = clients(sock);

    socker(SOCKACT_END);

    return ret;
}
