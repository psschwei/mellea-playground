# Mellea Frontend Dockerfile
# Multi-stage build for optimized production image

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage - use unprivileged nginx for OpenShift compatibility
FROM nginxinc/nginx-unprivileged:alpine

# Copy custom nginx config (as root-owned, but readable by nginx user)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose unprivileged port (>1024 for non-root)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:8080/health || exit 1

# Start nginx (runs as non-root user 101)
CMD ["nginx", "-g", "daemon off;"]
