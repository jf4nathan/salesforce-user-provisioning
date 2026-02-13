from runpy import run_path
from pathlib import Path

if __name__ == "__main__":
    run_path(str(Path(__file__).parent / "scripts/integrations/create_jira_ticket.py"), run_name="__main__")
