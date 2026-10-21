"""Internal detached worker; the public interfaces return its recorded job ID."""
import sys
from pathlib import Path
from .jobs import run_worker

if __name__=='__main__':run_worker(Path(sys.argv[1]),sys.argv[2])
