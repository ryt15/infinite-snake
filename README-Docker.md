# Docker Setup for Infinite Snake

This directory contains Docker configuration for running the Snake game and server.

## Quick Start

### Build the Docker image
```bash
docker build -t infinite-snake .
```

### Run the game only
```bash
docker run -it infinite-snake
```

### Run with server (using docker-compose)
```bash
# Start server in background
docker-compose up snake-server -d

# Run game connected to server
docker run -it --network container:snake-server infinite-snake ./snake.py -H localhost -P 8888
```

### Using docker-compose (recommended)
```bash
# Start both services
docker-compose up

# Or start individually
docker-compose up snake-server  # Start server only
docker-compose up snake        # Start game only
```

## Manual Server Setup

### Start server manually
```bash
docker run -d --name snake-server -p 8888:8888 infinite-snake ./snake++srv
```

### Connect game to server
```bash
docker run -it --rm --network host infinite-snake ./snake.py -H localhost -P 8888
```

## Game Options

The game supports various command-line options:

```bash
# Basic game
docker run -it infinite-snake ./snake.py

# With custom settings
docker run -it infinite-snake ./snake.py -r 20 -c 30 -t 200

# With logging
docker run -it -v $(pwd)/logs:/app/logs infinite-snake ./snake.py -L /app/logs/game.log

# Verbose output
docker run -it infinite-snake ./snake.py -v

# Help
docker run -it infinite-snake ./snake.py --help
```

## Available Commands

- `./snake.py` - Run the Snake game
- `./snake++srv` - Run the C++ server
- `make` - Build the C++ server (already done in image)

## Troubleshooting

### If curses display issues occur:
```bash
docker run -it --rm infinite-snake bash
# Then run: ./snake.py
```

### View server logs:
```bash
docker logs snake-server
```

### Clean up containers:
```bash
docker-compose down
docker system prune -f
```

## Development

To rebuild after code changes:
```bash
docker build --no-cache -t infinite-snake .
```

