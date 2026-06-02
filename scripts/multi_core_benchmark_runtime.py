import asyncio
import json
import os
import subprocess
import sys
import time

import websockets

from scripts.multi_core_benchmark_monitor import MultiMonitoring
from scripts.multi_core_benchmark_profiles import PROFILE_PRESETS, summarize_profile_log
from scripts._golive_common import terminate_processes

BASE_PORT = 8001
HOST = "127.0.0.1"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.abspath(BASE_DIR)
if os.path.exists(os.path.join(PROJECT_DIR, "main.py")):
    APP_PATH = PROJECT_DIR
else:
    APP_PATH = os.path.join(PROJECT_DIR, "application")


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


def _remaining_time(deadline):
    if deadline is None:
        return None
    return deadline - time.perf_counter()


def _request_recv_deadline(
    deadline, request_timeout_seconds, drain_timeout_seconds=2.0
):
    if deadline is None:
        return time.perf_counter() + max(0.1, float(request_timeout_seconds))
    return deadline + max(0.0, float(drain_timeout_seconds))


async def _recv_until_deadline(ws, deadline):
    remaining = _remaining_time(deadline)
    if remaining is not None and remaining <= 0:
        raise asyncio.TimeoutError
    if remaining is None:
        return await ws.recv()
    return await asyncio.wait_for(ws.recv(), timeout=remaining)


async def _drain_initial_render(ws, deadline, idle_seconds=0.25):
    seen_render = False
    while True:
        if seen_render:
            idle_deadline = min(deadline, time.perf_counter() + float(idle_seconds))
        else:
            idle_deadline = deadline
        try:
            resp = await _recv_until_deadline(ws, idle_deadline)
        except asyncio.TimeoutError:
            return
        if "beginRendering" in resp:
            seen_render = True


async def client_worker(
    worker_id,
    port,
    cycles,
    results,
    *,
    nav_paths,
    think_time_ms,
    max_messages,
    request_timeout_seconds,
    deadline=None,
    drain_timeout_seconds=2.0,
):
    url = f"ws://{HOST}:{port}/ws"
    try:
        async with websockets.connect(url, close_timeout=2) as ws:
            initial_deadline = _request_recv_deadline(
                deadline,
                request_timeout_seconds,
                drain_timeout_seconds,
            )
            await _drain_initial_render(ws, initial_deadline)

            login_req = {
                "type": "userAction",
                "userAction": {
                    "name": "auth.login_submit",
                    "context": {
                        "login_form": {"username": "admin", "password": "password"}
                    },
                },
                "request_id": f"login_{worker_id}",
            }
            start = time.perf_counter()
            await ws.send(json.dumps(login_req))

            jwt = None
            login_deadline = _request_recv_deadline(
                deadline,
                request_timeout_seconds,
                drain_timeout_seconds,
            )
            for _ in range(10):
                try:
                    resp = await _recv_until_deadline(ws, login_deadline)
                except asyncio.TimeoutError:
                    break
                data = json.loads(resp)
                if isinstance(data, dict) and "jwt" in data:
                    jwt = data["jwt"]
                    break
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "jwt" in item:
                            jwt = item["jwt"]
                            break
                    if jwt:
                        break

            if not jwt:
                if (
                    deadline is not None
                    and _remaining_time(deadline) is not None
                    and _remaining_time(deadline) <= 0
                ):
                    return
                with open("benchmark_errors.log", "a", encoding="utf-8") as f:
                    f.write(f"Worker {worker_id} (Port {port}): Failed to get JWT\n")
                results["errors"] += 1
                return

            results["total_requests"] += 1
            results["latencies"].append(time.perf_counter() - start)

            i = 0
            while True:
                if deadline is not None:
                    if time.perf_counter() >= deadline:
                        break
                elif i >= cycles:
                    break

                path = nav_paths[i % len(nav_paths)]
                start = time.perf_counter()
                nav_req = {
                    "type": "userAction",
                    "userAction": {
                        "name": "nav",
                        "context": {"path": path},
                    },
                    "jwt": jwt,
                    "request_id": f"nav_{worker_id}_{i}",
                }
                await ws.send(json.dumps(nav_req))

                success = False
                recv_deadline = _request_recv_deadline(
                    deadline,
                    request_timeout_seconds,
                    drain_timeout_seconds,
                )
                for _ in range(max_messages):
                    try:
                        resp = await _recv_until_deadline(ws, recv_deadline)
                    except asyncio.TimeoutError:
                        break
                    if "beginRendering" in resp:
                        success = True
                        break

                if success:
                    results["total_requests"] += 1
                    results["latencies"].append(time.perf_counter() - start)
                else:
                    if (
                        deadline is not None
                        and _remaining_time(deadline) is not None
                        and _remaining_time(deadline) <= 0
                    ):
                        break
                    results["errors"] += 1
                    with open("benchmark_errors.log", "a", encoding="utf-8") as f:
                        f.write(
                            f"Worker {worker_id} (Port {port}): beginRendering not found in {max_messages} messages\n"
                        )

                i += 1
                if think_time_ms > 0:
                    await asyncio.sleep(think_time_ms / 1000.0)

    except Exception as e:
        results["errors"] += 1
        with open("benchmark_errors.log", "a", encoding="utf-8") as f:
            f.write(f"Worker {worker_id} (Port {port}) EXCEPTION: {e}\n")


