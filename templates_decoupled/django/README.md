This is the backend portion of the fullstack template, built with Django, a high-level Python web framework that encourages rapid development and clean, pragmatic design.

Set up the database (ensure PostgreSQL is running):
   ```bash
   python manage.py migrate
   ```

Start the development server:
   ```bash
   python manage.py runserver 3001
   ```

Alternative start command using the package.json script:
   ```bash
   npm run dev
   ```

Project Structure

```
app/
├── admin.py              # Django admin configuration
├── models.py             # Database models
├── serializers.py        # Data serialization/deserialization
├── views.py              # API view logic
├── urls.py               # URL routing for the app
└── migrations/          # Database migration files
config/
├── __init__.py          # Package initialization
├── settings.py          # Django settings configuration
├── urls.py              # Main URL routing
└── wsgi.py              # WSGI application entry point
manage.py               # Django command-line utility
requirements.txt        # Python dependencies
.env                   # Environment variables
```

Development Workflow

Creating New Models:

1. Create a new model in `app/models.py`:
2. Create and apply migrations:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```
3. Register the model in `app/admin.py`:

Database Configuration:

The application uses Django ORM with PostgreSQL. Configuration is loaded from environment variables in `.env`:

```bash
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=myappuser
DB_PASSWORD=myapppassword
DB_NAME=myapp
```

### API Documentation

The API follows RESTful principles with endpoints available at `/api/` when running the application.

Available endpoints:
- `/api/` - API root
- `/api/users/` - User management
- `/health/` - Health check endpoint
- `/admin/` - Django admin interface