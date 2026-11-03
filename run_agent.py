# run_agent.py
import sys
from dotenv import load_dotenv
load_dotenv()

from pipeline import Sandbox
import agent

TASK = sys.argv[1] if len(sys.argv) > 1 else (
    "Which customer has the highest total value of paid orders?"
)

sb = Sandbox.from_file("pipeline/sandbox.yaml")
with sb.run() as env:
    print("sandbox up:", env)
    agent.main(TASK)