async def main(
    workers_per_instance=16,
    num_instances=1,
    clients_per_worker=10,
    cycles=30,
    duration_seconds=None,
    exe_path=None,
    profile_log_summary=False,
    profile_name="custom",
    nav_paths_override=None,
    think_time_ms_override=None,
    request_timeout_seconds=30.0,
):
    profile = PROFILE_PRESETS.get(profile_name)
    if profile is not None:
        workers_per_instance = workers_per_instance or profile.workers
        clients_per_worker = clients_per_worker or profile.clients
        cycles = cycles or profile.cycles
        duration_seconds = (
            duration_seconds
            if duration_seconds is not None
            else profile.duration_seconds
        )
        nav_paths = (
            tuple(nav_paths_override) if nav_paths_override else profile.nav_paths
        )
        think_time_ms = (
            int(think_time_ms_override)
            if think_time_ms_override is not None
            else profile.think_time_ms
        )
        max_messages = profile.max_messages
    else:
        nav_paths = (
            tuple(nav_paths_override)
            if nav_paths_override
            else ("/components/_effects/yaml",)
        )
        think_time_ms = int(think_time_ms_override or 0)
        max_messages = 20

    total_workers = max(1, workers_per_instance) * max(1, num_instances)
    total_clients = total_workers * clients_per_worker
    run_mode = (
        f"duration={duration_seconds}s"
        if duration_seconds is not None and duration_seconds > 0
        else f"cycles={cycles}"
    )
    print("--- Stricter Multi-Core Stress Benchmark ---")
    print(
        f"Profile={profile_name} instances={num_instances} workers/instance={workers_per_instance} "
        f"clients/worker={clients_per_worker} {run_mode} think_time_ms={think_time_ms}"
    )
    print(f"Paths={list(nav_paths)}")

    if os.path.exists("benchmark_errors.log"):
        os.remove("benchmark_errors.log")
    for index in range(max(1, num_instances)):
        log_path = f"server_worker_{index}.log"
        if os.path.exists(log_path):
            os.remove(log_path)

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

        log_path = f"server_worker_{i}.log"
        print(
            f"  -> Starting instance {i} on port {port} with {workers_per_instance} worker(s) (LOGGING to {log_path})..."
        )
        log_f = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT)
        server_procs.append(proc)
        await asyncio.sleep(1.5)

    try:
        print("Waiting for all instances to be up (this may take a while)...")
        for port in ports:
            proc = server_procs[ports.index(port)]
            if proc.poll() is not None:
                raise RuntimeError(
                    f"instance_on_port_{port}_exited_during_startup: code={proc.returncode}"
                )
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
                    nav_paths=nav_paths,
                    think_time_ms=think_time_ms,
                    max_messages=max_messages,
                    request_timeout_seconds=request_timeout_seconds,
                    deadline=deadline,
                    drain_timeout_seconds=2.0,
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

        if profile_log_summary:
            print("\n--- Request Profile Summary (worker 0) ---")
            print(summarize_profile_log("server_worker_0.log"))

    finally:
        print("Shutting down servers...")
        stuck = terminate_processes(server_procs, timeout_s=10.0)
        if stuck:
            print(f"Forced shutdown for stuck server pids: {stuck}")
