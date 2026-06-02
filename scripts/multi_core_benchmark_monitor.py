import asyncio
import time

import psutil


class MultiMonitoring:
    def __init__(self, pids):
        self.pids = pids
        self.samples = []
        self._stop = False
        self._proc_objs = {}
        self._last_cpu_times = {}
        self._last_poll_ts = None
        for pid in pids:
            self._prime_process(pid)

    def _prime_process(self, pid):
        try:
            proc = psutil.Process(pid)
            self._proc_objs[pid] = proc
        except psutil.NoSuchProcess:
            pass

    def _read_pss_bytes(self, pid):
        smaps_rollup = f"/proc/{pid}/smaps_rollup"
        try:
            with open(smaps_rollup, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("Pss:"):
                        return int(line.split()[1]) * 1024
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            return None
        return None

    def _collect_process_tree(self):
        procs = {}
        for pid in list(self.pids):
            proc = self._proc_objs.get(pid)
            if proc is None:
                self._prime_process(pid)
                proc = self._proc_objs.get(pid)
            if proc is None:
                continue
            try:
                procs[proc.pid] = proc
                for child in proc.children(recursive=True):
                    procs[child.pid] = child
                    if child.pid not in self._proc_objs:
                        child.cpu_percent(interval=None)
                        self._proc_objs[child.pid] = child
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return list(procs.values())

    async def poll(self):
        while not self._stop:
            now = time.perf_counter()
            elapsed = now - self._last_poll_ts if self._last_poll_ts is not None else None
            total_cpu_seconds = 0.0
            total_rss = 0.0
            total_uss = 0.0
            total_pss = 0.0
            has_uss = False
            has_pss = False
            for proc in self._collect_process_tree():
                try:
                    cpu_times = proc.cpu_times()
                    total_cpu_time = float(cpu_times.user) + float(cpu_times.system)
                    last_cpu_time = self._last_cpu_times.get(proc.pid)
                    self._last_cpu_times[proc.pid] = total_cpu_time
                    if elapsed and last_cpu_time is not None:
                        total_cpu_seconds += max(0.0, total_cpu_time - last_cpu_time)

                    mem = proc.memory_info()
                    total_rss += mem.rss / 1024 / 1024

                    try:
                        full_mem = proc.memory_full_info()
                        uss = getattr(full_mem, "uss", None)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        uss = None

                    if uss is not None:
                        total_uss += uss / 1024 / 1024
                        has_uss = True

                    pss = self._read_pss_bytes(proc.pid)
                    if pss is not None:
                        total_pss += pss / 1024 / 1024
                        has_pss = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            self.samples.append(
                {
                    "cpu": (total_cpu_seconds / elapsed * 100.0) if elapsed else 0.0,
                    "rss": total_rss,
                    "uss": total_uss if has_uss else None,
                    "pss": total_pss if has_pss else None,
                }
            )
            self._last_poll_ts = now
            await asyncio.sleep(0.5)

    def stop(self):
        self._stop = True

    def report(self):
        if not self.samples:
            return "No samples collected."
        avg_cpu = sum(s["cpu"] for s in self.samples) / len(self.samples)
        max_rss = max(s["rss"] for s in self.samples)
        lines = [
            f"Avg Total CPU: {avg_cpu:.1f}% (across all workers and descendants)",
            f"Peak Total RSS: {max_rss:.1f} MB",
        ]

        uss_samples = [s["uss"] for s in self.samples if s["uss"] is not None]
        if uss_samples:
            lines.append(f"Peak Total USS: {max(uss_samples):.1f} MB")

        pss_samples = [s["pss"] for s in self.samples if s["pss"] is not None]
        if pss_samples:
            lines.append(f"Peak Total PSS: {max(pss_samples):.1f} MB")

        return "\n".join(lines) + "\n"
