# Mellea Playground

> **Note:** This project is in active development. Features and APIs may change.

A centralized GUI playground for cataloging, running, and composing [mellea](https://github.com/ibm-granite/mellea) programs across multiple LLMs.

**Compatibility:** mellea >= 0.3.0 | Python >= 3.11

## What is this?

Mellea Playground provides a web interface for:

- **Cataloging** programs, models, and compositions with searchable metadata
- **Running** Python programs with `@generative` slots in isolated container environments
- **Composing** visual workflows that chain programs and models together
- **Collaborating** by sharing assets with other users

It's designed for builders who want to experiment with multi-model orchestration without managing infrastructure manually.

## Quick Start

```bash
# Create cluster, build images, and deploy everything
make spin-up-from-scratch
```

Once running, access the application at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8080

## Development

See [AGENTS.md](./AGENTS.md) for contributor guidelines, including multi-agent collaboration practices and git workflow.

## License

Apache 2.0 - see [LICENSE](./LICENSE) for details.
