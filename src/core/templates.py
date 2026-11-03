import os
import shutil
import time
import sys
import logging

import stat
import subprocess

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import (
    ReadFileTool, 
    WriteFileTool,
    ListDirectoryTool, 
    GlobTool,
    ShellTool,
    EditTool,
    GrepTool,
    ReadManyFilesTool,
    BackendTestTool
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

template_root = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "templates")

TEMPLATES = {
    "root_dir": template_root,
    "templates": [
        {
            "name": "nextjs-nestjs-postresql",
            "install": [
                "npm run install:all"
            ],
            "start": [
                "npm run dev"
            ],
            "description": "A full-stack template using Next.js for the frontend, NestJS for the backend, and PostgreSQL as the database, suitable for building full-stack web applications with a modern, scalable architecture.",
            "common_instruction": """This project template uses Next.js for the frontend, NestJS for the backend, and PostgreSQL as the database.

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

Common Issues and Solutions

- Ensure all services are running on their correct ports. If ports are already in use, find and kill processes bound to them using `ss -tulnp | grep :PORT` and `kill -9 [PID]`
- Verify CORS configuration in `backend/src/main.ts` if frontend cannot connect to backend

IMPORTANT: The PostgreSQL database has been initialized automatically. You **must not** modify the database connection settings, or try to use a different database.""",

            # frontend instruction
            "frontend_instruction": """Frontend (Next.js)

Key directories and files:
- `frontend/src/app`: Create new pages or modify existing ones here. Follow Next.js App Router conventions (e.g., `page.tsx` for pages, `layout.tsx` for layouts).
- `frontend/src/components`: Build reusable UI components in this directory.
- `frontend/src/lib`: Place utilities for interacting with your backend API here.
- Environment Variables: Configure frontend-specific environment variables in `frontend/.env.local`.

Coloring:
- The color of the background and components of ALL the pages must fit the color described in the **user instruction**.
- The color MUST have obvious contrast. For example, a light-colored component must have dark-colored text, and a dark-colored component must have light-colored text. The components and the background color must have similar contrast.
- You should modify the tailwindcss classes and configurations in the codebase.

IMPORTANT: 
- When importing tailwind in files such as `globals.css`, ALWAYS use the new Tailwind import syntax `@import "tailwindcss";` at the start of the file.
- Do NOT use the three lines of old Tailwind import syntax `@tailwind base;`, `@tailwind components;`, and `@tailwind utilities;`. They will cause rendering failures and jumbled pages.
- ALL content about the template or the technologies used MUST be removed from the final website.

You'll primarily work within the `frontend/src`.""",
            # backend instruction
            "backend_instruction": f"""Backend (NestJS)

Project Structure

```
backend/src/
├── app.controller.ts      # Main application controller
├── app.module.ts         # Root application module
├── app.service.ts        # Main application service
└── main.ts              # Application entry point
```

Development Workflow:
1. Creating new module directory (`backend/src/<module-name>`)
2. Generate controller and service (`*.controller.ts`, `*.service.ts`)
3. Create entity (if needed; `*.entity.ts`)

Key directories and files:
- `backend/src/<module-name>`: Create new NestJS modules here for your features, each containing controllers, services, and entities.
- Controllers (`*.controller.ts`): Define your REST API endpoints.
- Services (`*.service.ts`): Implement your business logic.
- Entities (`*.entity.ts`): Define your data models and database schema using TypeORM.
- Database Configuration: Adjust database settings in `backend/src/app.module.ts` or via `backend/.env`.
- DTOs (`dto/*.dto.ts`): Define data transfer objects for validation and type safety.

IMPORTANT: Notice that a global prefix `/api/` has been set in `backend/src/main.ts`, so don't add it again in individual endpoints:
```
app.setGlobalPrefix('api');
```

Route-Order CAUTION:
- Always declare fixed/static routes BEFORE parameterised routes.
  Example:
    @Get('search')   // static, goes first
    search() {{ ... }}
    @Get(':id')      // dynamic, goes after the static route
    findOne() {{ ... }}
- Symptom if you forget: 
  - If you place `:id` first, calling “…/search” throws would try to match the string 'search' to `:id`, which will cause an error.
  - If you encounter a validation error and the type validations all seem correct, this might be the reason.

Database Configuration:

The application uses TypeORM with PostgreSQL. The database is running on port 5432. Configuration is loaded from environment variables in `backend/.env`:

```
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=myappuser
DB_PASSWORD=myapppassword
DB_NAME=myapp
```

IMPORTANT:
- When testing the implemented background endpoints, NEVER start the service in the shell. NEVER use `curl` to send the testing requests.
- ALWAYS use the specialized backend testing tool, `{BackendTestTool.Name}`, to make the tests.
- Continue testing the APIs using `{BackendTestTool.Name}` until ALL the APIs are correctly functioning!
- Every time a new API endpoint has been implemented, install the dependencies using `{ShellTool.Name}`, then call `{BackendTestTool.Name}` to test it.
- ALWAYS add some mock data if the data returned from the testing is empty.
- You should ALWAYS inject some testing data into the database to make sure that the return is not empty!

Note: You can inject test data into the database by running `sudo -u postgres psql -d myapp -c "[SQL_COMMAND]"` with the shell tool `{ShellTool.Name}`.
Examples:
```
# create table
sudo -u postgres psql -d myapp -c 'CREATE TABLE test_table (id SERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL);'
# insert data
sudo -u postgres psql -d myapp -c "INSERT INTO test_table (name) VALUES ('Test Row');"
# view table
sudo -u postgres psql -d myapp -c "SELECT * FROM test_table;"
```

You'll primarily work within the `backend/src`."""
        }
    ]
}

