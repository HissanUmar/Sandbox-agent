# run_agent.py
import sys
from sandbox import Sandbox
from dotenv import load_dotenv
load_dotenv()

TASK = sys.argv[1] if len(sys.argv) > 1 else (
    "Find all pending orders. Get each customer and charge them the order total. "
    "Then get shipping rates and create a shipment with the cheapest carrier."
)

sb = Sandbox.from_file("sandbox.yaml")
with sb.run() as env:
    print("sandbox up:", env)
    import agent
    agent.main(TASK)