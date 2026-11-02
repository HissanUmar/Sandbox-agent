# sandbox.py
import os, sqlite3, tempfile, shutil, uuid, contextlib
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn, threading, socket, time

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close(); return port

class Sandbox:
    def __init__(self, config):
        self.config = config

    @classmethod
    def from_file(cls, path):
        with open(path) as f:
            return cls(yaml.safe_load(f))

    @contextlib.contextmanager
    def run(self):
        run_dir = tempfile.mkdtemp(prefix="sandbox-")
        servers = []
        env = {}
        try:
            for name, dbcfg in (self.config.get("databases") or {}).items():
                db_path = os.path.join(run_dir, f"{name}.db")
                conn = sqlite3.connect(db_path)
                for tbl, t in dbcfg["tables"].items():
                    cols = ", ".join(f"{c} {typ}" for c, typ in t["columns"].items())
                    conn.execute(f"CREATE TABLE {tbl} ({cols})")
                    for row in t.get("seed", []):
                        placeholders = ", ".join("?" * len(row))
                        conn.execute(f"INSERT INTO {tbl} VALUES ({placeholders})", list(row.values()))
                conn.commit(); conn.close()
                env[f"SB_DB_{name.upper()}"] = f"sqlite:///{db_path}"

            for name, apicfg in (self.config.get("apis") or {}).items():
                port = _free_port()
                app = self._build_app(apicfg)
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
                th = threading.Thread(target=server.run, daemon=True); th.start()
                while not server.started: time.sleep(0.02)
                servers.append(server)
                env[f"SB_API_{name.upper()}"] = f"http://127.0.0.1:{port}"

            os.environ.update(env)
            yield env
        finally:
            for s in servers: s.should_exit = True
            shutil.rmtree(run_dir, ignore_errors=True)

    def _build_app(self, apicfg):
        app = FastAPI()
        for ep in apicfg["endpoints"]:
            path = ep["path"]
            method = ep["method"].upper()
            async def handler(request: Request, _ep=ep):
                body = await request.json() if await request.body() else {}
                params = {**request.path_params, **body}
                out = _substitute(_ep["response"]["body"], params)
                return JSONResponse(out, status_code=_ep["response"]["status"])
            app.add_api_route(path.replace("{charge_id}", "{charge_id}").replace("{order_id}", "{order_id}"),
                              handler, methods=[method])
        return app

def _substitute(obj, params):
    if isinstance(obj, str) and obj.startswith("{") and obj.endswith("}"):
        return params.get(obj[1:-1], obj)
    if isinstance(obj, dict):
        return {k: _substitute(v, params) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, params) for v in obj]
    return obj