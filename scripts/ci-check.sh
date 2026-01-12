#!/bin/bash
# Run all CI checks locally before pushing
# Usage: ./scripts/ci-check.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Running CI Checks ===${NC}"
echo

# Backend checks
echo -e "${YELLOW}[1/5] Backend: ruff lint${NC}"
ruff check backend/
echo -e "${GREEN}✓ ruff passed${NC}"
echo

echo -e "${YELLOW}[2/5] Backend: mypy type check${NC}"
mypy backend/ --ignore-missing-imports
echo -e "${GREEN}✓ mypy passed${NC}"
echo

echo -e "${YELLOW}[3/5] Backend: pytest${NC}"
pytest backend/tests/ -v --tb=short
echo -e "${GREEN}✓ pytest passed${NC}"
echo

# Frontend checks
echo -e "${YELLOW}[4/5] Frontend: eslint${NC}"
cd frontend && npm run lint
echo -e "${GREEN}✓ eslint passed${NC}"
echo

echo -e "${YELLOW}[5/5] Frontend: tsc type check${NC}"
npm run type-check
echo -e "${GREEN}✓ tsc passed${NC}"
cd ..
echo

echo -e "${GREEN}=== All CI checks passed! ===${NC}"
