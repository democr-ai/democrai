# Sandbox Infrastructure

This package applies runtime access policies. The sandbox does not define module,
engine or extractor behavior; it enforces the permissions declared in manifests,
configuration and runtime approvals.

The runtime has three enforcement layers:

- Python-level in-process sandboxing.
- Process-level Linux restrictions.
- OS-level Linux network egress enforcement.

## Python-Level Sandbox

`process_guard.py` controls:

- filesystem access through `open`, `io.open`, `os.open` and
  `pathlib.Path.*`, plus common `os`, `os.path` and `shutil` path operations.
- access to external filesystem paths through the external access approval
  service.
- network calls through `network_policy_context`.
- imports of sensitive native-code roots such as `ctypes` unless explicitly
  allowed.
- mutation of protected `DEMOCRAI_*` environment variables.
- subprocess creation and `os.fork`.

Install flows for engines and extractors may enable `allow_subprocess=true`.
That mode is limited to installation contexts and exists because package
installers and Python stdlib cleanup paths use subprocesses and `dir_fd` APIs.

Normal runtime contexts keep stricter subprocess and `dir_fd` behavior.

When a subprocess is allowed by executable access but `allow_subprocess` is not
set, the guard launches it through the sandbox launcher. The launcher writes a
temporary policy file and restores the subject/access context in the child
process from environment variables.

Nested guard contexts inherit parent access by default. Callers can opt out with
`inherit_parent_access=false`, and can opt out of implicit application runtime
access with `include_runtime_access=false`.

## Process-Level Linux Restrictions

When enabled in config, OS process restrictions are applied during bootstrap
before network allowlist refresh:

- Seccomp applies a syscall blocklist when supported.
- Landlock applies filesystem rules when supported.

Landlock receives read-only access to system and Python runtime paths, and
read-write access to application data/config/cache/state/log paths, runtime
module/engine/extractor roots, temporary directories and local media storage.
Additional paths can be configured with
`sandbox.os.landlock.extra_read_paths` and
`sandbox.os.landlock.extra_write_paths`.

These restrictions apply to the current process and are intentionally separate
from the Python-level process guard. The Python guard owns semantic application
policy; Landlock/seccomp provide kernel-level containment for the process.

## Skill Script Sandbox

Skill scripts run in a child process with a dedicated policy. The runner uses a
process guard context with:

- no inherited parent access by default.
- no implicit runtime access by default.
- explicit filesystem access to the skill root, requested script and minimal
  Python runtime.

The child process is launched through the sandbox path so Landlock can be
applied when supported. Network access is applied per process by the privileged
helper. By default, skill scripts start with an empty network allowlist.

The behavior is fail-closed: if the privileged helper is required but not
available, the script is not executed.

## OS-Level Network Enforcement

On Linux, when `sandbox.os.enabled=true`, OS-level enforcement:

- builds a global application allowlist from config, module manifests, engine
  manifests, extractor manifests, MCP server rows, external access approvals
  and observed runtime endpoints.
- writes a local JSON policy file.
- applies `iptables`/`ip6tables` and cgroup v2 rules through a privileged
  helper.
- automatically includes system DNS resolvers from `/etc/resolv.conf`.
- periodically refreshes DNS/IP resolution.

The policy file, observed endpoints file and helper socket are local to the
node.

The allowlist is stored in `app_ctx().os_network_allowlist` and refreshed
through an application event. When enforcement is active, refresh events reapply
the current allowlist to the application process and to the engine orchestrator
process when it exists.

Kernel enforcement is PID/cgroup scoped. Applying a policy moves the target PID
into a dedicated cgroup and installs OUTPUT-chain rules for that cgroup. Rules
allow loopback, DNS resolver endpoints and resolved IP addresses for the
allowlisted host/port/protocol entries, then reject everything else.

### Install CONNECT Proxy

Engine and extractor installation may need to download packages from hosts whose
DNS answers change during a single `pip` run. The OS allowlist is still enforced
at the kernel level, but an IP resolved by `iptables` may become stale when a
package index or CDN returns a different address later.

For this case the privileged helper can expose a local HTTP CONNECT proxy:

- the proxy is owned by the OS sandbox helper and binds only to `127.0.0.1`.
- the application creates a short-lived proxy session with the same network
  allowlist already used for OS enforcement.
- the install process receives `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY`
  pointing to that local proxy.
- the install process is still added to the OS network allowlist cgroup, so
  direct outbound connections remain blocked.
- the proxy accepts only CONNECT tunnels whose `host:port` is present in the
  session allowlist.
- the proxy does not terminate TLS, inspect package contents or rewrite
  requests.

This keeps DNS/CDN churn outside the restricted install process. The helper is
the only component that opens the external TCP connection, and it does so only
after validating the requested endpoint against the application-provided
allowlist.

The proxy is not the application media proxy. `/media/proxy` is an application
HTTP endpoint for authorized media fetching; it is not a process-level forward
proxy and cannot be used by package installers.

## Privileged Helper

The helper is intentionally narrow. It receives only:

- socket path.
- policy file path.
- parent PID.

It does not read `config.yaml`, `app_ctx`, module metadata, engine metadata,
extractor metadata or approvals from the database. The application computes
policy; the helper only applies endpoint payloads or policy files it is given.

The local client is authenticated with `SO_PEERCRED`. The helper accepts
requests only from the application user and only for the parent process or its
descendants.

The helper supports four core actions:

- `apply`: load the current policy file and apply it to a PID.
- `apply_endpoints`: apply an explicit endpoint payload to a PID.
- `clear`: remove the PID-scoped network rules.
- `ping`: validate helper readiness and Linux enforcement support.

The helper also owns short-lived install proxy sessions. Session creation and
removal are requested over the same authenticated Unix socket. Session tokens
are passed to the install process through proxy URL credentials and are not part
of the persistent policy file.

The helper can be started directly when the current process has the required
privileges. Otherwise desktop mode may use `pkexec`, and non-desktop mode may
use `sudo`, depending on what is available.

## Distributed Deployments

The source of truth may be distributed, but enforcement remains node-local. Each
node builds its own allowlist, writes its own policy file and uses its own local
helper.

Do not share a single policy file across nodes.

## Rules

- Keep semantic access decisions in the application layer.
- Keep kernel-level enforcement local and narrow.
- Do not let modules, engines or extractors write sandbox policy directly.
- Fail closed when OS-level enforcement is required but unavailable.
