# Vue Frontend Template

This is a Vue.js frontend template created with [create-vue](https://github.com/vuejs/create-vue), featuring a full development setup out of the box.

## Features

- ⚡ [Vue 3](https://v3.vuejs.org/) with [Vite](https://vitejs.dev/)
- 🦾 [TypeScript](https://www.typescriptlang.org/)
- 🔥 [Vue Router](https://router.vuejs.org/)
- .Pinia](https://pinia.vuejs.org/)
- ✅ [Vitest](https://vitest.dev/) for unit testing
- 🧪 [Cypress](https://www.cypress.io/) for E2E testing
- 📑 [ESLint](https://eslint.org/) for code linting
- ✨ [Prettier](https://prettier.io/) for code formatting
- 🛠️ [JSDOM](https://github.com/jsdom/jsdom) for browser environment simulation in tests
- 🔄 Proxy configured to forward API requests to backend at http://localhost:3001

## Quick Setup

```bash
# Install dependencies
npm install

# Start development server (runs on port 3000 by default)
npm run dev

# Build for production
npm run build

# Run unit tests
npm run test:unit

# Run E2E tests
npm run test:e2e

# Lint and format code
npm run lint
npm run format

# Type checking
npm run type-check
```

## Backend Integration

This frontend is configured to proxy API requests to a backend server running at `http://localhost:3001`. All requests to `/api/*` will be forwarded to the backend.

Example API call from your Vue components:
```javascript
// This request will be proxied to http://localhost:3001/api/users
const response = await fetch('/api/users');
const data = await response.json();
```

During production, you would typically update the `VITE_API_BASE_URL` in the `.env` file to point to your actual backend API endpoint.

## Project Structure

```
├── public/              # Static assets
├── src/                 # Source files
│   ├── assets/          # Assets like images, fonts, etc.
│   ├── components/      # Reusable Vue components
│   ├── router/          # Vue Router configuration
│   ├── stores/          # Pinia stores
│   ├── views/           # Page components
│   ├── App.vue          # Main app component
│   └── main.ts          # Entry point
├── cypress/             # Cypress E2E tests
├── .vscode/             # VSCode settings
├── vite.config.ts       # Vite configuration
├── tsconfig.json        # TypeScript configuration
└── package.json         # Dependencies and scripts
```

## Development

### Recommended IDE Setup

- [VS Code](https://code.visualstudio.com/) with [Vue Language Features (Volar)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) extension

### Browser Support

This template uses modern JavaScript features and requires a browser that supports ES modules. For older browser support, additional configuration is needed.

## Environment Variables

Environment variables can be added to `.env` files. The project automatically loads `.env`, `.env.local`, `.env.*.local` files (in that order) for the current NODE_ENV.

## Deployment

To deploy this application, run `npm run build` and serve the `dist` folder using a static file server.