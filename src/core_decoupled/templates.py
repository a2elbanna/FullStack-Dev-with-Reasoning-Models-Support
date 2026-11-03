import os
import shutil
import time
import sys
import logging

import stat
import subprocess

import json
from pathlib import Path
import yaml   # pip install PyYAML

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

template_root = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "templates_decoupled")

TEMPLATES = {
    "root_dir": template_root,
    "common_instruction": """This project template uses {frontend_name} for the frontend, {backend_name} for the backend, and PostgreSQL as the database.

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
- Verify CORS configuration in the backend code if frontend cannot connect to backend

""" + f"""IMPORTANT: The PostgreSQL database has been initialized automatically. The application uses TypeORM with PostgreSQL. The database is running on port 5432. Configuration is loaded from environment variables in `backend/.env`:

```
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=myappuser
DB_PASSWORD=myapppassword
DB_NAME=myapp
```

You **must not** modify the database connection settings, or try to use a different database. You can inject test data into the database by running `sudo -u postgres psql -d myapp -c "[SQL_COMMAND]"` with the shell tool `{ShellTool.Name}`.
Examples:
```
# create table
sudo -u postgres psql -d myapp -c 'CREATE TABLE test_table (id SERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL);'
# insert data
sudo -u postgres psql -d myapp -c "INSERT INTO test_table (name) VALUES ('Test Row');"
# view table
sudo -u postgres psql -d myapp -c "SELECT * FROM test_table;"
```""",

    # frontend instruction
    "frontend_instruction": """Frontend ({name})

Key directories and files:
{key_directories_and_files}

Coloring:
{coloring}

IMPORTANT: 
{important}

You'll primarily work within the `frontend/`.""",

    # backend instruction
    "backend_instruction": """Backend ({name})

Development Workflow:
{development_workflow}

Key directories and files:
{key_directories_and_files}

IMPORTANT:
{important}

You'll primarily work within the `backend/`.""",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: str) -> dict:
    """
    Read `path` and return the loaded YAML as a Python object.
    Uses `yaml.safe_load` to avoid executing arbitrary tags.
    """
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


TEMPLATES["template_descriptions"] = load_json(os.path.join(template_root, "config/template_info.json"))


def build_chosen_template(chosen_template_name):
    try:
        frontend_name, backend_name = chosen_template_name.split("__")
    except:
        frontend_name, backend_name = "", ""
    if frontend_name not in TEMPLATES["template_descriptions"]["frontend_templates"]:
        frontend_name = list(TEMPLATES["template_descriptions"]["frontend_templates"].keys())[0]
    if backend_name not in TEMPLATES["template_descriptions"]["backend_templates"]:
        backend_name = list(TEMPLATES["template_descriptions"]["backend_templates"].keys())[0]
    frontend_template_path = os.path.join(template_root, f"config/{frontend_name}.yml")
    backend_template_path = os.path.join(template_root, f"config/{backend_name}.yml")
    frontend_config = load_yaml(frontend_template_path)
    backend_config = load_yaml(backend_template_path)
    chosen_template = {
        "name": f"{frontend_name}__{backend_name}",
        "install": [
                "npm run install:all"
        ],
        "start": [
            "npm run dev"
        ],
        "common_instruction": TEMPLATES["common_instruction"].format(
            frontend_name=frontend_name,
            backend_name=backend_name
        ),
        "frontend_instruction": TEMPLATES["frontend_instruction"].format(
            name=frontend_config["name"],
            key_directories_and_files=frontend_config["key_directories_and_files"],
            coloring=frontend_config["coloring"],
            important=frontend_config.get("important", "No additional important notes.")
        ),
        "backend_instruction": TEMPLATES["backend_instruction"].format(
            name=backend_config["name"],
            development_workflow=backend_config["development_workflow"],
            key_directories_and_files=backend_config["key_directories_and_files"],
            important=backend_config.get("important", "No additional important notes.")
        ),
    }
    chosen_template_name = f"{frontend_name}__{backend_name}"
    return chosen_template, chosen_template_name


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


def copy_contents(src, dst):
    """Copy contents from src to dst"""
    if not os.path.exists(dst):
        os.makedirs(dst)
    
    for item in os.listdir(src):
        source_item = os.path.join(src, item)
        dest_item = os.path.join(dst, item)
        
        if os.path.isfile(source_item):
            shutil.copy2(source_item, dest_item)
        elif os.path.isdir(source_item):
            shutil.copytree(source_item, dest_item)


def safe_copy_template(template_source_frontend, template_source_backend, common_files_dir, chosen_template, working_dir, max_retries=5):
    """Safely copy template with error handling"""
    for attempt in range(max_retries):
        try:
            # Clear working directory contents
            if os.path.exists(working_dir):
                for item in os.listdir(working_dir):
                    item_path = os.path.join(working_dir, item)
                    safe_remove_path(item_path)
            
            # Copy template contents
            copy_contents(template_source_frontend, os.path.join(working_dir, "frontend"))
            copy_contents(template_source_backend, os.path.join(working_dir, "backend"))
            copy_contents(common_files_dir, working_dir)
            
            # Run install commands if they exist
            subprocess.run("npm -v", shell=True, check=True, cwd=working_dir)
            subprocess.run("node --version", shell=True, check=True, cwd=working_dir)
            subprocess.run("npm config set registry https://registry.npmmirror.com", shell=True, check=True, cwd=working_dir)
            
            
            for command in chosen_template["install"]:
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


if __name__ == "__main__":
    safe_remove_path("/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root/test_project17")