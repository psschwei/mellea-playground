#!/bin/bash
# Firewall initialization script for Claude Code sandbox
# Implements default-deny policy with allowlist for essential services

set -e

echo "Initializing firewall rules..."

# Create ipset for allowed domains
sudo ipset create allowed-domains hash:ip -exist
sudo ipset flush allowed-domains

# Function to resolve and add domain IPs to allowlist
add_domain() {
    local domain=$1
    echo "Adding $domain..."
    for ip in $(dig +short "$domain" 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'); do
        sudo ipset add allowed-domains "$ip" -exist
    done
}

# Add GitHub IPs (from their meta API)
echo "Fetching GitHub IP ranges..."
curl -s https://api.github.com/meta 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?' | while read -r cidr; do
    # For CIDR ranges, just add the base IP (ipset hash:ip doesn't support CIDR)
    ip=$(echo "$cidr" | cut -d'/' -f1)
    sudo ipset add allowed-domains "$ip" -exist 2>/dev/null || true
done

# Essential domains for Claude Code operation
ALLOWED_DOMAINS=(
    # Anthropic services
    "api.anthropic.com"
    "api.claude.ai"
    "claude.ai"
    "statsig.anthropic.com"
    "sentry.io"

    # Custom LLM endpoint
    "ete-litellm.ai-models.vpc-int.res.ibm.com"

    # Package registries
    "registry.npmjs.org"
    "pypi.org"
    "files.pythonhosted.org"

    # GitHub
    "github.com"
    "api.github.com"
    "raw.githubusercontent.com"
    "objects.githubusercontent.com"
    "codeload.github.com"

    # VS Code (if using devcontainer)
    "update.code.visualstudio.com"
    "marketplace.visualstudio.com"
    "vscode.blob.core.windows.net"
)

for domain in "${ALLOWED_DOMAINS[@]}"; do
    add_domain "$domain"
done

# Get host network for Docker connectivity
HOST_NETWORK=$(ip route | grep default | awk '{print $3}' | head -1)
if [ -n "$HOST_NETWORK" ]; then
    # Allow Docker network
    DOCKER_SUBNET=$(ip route | grep -v default | head -1 | awk '{print $1}')
fi

# Flush existing rules
sudo iptables -F
sudo iptables -X 2>/dev/null || true

# Default policies: DROP everything
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT DROP

# Allow loopback
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A OUTPUT -o lo -j ACCEPT

# Allow established connections
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow DNS (required for domain resolution)
sudo iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow traffic to allowed domains
sudo iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Allow Docker network if detected
if [ -n "$DOCKER_SUBNET" ]; then
    sudo iptables -A INPUT -s "$DOCKER_SUBNET" -j ACCEPT
    sudo iptables -A OUTPUT -d "$DOCKER_SUBNET" -j ACCEPT
fi

# Reject everything else with feedback
sudo iptables -A INPUT -j REJECT --reject-with icmp-port-unreachable
sudo iptables -A OUTPUT -j REJECT --reject-with icmp-port-unreachable

echo "Firewall initialized. Testing connectivity..."

# Verify blocked
if curl -s --connect-timeout 2 https://example.com >/dev/null 2>&1; then
    echo "WARNING: example.com is reachable (should be blocked)"
else
    echo "OK: Unrestricted sites blocked"
fi

# Verify allowed
if curl -s --connect-timeout 5 https://api.github.com >/dev/null 2>&1; then
    echo "OK: GitHub API reachable"
else
    echo "WARNING: GitHub API not reachable"
fi

echo "Firewall setup complete."
