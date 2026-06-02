import argparse
import asyncio
import json
import os
import resource
import subprocess
import sys
import time

import websockets

from scripts.multi_core_benchmark_monitor import MultiMonitoring

BASE_PORT = 8001
HOST = "127.0.0.1"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.abspath(BASE_DIR)
if os.path.exists(os.path.join(PROJECT_DIR, "main.py")):
    APP_PATH = PROJECT_DIR
else:
    APP_PATH = os.path.join(PROJECT_DIR, "application")


def _raise_fd_limit() -> None:
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        print(f"Current FD limits: soft={soft}, hard={hard}")
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        print(f"Updated FD limits: soft={hard}, hard={hard}")
    except Exception as exc:
        print(f"Failed to update FD limits: {exc}")


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers", type=int, default=16, help="Workers per instance"
    )
    parser.add_argument(
        "--instances", type=int, default=1, help="Server instances to launch"
    )
    parser.add_argument("--clients", type=int, default=50, help="Clients per worker")
    parser.add_argument("--cycles", type=int, default=30)
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=None,
        help="Run guest nav load for a fixed duration instead of a fixed number of cycles",
    )
    parser.add_argument(
        "--exe", type=str, default=None, help="Path to compiled executable"
    )
    parser.add_argument(
        "--path",
        default="/auth/",
        help="Guest auth path to open repeatedly.",
    )
    parser.add_argument(
        "--think-time-ms",
        type=int,
        default=0,
        help="Optional client think time between nav requests.",
    )
    return parser.parse_args()


async def wait_for_server(port, timeout=30):
    url = f"ws://{HOST}:{port}/ws"
    start = time.time()
    while time.time() - start < timeout:
        try:
            async with websockets.connect(url) as ws:
                await ws.recv()
                return True
        except Exception:
            await asyncio.sleep(0.5)
    return False


async def client_worker(
    worker_id,
    port,
    cycles,
    results,
    *,
    path,
    think_time_ms,
    max_messages=20,
    deadline=None,
):
    url = f"ws://{HOST}:{port}/ws"
    try:
        async with websockets.connect(url) as ws:
            await ws.recv()

            i = 0
            while True:
                if deadline is not None:
                    if time.perf_counter() >= deadline:
                        break
                elif i >= cycles:
                    break

                start = time.perf_counter()
                nav_req = {
                    "type": "userAction",
                    "userAction": {
                        "name": "nav",
                        "context": {"path": path},
                    },
                    "request_id": f"auth_nav_{worker_id}_{i}",
                }
                await ws.send(json.dumps(nav_req))

                success = False
                for _ in range(max_messages):
                    resp = await ws.recv()
                    if "beginRendering" in resp:
                        success = True
                        break

                if success:
                    results["total_requests"] += 1
                    results["latencies"].append(time.perf_counter() - start)
                else:
                    results["errors"] += 1
                    with open("benchmark_errors.log", "a", encoding="utf-8") as f:
                        f.write(
                            f"Worker {worker_id} (Port {port}): beginRendering not found in {max_messages} messages for path {path}\n"
                        )

                i += 1
                if think_time_ms > 0:
                    await asyncio.sleep(think_time_ms / 1000.0)

    except Exception as e:
        results["errors"] += 1
        with open("benchmark_errors.log", "a", encoding="utf-8") as f:
            f.write(f"Worker {worker_id} (Port {port}) EXCEPTION: {e}\n")


