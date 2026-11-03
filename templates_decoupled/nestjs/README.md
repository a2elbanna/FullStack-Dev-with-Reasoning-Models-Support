This is the backend portion of the fullstack template, built with NestJS, a progressive Node.js framework for building efficient and scalable server-side applications.

Project Structure

```
src/
├── app.controller.ts      # Main application controller
├── app.module.ts         # Root application module
├── app.service.ts        # Main application service
└── main.ts              # Application entry point
```

Development Workflow

Creating New Modules:

1. Generate a new module:
   ```bash
   nest generate module <module-name>
   ```

2. Generate controller and service:
   ```bash
   nest generate controller <module-name>
   nest generate service <module-name>
   ```

3. Create entity (if needed):
   ```bash
   nest generate class <module-name>/<entity-name> --no-spec
   ```

Database Configuration:

The application uses TypeORM with PostgreSQL. Configuration is loaded from environment variables in `.env`:

```bash
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=myappuser
DB_PASSWORD=myapppassword
DB_NAME=myapp
```

### API Documentation

Swagger API documentation is available at `/api` when running the application.
