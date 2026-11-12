#!/usr/bin/env python3
"""BuildShield launcher and service manager.

Works on Windows, macOS and Linux. Only the Python standard library is used, so
the launcher itself has no install step.

    ./buildshield start            check/install Docker, then start the stack
    ./buildshield stop             stop the stack (database volume kept)
    ./buildshield restart          restart application services
    ./buildshield status           container + endpoint health
    ./buildshield monitor          watch health, restart failed services
    ./buildshield logs [service]   show logs (-f to follow)
    ./buildshield doctor           diagnose Docker and configuration
    ./buildshield install-docker   install Docker for this operating system
    ./buildshield open             open the dashboard
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.yml"
ENV_FILE = ROOT / ".env"
DASHBOARD_URL = "http://localhost:{port}"
DEFAULT_WEB_PORT = "3000"
DEFAULT_API_PORT = "8000"

APP_SERVICES = ("api", "web")
RESTARTABLE = ("api", "web", "db")
ONE_SHOT = ("setup",)

RESTART_COOLDOWN_SECONDS = 300
MAX_RESTARTS_PER_WINDOW = 3


# --------------------------------------------------------------------- output

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}


def _enable_ansi() -> bool:
    if os.name == "nt":
        try:
            os.system("")  # asks Windows to interpret escape sequences
            return True
        except Exception:
            return False
    return sys.stdout.isatty()


USE_COLOR = _enable_ansi()


def paint(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    return f"{_ANSI.get(color, '')}{text}{_ANSI['reset']}"


def ok(message: str) -> None:
    print(f"  {paint('[ok]', 'green')} {message}")


def info(message: str) -> None:
    print(f"  {paint('[--]', 'dim')} {message}")


def warn(message: str) -> None:
    print(f"  {paint('[!]', 'yellow')} {message}")


def bad(message: str) -> None:
    print(f"  {paint('[x]', 'red')} {message}")


def title(message: str) -> None:
    print(paint(message, "bold"))


def confirm(question: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"  {question} [y/N] ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


class LauncherError(Exception):
    """A failure with a short explanation and actionable hints."""

    def __init__(self, message: str, hints: Optional[Sequence[str]] = None):
        super().__init__(message)
        self.hints = list(hints or [])


# ------------------------------------------------------------------ utilities


def run(
    command: Sequence[str],
    timeout: Optional[float] = 120.0,
    check: bool = False,
    capture: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            list(command),
            cwd=str(ROOT),
            capture_output=capture,
            text=True,
            timeout=timeout,
            check=check,
            env=env,
        )
    except FileNotFoundError as error:
        raise LauncherError(f"Command not found: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise LauncherError(
            f"Command timed out after {timeout}s: {' '.join(command)}"
        ) from error


def have(program: str) -> bool:
    return shutil.which(program) is not None


def read_env_file() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not ENV_FILE.is_file():
        return values
    for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def ports() -> Tuple[str, str]:
    values = read_env_file()
    return (
        os.getenv("WEB_PORT") or values.get("WEB_PORT") or DEFAULT_WEB_PORT,
        os.getenv("API_PORT") or values.get("API_PORT") or DEFAULT_API_PORT,
    )


def port_number(value: str, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def web_port_number() -> int:
    return port_number(ports()[0], int(DEFAULT_WEB_PORT))


def api_port_number() -> int:
    return port_number(ports()[1], int(DEFAULT_API_PORT))


def dashboard_url() -> str:
    return DASHBOARD_URL.format(port=ports()[0])


def api_health_url() -> str:
    return f"http://localhost:{ports()[1]}/health"


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def tail_lines(text: str, count: int = 12) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines[-count:])


# -------------------------------------------------------------------- docker


def docker(*args: str, timeout: float = 60.0, capture: bool = True) -> subprocess.CompletedProcess:
    return run(["docker", *args], timeout=timeout, capture=capture)


def compose(*args: str, timeout: float = 180.0, capture: bool = True) -> subprocess.CompletedProcess:
    return docker("compose", *args, timeout=timeout, capture=capture)


def docker_cli_present() -> bool:
    return have("docker")


def docker_cli_version() -> Optional[str]:
    if not docker_cli_present():
        return None
    result = docker("--version", timeout=20)
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip()


def compose_present() -> bool:
    if not docker_cli_present():
        return False
    result = docker("compose", "version", timeout=20)
    return result.returncode == 0


def compose_version() -> Optional[str]:
    if not docker_cli_present():
        return None
    result = docker("compose", "version", timeout=20)
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def engine_state() -> Tuple[bool, str]:
    """Returns (running, diagnostic) for the Docker engine."""
    if not docker_cli_present():
        return False, "the docker command is not installed"

    result = docker("info", "--format", "{{.ServerVersion}}", timeout=20)
    if result.returncode == 0:
        return True, (result.stdout or "").strip()

    message = ((result.stderr or "") + (result.stdout or "")).strip()
    lowered = message.lower()
    if "permission denied" in lowered:
        return False, "permission denied while contacting the Docker socket"
    if "cannot connect" in lowered or "is the docker daemon running" in lowered:
        return False, "the Docker engine is not running"
    if "error during connect" in lowered:
        return False, "the Docker engine is not reachable"
    return False, message.splitlines()[0] if message else "unknown Docker engine error"


def engine_start_hint() -> List[str]:
    system = platform.system()
    if system == "Darwin":
        return [
            "Start Docker Desktop:  open -a Docker",
            "Wait until the whale icon stops animating, then run this command again.",
        ]
    if system == "Windows":
        return [
            "Start Docker Desktop from the Start menu and wait for \"Engine running\".",
            'Or from PowerShell:  Start-Process "Docker Desktop"',
            "If Docker Desktop is not installed:  .\\buildshield install-docker",
        ]
    return [
        "Start the daemon:  sudo systemctl start docker",
        "Then check:  sudo systemctl status docker",
        "If your user cannot access Docker:  sudo usermod -aG docker $USER  (then log out/in)",
    ]


def _start_engine_command() -> Optional[List[str]]:
    system = platform.system()
    if system == "Darwin":
        return ["open", "-a", "Docker"]
    if system == "Windows":
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Docker"
            / "Docker"
            / "Docker Desktop.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Docker"
            / "Docker"
            / "Docker Desktop.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return [str(candidate)]
        return None
    # Linux: prefer systemd, fall back to the service shim.
    if have("systemctl"):
        prefix = [] if os.geteuid() == 0 else ["sudo"]
        return [*prefix, "systemctl", "start", "docker"]
    if have("service"):
        prefix = [] if os.geteuid() == 0 else ["sudo"]
        return [*prefix, "service", "docker", "start"]
    return None


def start_engine(wait_seconds: float = 120.0, announce: bool = True) -> None:
    """Tries to start Docker Desktop / dockerd and waits for the engine."""
    running, _ = engine_state()
    if running:
        return

    command = _start_engine_command()
    if command is None:
        raise LauncherError(
            "Docker is installed but the engine is not running, and the launcher "
            "could not find a way to start it automatically.",
            engine_start_hint(),
        )

    if announce:
        info(f"Starting the Docker engine: {' '.join(command)}")

    try:
        if command[0] == "open":
            run(command, timeout=30, check=False)
        elif platform.system() == "Windows":
            subprocess.Popen(command, cwd=str(ROOT))  # noqa: S603 - fixed, resolved path
        else:
            result = run(command, timeout=60, check=False)
            if result.returncode != 0:
                detail = ((result.stderr or "") + (result.stdout or "")).strip()
                raise LauncherError(
                    "Could not start the Docker service.",
                    [detail] if detail else engine_start_hint(),
                )
    except LauncherError:
        raise
    except Exception as error:
        raise LauncherError(f"Could not start Docker: {error}", engine_start_hint()) from error

    if announce:
        info("Waiting for the Docker engine to become ready...")

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        running, _ = engine_state()
        if running:
            if announce:
                ok("Docker engine is running")
            return
        time.sleep(2)

    running, diagnostic = engine_state()
    if not running:
        raise LauncherError(
            f"The Docker engine did not become ready within {int(wait_seconds)}s ({diagnostic}).",
            engine_start_hint(),
        )


def ensure_docker(install: bool = False, assume_yes: bool = False, dry_run: bool = False) -> None:
    """Verifies CLI, engine and the compose plugin, installing Docker if asked."""
    if not docker_cli_present():
        if install:
            install_docker(assume_yes=assume_yes, dry_run=dry_run)
            if dry_run:
                return
        else:
            if not dry_run and confirm("Docker is not installed. Install it now?"):
                install_docker(assume_yes=assume_yes, dry_run=dry_run)
                if dry_run or not docker_cli_present():
                    if dry_run:
                        return
                    raise LauncherError(
                        "Docker is still not available after installation.",
                        [
                            "Open a new terminal so PATH picks up Docker, then run this again.",
                            "Or install manually: https://docs.docker.com/engine/install/",
                        ],
                    )
            else:
                raise LauncherError(
                    "Docker is not installed.",
                [
                    "Install it automatically:  ./buildshield install-docker",
                    "macOS:    brew install --cask docker",
                    "Windows:  winget install -e --id Docker.DockerDesktop",
                    "Linux:    curl -fsSL https://get.docker.com | sudo sh",
                ],
            )

    if not compose_present():
        raise LauncherError(
            "The Docker Compose plugin is missing (docker compose).",
            [
                "Docker Desktop bundles it; reinstall or update Docker Desktop.",
                "Linux: install the docker-compose-plugin package for your distribution.",
            ],
        )

    running, diagnostic = engine_state()
    if not running:
        if "permission denied" in diagnostic:
            raise LauncherError(
                "Your user cannot access the Docker socket.",
                [
                    "Add yourself to the docker group:  sudo usermod -aG docker $USER",
                    "Log out and back in (or run `newgrp docker`), then retry.",
                ],
            )
        info(f"Docker engine is not running ({diagnostic}); starting it...")
        if dry_run:
            info("dry run: would start the Docker engine")
            return
        start_engine()


# --------------------------------------------------------------- installation


def _install_plan() -> Tuple[List[List[str]], List[str], str]:
    """Returns (commands, notes, manual_url) for this operating system."""
    system = platform.system()

    if system == "Darwin":
        if have("brew"):
            return (
                [["brew", "install", "--cask", "docker"]],
                [
                    "Homebrew will install Docker Desktop.",
                    "After installation, open Docker once and accept its terms.",
                ],
                "https://docs.docker.com/desktop/install/mac-install/",
            )
        return (
            [],
            [
                "Homebrew was not found, so Docker Desktop must be installed manually.",
                "Download the Apple Silicon or Intel installer from the link below,",
                "drag Docker to Applications, then open it once.",
            ],
            "https://docs.docker.com/desktop/install/mac-install/",
        )

    if system == "Windows":
        if have("winget"):
            return (
                [
                    [
                        "winget",
                        "install",
                        "-e",
                        "--id",
                        "Docker.DockerDesktop",
                        "--accept-source-agreements",
                        "--accept-package-agreements",
                    ]
                ],
                [
                    "Windows will ask for administrator approval.",
                    "WSL 2 is required; Docker Desktop offers to install it on first run.",
                    "Sign out or reboot if the installer asks, then run: buildshield start",
                ],
                "https://docs.docker.com/desktop/install/windows-install/",
            )
        return (
            [],
            [
                "winget was not found, so Docker Desktop must be installed manually.",
                "Download the installer from the link below and run it.",
            ],
            "https://docs.docker.com/desktop/install/windows-install/",
        )

    # Linux
    notes = [
        "The official Docker convenience script will be used.",
        "It needs sudo and installs docker-ce plus the compose plugin.",
        "Afterwards your user is added to the docker group; log out/in to use it without sudo.",
    ]
    if have("curl"):
        downloader = ["curl", "-fsSL", "https://get.docker.com", "-o", "/tmp/get-docker.sh"]
    elif have("wget"):
        downloader = ["wget", "-qO", "/tmp/get-docker.sh", "https://get.docker.com"]
    else:
        return (
            [],
            [
                "Neither curl nor wget is available; install Docker from your package manager:",
                "  Debian/Ubuntu:  sudo apt install docker.io docker-compose-plugin",
                "  Fedora:         sudo dnf install docker docker-compose-plugin",
                "  Arch:           sudo pacman -S docker docker-compose",
            ],
            "https://docs.docker.com/engine/install/",
        )

    commands = [
        downloader,
        ["sudo", "sh", "/tmp/get-docker.sh"],
        ["sudo", "usermod", "-aG", "docker", os.environ.get("USER", "$USER")],
        ["sudo", "systemctl", "enable", "--now", "docker"],
    ]
    return commands, notes, "https://docs.docker.com/engine/install/"


def install_docker(assume_yes: bool = False, dry_run: bool = False) -> None:
    title("Installing Docker")
    commands, notes, manual_url = _install_plan()

    for note in notes:
        info(note)

    if not commands:
        warn("Automatic installation is not possible on this machine.")
        print(f"\n  Manual instructions: {manual_url}\n")
        return

    print("\n  Commands the launcher will run:")
    for command in commands:
        print(f"    {' '.join(command)}")

    if dry_run:
        info("dry run: nothing was executed")
        return

    if not assume_yes:
        if not confirm("Continue?", assume_yes=False):
            warn("Cancelled.")
            return

    for command in commands:
        info(f"Running: {' '.join(command)}")
        result = run(command, timeout=None, check=False, capture=False)
        if result.returncode != 0:
            raise LauncherError(
                f"Command failed (exit {result.returncode}): {' '.join(command)}",
                [f"Install Docker manually: {manual_url}"],
            )

    ok("Docker installation finished")

    if platform.system() == "Darwin":
        info("Opening Docker Desktop for the first-run setup...")
        run(["open", "-a", "Docker"], timeout=30, check=False)
    elif platform.system() == "Linux":
        warn("Log out and back in so your user can use Docker without sudo.")


# ----------------------------------------------------------------- compose ps


def compose_rows() -> List[Dict[str, object]]:
    """Returns one dict per container with normalised keys."""
    result = compose("ps", "--all", "--format", "json", timeout=60)
    if result.returncode != 0:
        message = ((result.stderr or "") + (result.stdout or "")).strip()
        raise LauncherError(
            "Could not read the container list.",
            [message.splitlines()[-1]] if message else [],
        )

    rows: List[Dict[str, object]] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        service = str(raw.get("Service") or raw.get("Name") or "unknown")
        rows.append(
            {
                "service": service,
                "name": str(raw.get("Name") or service),
                "state": str(raw.get("State") or "").lower(),
                "health": str(raw.get("Health") or "").lower(),
                "status": str(raw.get("Status") or ""),
                "exit": raw.get("ExitCode"),
                "ports": raw.get("Publishers") or [],
            }
        )
    return rows


def row_ok(row: Dict[str, object]) -> bool:
    state = str(row.get("state"))
    health = str(row.get("health"))
    service = str(row.get("service"))

    if service in ONE_SHOT:
        return state == "exited" and int(row.get("exit") or 0) == 0
    if state != "running":
        return False
    return health in {"", "healthy", "starting"} and health != "unhealthy"


def describe_row(row: Dict[str, object]) -> str:
    service = str(row.get("service"))
    state = str(row.get("state")) or "unknown"
    health = str(row.get("health"))

    if service in ONE_SHOT:
        if state == "exited" and int(row.get("exit") or 0) == 0:
            return paint("completed", "green")
        return paint(f"exit {row.get('exit')}", "red")
    if state == "running" and health == "healthy":
        return paint("healthy", "green")
    if state == "running" and health in {"", "starting"}:
        return paint("running", "cyan")
    if health == "unhealthy":
        return paint("unhealthy", "red")
    if state == "exited":
        return paint(f"stopped (exit {row.get('exit')})", "red")
    return paint(state, "yellow")


# ------------------------------------------------------------------ lifecycle


def wait_for_stack(timeout: float = 240.0, quiet: bool = False) -> bool:
    deadline = time.time() + timeout
    last_report = 0.0
    while time.time() < deadline:
        try:
            rows = compose_rows()
        except LauncherError:
            rows = []

        running = [row for row in rows if str(row.get("service")) in APP_SERVICES]
        containers_ready = bool(running) and all(row_ok(row) for row in running)
        api_ready = http_ok(api_health_url())
        web_port, _ = ports()
        web_ready = port_open(web_port_number())

        if containers_ready and api_ready and web_ready:
            return True

        if not quiet and time.time() - last_report > 8:
            pending = [str(row.get("service")) for row in running if not row_ok(row)]
            info(f"waiting for {', '.join(pending) or 'services'}...")
            last_report = time.time()
        time.sleep(2)

    return False


def cmd_start(args: argparse.Namespace) -> int:
    title("BuildShield — starting the stack")
    first_run = not ENV_FILE.is_file()

    ensure_docker(install=args.install_docker, assume_yes=args.yes, dry_run=args.dry_run)
    if args.dry_run:
        info("dry run: would run docker compose up -d" + (" --build" if not args.no_build else ""))
        return 0

    if first_run:
        info("First run: the setup wizard will generate secrets and the admin account.")

    command = ["up", "-d"]
    if not args.no_build:
        command.append("--build")

    info(f"docker compose {' '.join(command)}")
    result = compose(*command, timeout=None, capture=False)
    if result.returncode != 0:
        raise LauncherError(
            "docker compose could not start the stack.",
            [
                "Inspect the output above for the failing service.",
                "Port already allocated? Change WEB_PORT / API_PORT in .env.",
                "Run: ./buildshield doctor",
            ],
        )

    if not wait_for_stack(timeout=args.timeout):
        warn("Services did not all report healthy in time.")
        print_status()
        return 1

    ok("BuildShield is running")
    print_status()

    if first_run:
        print()
        info("Admin credentials were generated during setup:")
        print(f"    ./buildshield logs setup      (line: Admin password)")
        print(f"    or: docker compose logs setup")

    print()
    info(f"Dashboard: {dashboard_url()}")
    if args.monitor:
        return cmd_monitor(argparse.Namespace(interval=15, once=False, restart=True, quiet=False))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    title("BuildShield — stopping the stack")
    ensure_docker()
    result = compose("down", timeout=None, capture=False)
    if result.returncode != 0:
        raise LauncherError("docker compose down failed.", ["Run: ./buildshield doctor"])
    ok("Stack stopped (database volume kept; use `docker compose down -v` to wipe it)")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    title("BuildShield — restarting services")
    ensure_docker()

    services = [args.service] if args.service else list(APP_SERVICES)
    info(f"Restarting: {', '.join(services)}")
    result = compose("restart", *services, timeout=180, capture=False)
    if result.returncode != 0:
        raise LauncherError(
            "Restart failed.",
            ["The container may not exist yet: run ./buildshield start"],
        )

    if wait_for_stack(timeout=args.timeout):
        ok("Services are healthy again")
        return 0
    warn("Services restarted but are not healthy yet. Check ./buildshield logs")
    return 1


# --------------------------------------------------------------------- status


def print_status() -> None:
    try:
        rows = compose_rows()
    except LauncherError as error:
        bad(str(error))
        return

    web_port, api_port = ports()
    title("\nService status")
    print(f"  {'SERVICE':<10} {'CONTAINER':<28} {'STATE'}")
    print("  " + "-" * 62)
    for row in sorted(rows, key=lambda item: str(item.get("service"))):
        service = str(row.get("service"))
        name = str(row.get("name"))[:28]
        print(f"  {service:<10} {name:<28} {describe_row(row)}")

    print()
    api_up = http_ok(api_health_url())
    web_up = port_open(web_port_number())
    print(f"  API health   {paint('ok', 'green') if api_up else paint('unreachable', 'red')}   {api_health_url()}")
    print(f"  Dashboard    {paint('ok', 'green') if web_up else paint('unreachable', 'red')}   http://localhost:{web_port}")
    print(f"  Config       {'present' if ENV_FILE.is_file() else 'missing (setup will create it)'}   {ENV_FILE}")


def cmd_status(args: argparse.Namespace) -> int:
    if not docker_cli_present():
        bad("Docker is not installed. Run: ./buildshield install-docker")
        return 1

    running, diagnostic = engine_state()
    if not running:
        bad(f"Docker engine: {diagnostic}")
        for hint in engine_start_hint():
            info(hint)
        return 1

    print_status()
    rows = compose_rows()
    healthy = all(row_ok(row) for row in rows) if rows else False
    return 0 if healthy and http_ok(api_health_url()) else 1


def cmd_reset_data(args: argparse.Namespace) -> int:
    title("BuildShield - resetting working data")
    ensure_docker()

    warn(
        "This deletes every user, repository, scan, finding, audit entry, API token, "
        "session, notification and webhook."
    )
    info("The .env configuration, the schema and the GitHub connection are kept.")

    if not args.yes and not confirm("Delete all data and recreate the admin account?"):
        warn("Cancelled.")
        return 1

    info("Running the reset inside the API container...")
    result = compose(
        "exec", "-T", "api", "python", "-m", "app.reset_data", "--yes",
        timeout=None,
        capture=False,
    )
    if result.returncode != 0:
        raise LauncherError(
            "The data reset failed.",
            [
                "The API container must be running: ./buildshield start",
                "Then retry: ./buildshield reset-data",
            ],
        )

    ok("All working data removed; the admin password is printed above")
    info("Sign in, then connect a repository from the Repositories page.")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    url = dashboard_url()
    info(f"Opening {url}")
    webbrowser.open(url)
    return 0


# ---------------------------------------------------------------------- logs


def cmd_logs(args: argparse.Namespace) -> int:
    ensure_docker()
    command = ["logs", "--tail", str(args.tail)]
    if args.follow:
        command.append("-f")
    if args.service:
        command.append(args.service)
    return compose(*command, timeout=None, capture=False).returncode


# -------------------------------------------------------------------- monitor


def restart_service(service: str) -> bool:
    info(f"Restarting service: {service}")
    result = compose("restart", service, timeout=180, capture=True)
    if result.returncode != 0:
        # The container may be gone entirely; recreate it.
        result = compose("up", "-d", "--no-deps", service, timeout=300, capture=True)
    if result.returncode != 0:
        detail = tail_lines((result.stderr or "") + (result.stdout or ""))
        bad(f"Could not restart {service}")
        if detail:
            print(f"      {detail}")
        return False
    return True


def cmd_monitor(args: argparse.Namespace) -> int:
    ensure_docker()
    title("BuildShield — health monitor")

    history: Dict[str, List[float]] = {name: [] for name in RESTARTABLE}
    http_failures: Dict[str, int] = {}
    interval = max(2.0, float(args.interval))

    if args.once:
        info("Checking once")

    try:
        while True:
            try:
                rows = compose_rows()
            except LauncherError as error:
                bad(str(error))
                if args.once:
                    return 1
                time.sleep(interval)
                continue

            problems: List[Tuple[str, str]] = []
            for row in rows:
                service = str(row.get("service"))
                if service in ONE_SHOT:
                    if not row_ok(row):
                        problems.append((service, "setup exited with an error"))
                    continue
                if not row_ok(row):
                    problems.append((service, describe_row(row)))

            # Application-level check: healthy containers can still serve errors.
            api_ok = http_ok(api_health_url())
            web_port, _ = ports()
            web_ok = port_open(web_port_number())
            if not api_ok:
                http_failures["api"] = http_failures.get("api", 0) + 1
            else:
                http_failures["api"] = 0
            if not web_ok:
                http_failures["web"] = http_failures.get("web", 0) + 1
            else:
                http_failures["web"] = 0

            for service, counter in list(http_failures.items()):
                if counter >= 2 and not any(name == service for name, _ in problems):
                    problems.append((service, "endpoint not responding"))

            unresolved: List[str] = [service for service, _ in problems if service in ONE_SHOT]
            if not problems:
                if not args.quiet:
                    print(f"  {time.strftime('%H:%M:%S')}  {paint('all services healthy', 'green')}")
            else:
                for service, reason in problems:
                    warn(f"{time.strftime('%H:%M:%S')}  {service}: {reason}")

                if args.restart:
                    now = time.time()
                    for service, reason in problems:
                        if service not in RESTARTABLE:
                            continue
                        recent = [stamp for stamp in history[service] if now - stamp < RESTART_COOLDOWN_SECONDS]
                        history[service] = recent
                        if len(recent) >= MAX_RESTARTS_PER_WINDOW:
                            bad(
                                f"{service} keeps failing; giving up for "
                                f"{RESTART_COOLDOWN_SECONDS // 60} minutes."
                            )
                            info(f"Inspect logs: ./buildshield logs {service}")
                            continue
                        history[service].append(now)
                        if restart_service(service):
                            ok(f"{service} restarted")
                            http_failures[service] = 0
                        else:
                            bad(f"{service} could not be restarted")
                            unresolved.append(service)

                    if any(service in ONE_SHOT for service, _ in problems):
                        info("Setup failed. Re-run it with:")
                        print("    docker compose run --rm -e BUILDSHIELD_RECONFIGURE=1 setup")

            if args.once:
                return 1 if unresolved else 0
            time.sleep(interval)
    except KeyboardInterrupt:
        print()
        info("Monitor stopped")
        return 0


# --------------------------------------------------------------------- doctor


def cmd_doctor(args: argparse.Namespace) -> int:
    title("BuildShield — environment check")
    failures = 0

    def check(label: str, good: bool, detail: str = "", hints: Sequence[str] = ()) -> None:
        nonlocal failures
        if good:
            ok(f"{label}{': ' + detail if detail else ''}")
        else:
            failures += 1
            bad(f"{label}{': ' + detail if detail else ''}")
            for hint in hints:
                info(hint)

    system = platform.system()
    check("Operating system", True, f"{system} {platform.release()} ({platform.machine()})")
    check("Python", sys.version_info >= (3, 8), platform.python_version())

    cli_version = docker_cli_version()
    check(
        "Docker CLI",
        cli_version is not None,
        cli_version or "not found",
        ["Install it with: ./buildshield install-docker"],
    )

    compose_ok = compose_present()
    check(
        "Compose plugin",
        compose_ok,
        compose_version() or "not available",
        ["Docker Desktop includes it; on Linux install docker-compose-plugin"],
    )

    running, diagnostic = engine_state()
    check(
        "Docker engine",
        running,
        f"server {diagnostic}" if running else diagnostic,
        [] if running else engine_start_hint(),
    )

    check("Compose file", COMPOSE_FILE.is_file(), str(COMPOSE_FILE))
    check(
        "Configuration",
        ENV_FILE.is_file(),
        "(.env present)" if ENV_FILE.is_file() else "(.env missing — created on first start)",
    )

    if ENV_FILE.is_file():
        values = read_env_file()
        check(
            "Secrets",
            bool(values.get("SECRET_KEY")) and bool(values.get("GITHUB_WEBHOOK_SECRET")),
            "SECRET_KEY and GITHUB_WEBHOOK_SECRET set"
            if values.get("SECRET_KEY") and values.get("GITHUB_WEBHOOK_SECRET")
            else "SECRET_KEY or GITHUB_WEBHOOK_SECRET missing",
        )

    web_port, api_port = ports()
    if running:
        check(
            "Dashboard port",
            port_open(web_port_number()),
            f"localhost:{web_port} " + ("listening" if port_open(web_port_number()) else "free"),
        )
        check(
            "API port",
            port_open(api_port_number()),
            f"localhost:{api_port} " + ("listening" if port_open(api_port_number()) else "free"),
        )
        check("API health", http_ok(api_health_url()), api_health_url())

        try:
            rows = compose_rows()
        except LauncherError:
            rows = []
        unhealthy = [str(row.get("service")) for row in rows if not row_ok(row)]
        check(
            "Containers",
            bool(rows) and not unhealthy,
            "all healthy" if rows and not unhealthy else (", ".join(unhealthy) or "stack not started"),
            [] if rows else ["Start it with: ./buildshield start"],
        )

    print()
    if failures:
        warn(f"{failures} check(s) need attention")
        return 1
    ok("Everything looks good")
    return 0


# ----------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="buildshield",
        description="BuildShield launcher and service manager",
    )
    parser.add_argument("--version", action="version", version="BuildShield launcher 1.0")
    subparsers = parser.add_subparsers(dest="command")

    start = subparsers.add_parser("start", help="start the whole stack (default)")
    start.add_argument("--no-build", action="store_true", help="reuse existing images")
    start.add_argument("--install-docker", action="store_true", help="install Docker when missing")
    start.add_argument("--yes", action="store_true", help="do not ask before installing")
    start.add_argument("--dry-run", action="store_true", help="only print what would happen")
    start.add_argument("--timeout", type=float, default=240.0, help="seconds to wait for health")
    start.add_argument("--monitor", action="store_true", help="keep watching after startup")
    start.set_defaults(func=cmd_start)

    stop = subparsers.add_parser("stop", help="stop the stack")
    stop.set_defaults(func=cmd_stop)

    restart = subparsers.add_parser("restart", help="restart application services")
    restart.add_argument("service", nargs="?", help="api, web, db ... (default: api and web)")
    restart.add_argument("--timeout", type=float, default=180.0)
    restart.set_defaults(func=cmd_restart)

    status = subparsers.add_parser("status", help="show container and endpoint health")
    status.set_defaults(func=cmd_status)

    logs = subparsers.add_parser("logs", help="show service logs")
    logs.add_argument("service", nargs="?", help="api, web, db, mailhog, setup")
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("--tail", type=int, default=80)
    logs.set_defaults(func=cmd_logs)

    monitor = subparsers.add_parser("monitor", help="watch health and restart failed services")
    monitor.add_argument("--interval", type=float, default=15.0)
    monitor.add_argument("--once", action="store_true", help="check a single time")
    monitor.add_argument("--no-restart", dest="restart", action="store_false")
    monitor.add_argument("--quiet", action="store_true")
    monitor.set_defaults(func=cmd_monitor, restart=True)

    doctor = subparsers.add_parser("doctor", help="diagnose Docker and the configuration")
    doctor.set_defaults(func=cmd_doctor)

    install = subparsers.add_parser("install-docker", help="install Docker for this OS")
    install.add_argument("--yes", action="store_true")
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install_docker)

    reset = subparsers.add_parser("reset-data", help="delete all data and recreate the admin")
    reset.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    reset.set_defaults(func=cmd_reset_data)

    open_cmd = subparsers.add_parser("open", help="open the dashboard in a browser")
    open_cmd.set_defaults(func=cmd_open)

    return parser


def cmd_install_docker(args: argparse.Namespace) -> int:
    install_docker(assume_yes=args.yes, dry_run=args.dry_run)
    if args.dry_run:
        return 0
    if not docker_cli_present():
        warn("Docker is still not on PATH; open a new terminal and run ./buildshield doctor")
        return 1
    try:
        start_engine()
    except LauncherError as error:
        bad(str(error))
        for hint in error.hints:
            info(hint)
        return 1
    ok("Docker is ready")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    if os.name == "nt":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    parser = build_parser()
    commands = {
        "start", "stop", "restart", "status", "logs", "monitor", "doctor",
        "install-docker", "reset-data", "open",
    }
    raw = list(sys.argv[1:] if argv is None else argv)

    if not raw:
        raw = ["start"]
    elif raw[0] not in commands and raw[0] not in {"-h", "--help", "--version"}:
        # Flags without a subcommand belong to `start`.
        raw = ["start", *raw]

    args = parser.parse_args(raw)

    try:
        return int(args.func(args))
    except LauncherError as error:
        print()
        bad(str(error))
        for hint in error.hints:
            print(f"      {hint}")
        return 1
    except KeyboardInterrupt:
        print()
        info("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
