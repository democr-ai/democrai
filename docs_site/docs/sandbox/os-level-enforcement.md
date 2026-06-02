# OS-Level Enforcement

The Python-level sandbox is the semantic layer: it knows the active subject, subject chain, session, and approvals.

On Linux, Democr.ai can add OS-level enforcement underneath it. This layer is designed to block bypasses that leave Python through native code, child processes, or direct sockets.

OS-level enforcement is not a replacement for structured manifest access declarations or access-policy approvals. It is a second line of defense for deployments that need kernel-level controls.

## Controls

The Linux OS-level layer is made of three independent controls.

| Control | Purpose | Enforcement scope |
|---|---|---|
| Landlock | restrict filesystem access to read-only and read-write path allowlists | current process and future children after restriction |
| seccomp BPF | block dangerous syscalls such as process execution, ptrace, kernel module loading, filesystem root pivots, UID changes, BPF loading, and common exploit primitives | current process, with TSYNC attempted for all threads |
| iptables/ip6tables + cgroup v2 | restrict outbound network egress to allowed IP/port pairs for the application process cgroup | process-level network egress |

Landlock and seccomp are applied directly by the application process when enabled and supported. Network egress enforcement is applied by a privileged local helper because it needs access to cgroup and packet-filtering operations.

SDK subprocess execution has an additional launcher path. When `sandbox.os.enabled` is true, `sdk.tasks.run_subprocess(...)` starts a small sandbox launcher instead of executing the target command directly. The launcher receives the current parent guard policy, applies the available OS-level filesystem restrictions to the child process, and then executes the requested command.

## Configuration

Process restrictions are controlled separately:

```yaml
sandbox:
  os:
    seccomp:
      enabled: true
    landlock:
      enabled: true
      extra_read_paths:
        - /opt/democrai/read-only
      extra_write_paths:
        - /srv/democrai/work
```

Network allowlist enforcement uses these keys:

```yaml
sandbox:
  os:
    enabled: true
    policy_file: /var/lib/democrai/os_sandbox_allowlist.json
    helper_socket: /run/democrai/os_sandbox_helper.sock
    refresh_seconds: 60
```

If paths are not configured, the runtime uses per-process local defaults under the application data and state directories. The default names include the application process identifier:

- `<state_dir>/os_sandbox_helper_<pid>.sock`
- `<data_dir>/os_sandbox_allowlist_<pid>.json`

This allows multiple application instances on the same machine to run separate helpers and policy files while applying the same logical allowlist to their own process IDs.

## Runtime Requirements

OS-level enforcement is Linux-only.

Landlock requires a kernel with Landlock ABI support. The implementation requires ABI version 1 or newer, which starts with Linux 5.13.

seccomp BPF support currently depends on:

- Linux
- libc availability
- a supported architecture, currently `x86_64` or `aarch64`

Network egress enforcement depends on:

- cgroup v2 mounted at `/sys/fs/cgroup`
- `iptables` and `ip6tables`
- permission to create cgroups and install packet-filtering rules

If the application process already has the required privileges, the helper can start directly. Otherwise desktop mode uses `pkexec` when available, and non-desktop mode uses `sudo` when available. Server deployments that enable OS network enforcement should provide a deliberate elevation path, such as a dedicated `sudoers` rule for the helper command.

## Landlock Filesystem Rules

Landlock builds two path lists:

- read-only paths for system and runtime dependencies
- read-write paths for application data, configuration, cache, state, logs, user module directories, configured extra module/engine/extractor directories, temp, and local media storage

Configured `sandbox.os.landlock.extra_read_paths` and `sandbox.os.landlock.extra_write_paths` are appended to those lists.

Only paths that exist when Landlock is applied can be added. Landlock restriction is irrevocable for the process after it is applied, so it is applied after setup storage has been initialized.

The implementation checks the Landlock ABI before applying rules.

For SDK subprocesses, the launcher derives the child Landlock rules from the filesystem access rules already active in the parent guard. `read` and `execute` entries become read-only paths. `create`, `modify`, and `delete` entries become read-write paths. If the platform is not Linux or Landlock is not supported, the launcher does not apply filesystem restrictions and the subprocess continues through the normal SDK execution path.

## seccomp BPF

The seccomp filter is a blocklist for high-risk syscalls. It currently supports known syscall numbers for `x86_64` and `aarch64`.

The blocked groups include:

- `execve` and `execveat`
- `ptrace`
- `kexec`
- kernel module loading and unloading
- `pivot_root` and `chroot`
- UID/GID changing syscalls
- `bpf`
- `perf_event_open`
- `userfaultfd`