def safe_remove_path(path, max_retries=15, delay=1, force=True):
    """Safely remove a file or directory with retries and optional force flag
    
    Args:
        path: Path to file or directory to remove
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
        force: Use more aggressive methods on final attempt
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Attempting to remove path: {path}")
    
    for attempt in range(max_retries):
        try:
            if not os.path.exists(path):
                logger.info(f"Path does not exist: {path}")
                return True
                
            # On final attempt with force flag, use more aggressive methods
            if force and attempt >= max_retries - 3:  # Start aggressive methods earlier
                logger.info(f"Using force removal for {path} (attempt {attempt + 1})")
                result = _force_remove(path)
                if result:
                    logger.info(f"Force removal successful for {path}")
                    return True
                elif attempt == max_retries - 1:
                    logger.error(f"Force removal failed for {path} after {max_retries} attempts")
                    return False
                    
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
                logger.info(f"Removed file: {path}")
                return True
            elif os.path.isdir(path):
                shutil.rmtree(path)
                logger.info(f"Removed directory: {path}")
                return True
                
        except (OSError, PermissionError, shutil.Error) as e:
            if attempt == max_retries - 1:
                if force:
                    logger.warning(f"Final attempt using force removal for {path}")
                    return _force_remove(path)
                else:
                    logger.error(f"Failed to remove {path} after {max_retries} attempts: {e}")
                    raise
            logger.warning(f"Attempt {attempt + 1} failed for {path}: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    return False

def _force_remove(path):
    """Internal function to forcefully remove files/directories"""
    logger.info(f"Starting force removal for: {path}")
    
    try:
        if not os.path.exists(path):
            logger.info(f"Path does not exist: {path}")
            return True
            
        # Make everything writable first
        if os.path.isdir(path):
            logger.info(f"Making directory contents writable: {path}")
            for root, dirs, files in os.walk(path):
                for item in files + dirs:
                    item_path = os.path.join(root, item)
                    try:
                        os.chmod(item_path, stat.S_IWRITE | stat.S_IREAD)
                    except Exception as e:
                        logger.debug(f"Failed to chmod {item_path}: {e}")
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        else:
            logger.info(f"Making file writable: {path}")
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            
        # Try standard removal again
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
            logger.info(f"Removed file with chmod: {path}")
            return True
        elif os.path.isdir(path):
            shutil.rmtree(path)
            logger.info(f"Removed directory with chmod: {path}")
            return True
            
    except Exception as e:
        logger.warning(f"Standard force removal failed for {path}: {e}")
        
        # Try killing processes that might be using files in the directory
        try:
            _kill_processes_using_path(path)
        except Exception as kill_error:
            logger.warning(f"Failed to kill processes using {path}: {kill_error}")
        
        # Platform-specific fallbacks with more robust options
        try:
            if os.name == 'nt':
                # Use Windows command line for force deletion
                logger.info(f"Using Windows cmd to remove: {path}")
                if os.path.isdir(path):
                    subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path], 
                                 shell=True, check=True, stdout=subprocess.DEVNULL, 
                                 stderr=subprocess.DEVNULL)
                else:
                    subprocess.run(['cmd', '/c', 'del', '/f', '/q', path], 
                                 shell=True, check=True, stdout=subprocess.DEVNULL, 
                                 stderr=subprocess.DEVNULL)
            else:  # Unix-like systems
                # Use rm -rf command with additional flags
                logger.info(f"Using rm command to remove: {path}")
                subprocess.run(['rm', '-rf', '--one-file-system', path], 
                             check=True, stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            logger.info(f"Fallback removal successful for: {path}")
            return True
        except subprocess.CalledProcessError:
            # Try one more time with even more force
            try:
                if os.name != 'nt':
                    logger.info(f"Using rm with additional flags for: {path}")
                    subprocess.run(['rm', '-rf', '--one-file-system', '--preserve-root=no', path], 
                                 check=True, stdout=subprocess.DEVNULL, 
                                 stderr=subprocess.DEVNULL)
                    logger.info(f"Extended rm successful for: {path}")
                    return True
            except Exception as unix_error:
                logger.error(f"Unix force removal failed for {path}: {unix_error}")
        except Exception as fallback_error:
            logger.error(f"Fallback removal also failed for {path}: {fallback_error}")
            
        # Final attempt: move then delete
        try:
            logger.info(f"Trying move-then-delete for: {path}")
            temp_name = path + ".deleting_" + str(int(time.time()))
            os.rename(path, temp_name)
            if os.path.isfile(temp_name) or os.path.islink(temp_name):
                os.remove(temp_name)
            elif os.path.isdir(temp_name):
                shutil.rmtree(temp_name)
            logger.info(f"Move-then-delete successful for: {path}")
            return True
        except Exception as move_error:
            logger.error(f"Move-then-delete also failed for {path}: {move_error}")
            
        return False

def _kill_processes_using_path(path):
    """Kill processes that might be using files in the path"""
    if os.name != 'nt':  # Unix-like systems
        try:
            logger.info(f"Checking for processes using: {path}")
            # Find processes using files in the directory
            result = subprocess.run(['lsof', '+D', path], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                pids = set()
                for line in lines:
                    parts = line.split()
                    if len(parts) > 1:
                        pids.add(parts[1])
                
                # Kill the processes
                for pid in pids:
                    try:
                        logger.info(f"Killing process {pid} using {path}")
                        subprocess.run(['kill', '-9', pid], 
                                     stdout=subprocess.DEVNULL, 
                                     stderr=subprocess.DEVNULL)
                    except Exception as e:
                        logger.warning(f"Failed to kill process {pid}: {e}")
        except Exception as e:
            logger.warning(f"Failed to check/processes using {path}: {e}")

def safe_copy_template(template_source, working_dir, max_retries=5):
    """Safely copy template with error handling"""
    for attempt in range(max_retries):
        try:
            # Clear working directory contents
            if os.path.exists(working_dir):
                for item in os.listdir(working_dir):
                    item_path = os.path.join(working_dir, item)
                    safe_remove_path(item_path)
            
            # Copy template contents
            for item in os.listdir(template_source):
                source_item = os.path.join(template_source, item)
                dest_item = os.path.join(working_dir, item)
                
                if os.path.isfile(source_item):
                    shutil.copy2(source_item, dest_item)
                elif os.path.isdir(source_item):
                    shutil.copytree(source_item, dest_item)
            
            # Run install commands if they exist
            subprocess.run("npm -v", shell=True, check=True, cwd=working_dir)
            subprocess.run("node --version", shell=True, check=True, cwd=working_dir)
            subprocess.run("npm config set registry https://registry.npmmirror.com", shell=True, check=True, cwd=working_dir)
            template_config = _get_template_config(template_source)
            if template_config and "install" in template_config:
                for command in template_config["install"]:
                    try:
                        logger.info(f"Running install command: {command}")
                        subprocess.run(command, shell=True, check=True, cwd=working_dir)
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Install command failed: {e}")
                        raise
            
            return True
                    
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"Copy attempt {attempt + 1} failed: {e}. Retrying...")
            time.sleep(1)
    
    return False


def _get_template_config(template_source):
    """Get template configuration from TEMPLATES dict based on template source"""
    # Extract template name from path (last directory name)
    template_name = os.path.basename(template_source)
    
    # Find matching template in TEMPLATES config
    for template in TEMPLATES.get("templates", []):
        if template.get("name") == template_name:
            return template
    
    logger.warning(f"No template config found for {template_name}")
    return None


if __name__ == "__main__":
    safe_remove_path("/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root/test_project17")