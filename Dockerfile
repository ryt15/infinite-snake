FROM ubuntu:24.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-dev \
    python3-pip \
    g++ \
    make \
    libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic links for python3.12
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/bin/python

# Set working directory
WORKDIR /app

# Copy source files
COPY snake.py .
COPY snake++srv.cpp .
COPY makefile .

# Build C++ server using the existing makefile
RUN make snake++srv

# Make snake.py executable
RUN chmod +x snake.py

# Create entrypoint script for flexible execution
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Function to display usage\n\
usage() {\n\
    echo "Usage: $0 [server|client|game]"\n\
    echo "  server - Run C++ server (snake++srv)"\n\
    echo "  client - Run Python client connected to server"\n\
    echo "  game   - Run standalone Python game (default)"\n\
    echo ""\n\
    echo "Server options:"\n\
    echo "  docker run -p 8888:8888 <image> server"\n\
    echo ""\n\
    echo "Client options:"\n\
    echo "  docker run --network host <image> client [server_host] [server_port]"\n\
    echo "  docker run <image> client [server_host] [server_port]"\n\
    echo ""\n\
    echo "Game options:"\n\
    echo "  docker run -it <image> game [game_options]"\n\
    echo "  docker run -it <image> game --help"\n\
}\n\
\n\
case "${1:-game}" in\n\
    "server")\n\
        echo "Starting C++ Snake Server..."\n\
        exec ./snake++srv\n\
        ;;\n\
    "client")\n\
        SERVER_HOST=${2:-localhost}\n\
        SERVER_PORT=${3:-8888}\n\
        echo "Starting Snake Client connected to ${SERVER_HOST}:${SERVER_PORT}..."\n\
        exec ./snake.py -H "${SERVER_HOST}" -P "${SERVER_PORT}"\n\
        ;;\n\
    "game")\n\
        shift\n\
        echo "Starting Snake Game..."\n\
        exec ./snake.py "$@"\n\
        ;;\n\
    "help"|"-h"|"--help")\n\
        usage\n\
        ;;\n\
    *)\n\
        echo "Unknown command: $1"\n\
        usage\n\
        exit 1\n\
        ;;\n\
esac' > entrypoint.sh && \
    chmod +x entrypoint.sh

# Default command runs the game
ENTRYPOINT ["./entrypoint.sh"]
CMD ["game"]