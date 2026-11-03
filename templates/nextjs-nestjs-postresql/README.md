This project template uses Next.js for the frontend, NestJS for the backend, and PostgreSQL as the database, making it suitable for building full-stack web applications with a modern, scalable architecture.

Quick Start

1. Install dependencies:
   ```bash
   npm run install:all
   ```

2. Start services:
   ```bash
   # Start frontend and backend
   npm run dev
   ```

3. Access the applications:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:3001
   - API Documentation: http://localhost:3001/api (when enabled)

Project Structure

```
.
├── backend/                 # NestJS backend
│   ├── src/
│   │   ├── app.controller.ts
│   │   ├── app.module.ts
│   │   ├── app.service.ts
│   │   └── main.ts
│   └── ...
├── frontend/                # Next.js frontend
│   ├── src/
│   │   ├── app/             # App Router pages
│   │   ├── components/      # Reusable UI components
│   │   └── lib/             # Utility functions
│   └── ...
└── ...
```

Frontend (Next.js)

Key directories and files:
- `frontend/src/app`: Create new pages or modify existing ones here. Follow Next.js App Router conventions (e.g., `page.tsx` for pages, `layout.tsx` for layouts).
- `frontend/src/components`: Build reusable UI components in this directory.
- `frontend/src/lib`: Place utilities for interacting with your backend API here.
- Styling: The project uses Tailwind CSS with the new `@import "tailwindcss"` syntax.
- Environment Variables: Configure frontend-specific environment variables in `frontend/.env.local`.

Frontend Components
The template includes a set of professionally designed components. You MUST modify these components based on the user instruction:
- Header with responsive navigation
- Hero section with call-to-action
- Features section with icon cards
- Footer with social links
- Responsive design for all screen sizes
IMPORTANT: Make these components match the content, theme and coloring of the website!

Backend (NestJS)

Key directories and files:
- `backend/src/<module-name>`: Create new NestJS modules here for your features, each containing controllers, services, and entities.
- Controllers (`*.controller.ts`): Define your REST API endpoints.
- Services (`*.service.ts`): Implement your business logic.
- Entities (`*.entity.ts`): Define your data models and database schema using TypeORM.
- Database Configuration: Adjust database settings in `backend/src/app.module.ts` or via `backend/.env`.
- DTOs (`dto/*.dto.ts`): Define data transfer objects for validation and type safety.

Database (PostgreSQL)

The database is running on port 5432, with the following configuration:
```bash
DB_HOST=postgres
DB_PORT=5432
DB_USERNAME=myappuser
DB_PASSWORD=myapppassword
DB_NAME=myapp
```

Connection settings are in `backend/.env`.

Environment Configuration

- Backend: Configure values in `backend/.env`
- Frontend: Configure values in `frontend/.env.local`

Common Issues and Solutions

- Ensure all services are running on their correct ports. If ports are already in use, find and kill processes bound to them using `ss -tulnp | grep :PORT` and `kill -9 [PID]`
- Verify CORS configuration in `backend/src/main.ts` if frontend cannot connect to backend

In summary, you'll primarily work within the `frontend/src` and `backend/src` directories to build your application's features.