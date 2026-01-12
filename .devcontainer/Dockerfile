# Claude Code Sandbox Container
# Based on the official Anthropic devcontainer setup
FROM node:20-bookworm

ARG TZ=UTC
ARG CLAUDE_CODE_VERSION=latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    vim \
    nano \
    sudo \
    iptables \
    ipset \
    dnsutils \
    net-tools \
    iproute2 \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python (for projects that need it)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with sudo access
RUN echo "node ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Set up command history persistence
RUN mkdir -p /commandhistory && chown node:node /commandhistory

# Create workspace and claude config directories
RUN mkdir -p /workspace /home/node/.claude \
    && chown -R node:node /workspace /home/node/.claude

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Copy firewall initialization script
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /usr/local/bin/init-firewall.sh

# Set environment variables
ENV TZ=${TZ}
ENV EDITOR=nano
ENV HISTFILE=/commandhistory/.bash_history

# Switch to non-root user
USER node
WORKDIR /workspace

# Default command
CMD ["bash"]
