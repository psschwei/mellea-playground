# Mellea Playground

> **Note:** This project is in active development. Features and APIs may change.

A web-based GUI for cataloging, running, and composing [mellea](https://github.com/ibm-granite/mellea) programs across multiple LLMs.

## What is this?

Mellea Playground provides a browser interface for:

- **Cataloging** programs, models, and compositions with searchable metadata
- **Composing** visual workflows that chain programs and models together via a drag-and-drop canvas
- **Running** compositions and viewing execution logs
- **Collaborating** by sharing assets with other users

It's designed for builders who want to experiment with multi-model orchestration without managing infrastructure manually.

## Tech Stack

- **Framework**: React 18 + TypeScript
- **UI**: Chakra UI
- **Visual Builder**: React Flow + Dagre (auto-layout)
- **State**: Zustand (builder) + React Context (auth)
- **Build**: Vite

The API layer uses an in-memory mock store — no backend is required to run locally.

## Development

```bash
cd frontend
npm install
npm run dev
```

The app will be available at http://localhost:5173.

Other useful commands:

```bash
npm run build       # Production build
npm run lint        # Run ESLint
npm run type-check  # TypeScript type checking
npm test            # Run tests
```

## Deployment

A `Dockerfile` and `nginx.conf` are included in `frontend/` for building a production container image.

## Contributing

See [AGENTS.md](./AGENTS.md) for contributor guidelines, including multi-agent collaboration practices and git workflow.

## License

Apache 2.0 - see [LICENSE](./LICENSE) for details.
