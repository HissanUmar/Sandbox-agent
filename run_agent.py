# run_agent.py
import argparse
import importlib

from dotenv import load_dotenv
load_dotenv()

from pipeline import Sandbox
import agent


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task", nargs="?", default="Cancel order 101, then list pending orders.")
    parser.add_argument("--env", default="shop", choices=["shop", "hospital"])
    args = parser.parse_args()

    env_dir = f"environments/{args.env}"
    sb = Sandbox.from_file(f"{env_dir}/sandbox.yaml")

    with sb.run() as env:
        print("sandbox up:", env)

        # 1. configure the per-environment runtime (populates _ENV)
        runtime_mod = importlib.import_module(f"environments.{args.env}._runtime")
        runtime_mod.configure(env)

        # 2. load the environment's tools (their api_url() calls now work)
        tools_mod = importlib.import_module(f"environments.{args.env}.tools")

        # 3. load the environment's prompt
        with open(f"{env_dir}/prompt.md") as f:
            env_prompt = f.read()


        # 4. run the agent with this environment's tools and prompt
        agent.main(args.task, tools_mod.TOOLS, env_prompt)