The filter uses `SECCOMP_RET_KILL_PROCESS` for blocked syscalls. It sets `PR_SET_NO_NEW_PRIVS`, attempts `SECCOMP_FILTER_FLAG_TSYNC` to cover all threads, and falls back to applying the filter to the current thread if TSYNC is rejected.

## Network Egress Allowlist

The network allowlist is built from runtime sources:

- remote service endpoints from configuration
- module manifests
- engine manifests
- extractor manifests
- MCP server registry entries
- permanent access-policy approvals
- session access-policy approvals
- observed runtime endpoints recorded after Python-level checks

The allowlist is serialized to a local JSON policy file. The helper reads that file, resolves hostnames to IP addresses, creates a cgroup for the target process, and installs `iptables` and `ip6tables` `OUTPUT` rules that allow only matching destination IP/port pairs for that cgroup.

The cgroup and packet-filtering names are per process:

- cgroup suffix: `democrai_os_sandbox_<pid>`
- chain base: `DEMOCRAI_OS_<pid>`
- active/pending chains: `DEMOCRAI_OS_<pid>_A` and `DEMOCRAI_OS_<pid>_B`

The helper builds the pending chain, inserts the jump for the process cgroup, and then removes the previous chain for that same process. Different application instances on the same host therefore use distinct cgroups and distinct iptables chains by default.

System DNS resolvers from `/etc/resolv.conf` are added automatically on UDP and TCP port `53`.

The helper periodically reapplies the policy when `refresh_seconds` is greater than zero. This keeps DNS-derived IP rules aligned with changing DNS answers.

Same-machine multi-instance deployment and multi-node deployment solve different problems:

- same-machine instances need per-process helper sockets, policy files, cgroups, and iptables chains; the defaults provide this isolation
- multi-node instances need approval refresh events to reach processes on other hosts; use a stream provider that crosses hosts, such as Redis

With an in-memory stream provider, refresh events are local to one process. Same-host instances can share a host-local IPC stream only if that provider is shared by all relevant processes. Multi-node deployments need a networked provider.

When an instance observes a session or permanent approval during an access check and OS allowlist enforcement is active, it also refreshes and applies its local allowlist. This is a local safety net for delayed refresh events; the normal propagation mechanism is still the distributed stream.

## Privileged Helper

The helper is intentionally small. It receives:

- socket path
- policy file path
- refresh interval
- parent PID

It does not read application config, module manifests, engine manifests, extractor manifests, or database approvals. The application builds the policy file; the helper only validates and applies it.

The Unix socket client is authenticated with `SO_PEERCRED`. The helper accepts requests only when:

- the client UID matches the expected application user
- the client process is the parent process or a descendant of it
- the requested target PID, when provided, is also the parent process or a descendant

The helper also validates the policy file owner and permissions before reading it. The policy file must be owned by the expected client user and must not be group- or world-writable.

The helper can be started:

- directly when the process already has the privileges needed for cgroup and iptables operations
- through `pkexec` in desktop mode
- through `sudo` outside desktop mode

It runs a watchdog for the parent process. On modern Linux it uses `pidfd_open` when available; otherwise it falls back to polling with `kill(pid, 0)`. If the parent exits, the helper exits.

## Limits and Tradeoffs

The OS-level network policy is process-level, not truly per session. Session approvals can open a target at the process egress layer while the Python-level guard still keeps subject/session semantics.

The network policy filters `OUTPUT`. It does not filter `INPUT`, `FORWARD`, or NAT.

The network policy is IP-and-port based after DNS resolution. It does not enforce hostname, HTTP path, TLS SNI, or HTTP method.

Host patterns that cannot be resolved to concrete hostnames are not directly materialized as iptables rules. Concrete runtime endpoints that pass the Python-level policy can be recorded and included in later OS allowlist refreshes.

Landlock and seccomp are Linux-only and depend on kernel and architecture support. Unsupported controls are skipped or reported as unsupported by status helpers instead of silently pretending to apply.

## Why This Design

This design is different from a virtual environment, restricted Python, or a container-only model:

| Alternative | What it does not solve alone | Democr.ai sandbox layer |
|---|---|---|
| Python virtual environment | does not restrict filesystem or network access | runtime guard plus optional kernel controls |
| restricted Python style | does not reliably control native libraries or direct syscalls | Python-level policy backed by OS-level enforcement |
| subprocess/container isolation only | can be expensive or coarse for in-process module execution | in-process guard for normal runtime plus kernel controls where available |

The result is a layered model: subject-aware policy in Python, administrator approval state in the application, and Linux kernel enforcement for deployments that require it.
