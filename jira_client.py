from scripts.integrations.jira_client import *  # noqa: F401,F403
from runpy import run_path
from pathlib import Path

if __name__ == "__main__":
    run_path(str(Path(__file__).parent / "scripts/integrations/jira_client.py"), run_name="__main__")