async def main(
    *,
    workers_per_instance,
    num_instances,
    clients_per_worker,
    cycles,
    duration_seconds,
    exe_path,
    path,
    think_time_ms,
):
    total_workers = max(1, workers_per_instance) * max(1, num_instances)
    total_clients = total_workers * clients_per_worker
    print("--- Guest Auth Page Benchmark ---")
    print(
        f"instances={num_instances} workers/instance={workers_per_instance} "
        f"clients/worker={clients_per_worker} cycles={cycles} think_time_ms={think_time_ms}"
    )
    print(f"path={path}")

    if os.path.exists("benchmark_errors.log"):
        os.remove("benchmark_errors.log")

    env = os.environ.copy()
    env["PYTHONPATH"] = APP_PATH + os.pathsep + env.get("PYTHONPATH", "")

    server_procs = []
    ports = [BASE_PORT + i for i in range(max(1, num_instances))]
    clients_per_instance = workers_per_instance * clients_per_worker
    target_ports = []
    for port in ports:
        target_ports.extend([port] * clients_per_instance)

    print(
        f"Starting {num_instances} instance(s) with {workers_per_instance} worker(s) each..."
    )
    for i, port in enumerate(ports):
        if exe_path:
            cmd = [
                exe_path,
                "--mode",
                "server",
                "--http",
                "--port",
                str(port),
                "--workers",
                str(workers_per_instance),
            ]
        else:
            cmd = [
                sys.executable,
                os.path.join(APP_PATH, "main.py"),
                "--mode",
                "server",
                "--http",
                "--port",
                str(port),
                "--workers",
                str(workers_per_instance),
            ]

        if i == 0:
            print(
                f"  -> Starting instance {i} on port {port} with {workers_per_instance} worker(s) (LOGGING to server_worker_0.log)..."
            )
            log_f = open("server_worker_0.log", "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT
            )
        else:
            print(
                f"  -> Starting instance {i} on port {port} with {workers_per_instance} worker(s)..."
            )
            proc = subprocess.Popen(
                cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        server_procs.append(proc)
        await asyncio.sleep(1.5)

    try:
        print("Waiting for all instances to be up (this may take a while)...")
        for port in ports:
            if await wait_for_server(port, timeout=120):
                print(f"     Instance on port {port} is UP.")
            else:
                print(f"     Instance on port {port} TIMEOUT.")

        monitor = MultiMonitoring([p.pid for p in server_procs])
        monitor_task = asyncio.create_task(monitor.poll())

        results = {"total_requests": 0, "latencies": [], "errors": 0}
        start_time = time.perf_counter()
        deadline = (
            start_time + float(duration_seconds)
            if duration_seconds is not None and duration_seconds > 0
            else None
        )

        all_clients = []
        for i in range(total_clients):
            all_clients.append(
                client_worker(
                    i,
                    target_ports[i],
                    cycles,
                    results,
                    path=path,
                    think_time_ms=think_time_ms,
                    deadline=deadline,
                )
            )

        await asyncio.gather(*all_clients)

        end_time = time.perf_counter()
        total_duration = end_time - start_time

        monitor.stop()
        await monitor_task

        print("\n--- Results ---")
        print(f"Total Duration: {total_duration:.2f}s")
        print(f"Total Requests: {results['total_requests']}")
        print(f"Errors: {results['errors']}")
        print(f"Throughput: {results['total_requests'] / total_duration:.2f} req/s")

        if results["latencies"]:
            avg_latency = (sum(results["latencies"]) / len(results["latencies"])) * 1000
            p95_idx = max(0, int(len(results["latencies"]) * 0.95) - 1)
            p95 = sorted(results["latencies"])[p95_idx] * 1000
            print(f"Avg Latency: {avg_latency:.2f}ms")
            print(f"95th Percentile: {p95:.2f}ms")

        print("\n--- Resource Usage (AGGREGATE) ---")
        print(
            "RSS overstates standalone bundles because it double-counts shared pages."
        )
        print(monitor.report())

    finally:
        print("Shutting down servers...")
        for p in server_procs:
            p.terminate()
        for p in server_procs:
            p.wait()


def run() -> None:
    _raise_fd_limit()
    args = _parse_args()
    asyncio.run(
        main(
            workers_per_instance=args.workers,
            num_instances=args.instances,
            clients_per_worker=args.clients,
            cycles=args.cycles,
            duration_seconds=args.duration_seconds,
            exe_path=args.exe,
            path=args.path,
            think_time_ms=args.think_time_ms,
        )
    )


if __name__ == "__main__":
    run()
