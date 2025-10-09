# Docker Setup for Snake Game

This Docker setup provides both the Python Snake game (`snake.py`) and C++ server (`snake++srv`) built on Ubuntu 24.04 with Python 3.12 and g++.

## Quick Start

### Build the Docker Image
```bash
docker build -t snake-game .
```

## Running Options

### 1. Standalone Game (Default)
```bash
# Run the game without server
docker run -it snake-game

# With custom options
docker run -it snake-game game -r 20 -c 30 -t 200 -v

# Get help
docker run -it snake-game game --help
```

### 2. Client-Server Setup

#### Option A: Using Docker Compose (Recommended)
```bash
# Start server and client together
docker-compose --profile client up

# Start server only
docker-compose up snake-server

# Start standalone game
docker-compose --profile standalone up snake-game
```

#### Option B: Manual Setup
```bash
# Start server
docker run -d --name snake-server -p 8888:8888 snake-game server

# Connect client (option 1: using host network)
docker run -it --rm --network host snake-game client localhost 8888

# Connect client (option 2: using container network)
docker run -it --rm --link snake-server:server snake-game client server 8888
```

## Build Commands

### Build Image
```bash
docker build -t snake-game .
```

### Build with No Cache
```bash
docker build --no-cache -t snake-game .
```

### Build Specific Tag
```bash
docker build -t snake-game:latest -t snake-game:v1.0 .
```

## Run Commands

### Server Commands
```bash
# Run server on default port 8888
docker run -d -p 8888:8888 snake-game server

# Run server with custom port
docker run -d -p 9999:9999 snake-game server

# View server logs
docker logs snake-server
```

### Client Commands
```bash
# Connect to localhost server
docker run -it snake-game client localhost 8888

# Connect to remote server
docker run -it snake-game client 192.168.1.100 8888

# Connect with custom game settings
docker run -it snake-game client localhost 8888 -r 25 -c 40
```

### Game Commands
```bash
# Basic game
docker run -it snake-game game

# Game with verbose logging
docker run -it snake-game game -v

# Game with custom settings
docker run -it snake-game game -r 20 -c 30 -l 5 -t 150

# Game with logging to file
docker run -it -v $(pwd)/logs:/app/logs snake-game game -L /app/logs/game.log
```

## Docker Compose Profiles

### Available Profiles:
- `client`: Runs both server and client
- `standalone`: Runs standalone game only

### Usage:
```bash
# Run client-server setup
docker-compose --profile client up

# Run standalone game
docker-compose --profile standalone up

# Run server only
docker-compose up snake-server

# Stop all services
docker-compose down
```

## Network Configuration

### Host Network (Simplest)
```bash
# Server
docker run -d --network host snake-game server

# Client
docker run -it --network host snake-game client localhost 8888
```

### Bridge Network (Default)
```bash
# Server
docker run -d -p 8888:8888 snake-game server

# Client
docker run -it snake-game client host.docker.internal 8888
```

### Custom Network
```bash
# Create network
docker network create snake-net

# Server
docker run -d --network snake-net --name server snake-game server

# Client
docker run -it --network snake-net snake-game client server 8888
```

## Volume Mounts

### Log Files
```bash
# Mount logs directory
docker run -it -v $(pwd)/logs:/app/logs snake-game game -L /app/logs/game.log
```

### Configuration Files
```bash
# Mount config file
docker run -it -v $(pwd)/snake.cnf:/app/snake.cnf snake-game game -C /app/snake.cnf
```

## Troubleshooting

### Common Issues

#### Curses Display Problems
```bash
# Run with proper terminal settings
docker run -it --env TERM=xterm-256color snake-game game
```

#### Server Connection Issues
```bash
# Check if server is running
docker ps | grep snake-server

# Check server logs
docker logs snake-server

# Test server connectivity
docker exec snake-server netstat -tlnp | grep 8888
```

#### Permission Issues
```bash
# Rebuild with proper permissions
docker build --no-cache -t snake-game .
```

### Debug Mode
```bash
# Run interactive shell
docker run -it snake-game bash

# Inside container:
./snake.py --help
./snake++srv --help
```

## Environment Variables

```bash
# Set terminal type
docker run -it -e TERM=xterm-256color snake-game game

# Set timezone
docker run -it -e TZ=UTC snake-game game
```

## Cleanup

```bash
# Remove containers
docker rm -f snake-server snake-client

# Remove images
docker rmi snake-game

# Clean up everything
docker system prune -a
```

## Development

### Rebuild After Code Changes
```bash
docker build --no-cache -t snake-game .
```

### Live Development
```bash
# Mount source code for live editing
docker run -it -v $(pwd)/snake.py:/app/snake.py snake-game game
```
