"""Photograph every screen the browser smoke scripts walk, in a throwaway stack.

    docker compose -f docker/docker-compose.screenshots.yml run --rm --build shots

This is the entrypoint of the run-once container in ``docker/Dockerfile.shots``.
It starts the dev server -- in memory, with the fake GPU box -- seeds the demo
story into it exactly as ``devserver --seed`` does, then runs each smoke script
with ``SHOTS`` pointing into one folder per run:

    screenshots/
      index.html                       every run, newest first
      2026-10-15-190412-5f9d466/
        index.html                     the contact sheet: every screen at a glance
        manifest.json                  the commit, the timings, and what passed
        devserver.log, seed.log
        smoke_story_map/
          01-map-all-threads.png ...
          log.txt

The scripts are checks first and cameras second. One that fails still leaves
the screens it reached and a log saying why, and the container exits 1, so
Container Manager shows the run red. Nothing here can reach real data: the
database is mongomock inside this container, and compose gives the container
no network at all.

``SHOTS_ONLY=smoke_story_map,smoke_goals`` runs a subset.
"""

from __future__ import annotations

import html
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from visualizer.devserver import DEV_PASSWORD, DEV_USER, SEEDS, seed_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = Path(os.environ.get("SHOTS_OUT", "/shots"))
# The repo's .git, mounted read-only, so a run can say which commit it shows.
GIT = Path(os.environ.get("SHOTS_GIT", "/repo.git"))
PORT = 5050
BASE = f"http://127.0.0.1:{PORT}"
# A fake research job walks seven stages; the slowest script asks for several.
SCRIPT_TIMEOUT = int(os.environ.get("SHOTS_SCRIPT_TIMEOUT", "900"))


@dataclass(frozen=True)
class Script:
    name: str     # its file under docker/, without .py
    title: str    # what a writer would call the screen
    served: bool  # drives the seeded dev server, rather than bringing its own


SCRIPTS = (
    # Each of these builds its own in-memory app and needs nothing from us.
    Script("smoke_goals_ui", "Goals on the timeline", served=False),
    Script("smoke_scenes_timeline", "The scenes timeline", served=False),
    Script("smoke_logos_writer", "The writing page", served=False),
    # These drive the seeded dev server. Readers before writers: the last two
    # change the demo world -- research notes, accepted fixes -- and nothing
    # earlier should photograph their leftovers.
    Script("smoke_service_nav", "The service navigation", served=True),
    Script("smoke_story_map", "The story map", served=True),
    Script("smoke_goals", "Goals", served=True),
    Script("smoke_prithvi_ui", "Maps", served=True),
    Script("smoke_research_studio_ui", "The research studio", served=True),
    Script("smoke_logos_editor_ui", "The writing page's editor", served=True),
)

PASSED, FAILED, TIMED_OUT, SKIPPED = "passed", "failed", "timed out", "skipped"


def say(message: str) -> None:
    print(f"shots: {message}", flush=True)


# -- which commit ------------------------------------------------------------


def read_commit(git: Path) -> tuple[str, str]:
    """``(short sha, branch)`` from a ``.git`` directory, with no git binary.

    The NAS has git, but Container Manager cannot pass its output in, and a
    mounted ``.git`` is only files: HEAD names a branch and the branch names a
    commit, loose or packed. Anything unexpected -- a worktree's ``.git`` file,
    a download with no ``.git`` at all -- is "unknown", never a failed run.
    """
    override = os.environ.get("SHOTS_COMMIT", "").strip()
    if override:
        return override[:7], ""
    try:
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head[:7], ""
        ref = head.removeprefix("ref: ")
        branch = ref.removeprefix("refs/heads/")
        loose = git / ref
        if loose.is_file():
            return loose.read_text().strip()[:7], branch
        for line in (git / "packed-refs").read_text().splitlines():
            sha, _, name = line.partition(" ")
            if name == ref:
                return sha[:7], branch
    except OSError:
        pass
    return "unknown", ""


# -- the stack being photographed --------------------------------------------


def start_server(log: Path) -> subprocess.Popen:
    """The dev server, fresh and in memory, with the fake GPU box behind it.

    ``--data`` points at /tmp so even its on-exit snapshot stays inside the
    container. Its own session, so stopping it takes any children with it.
    """
    return subprocess.Popen(
        [
            sys.executable, "-m", "visualizer.devserver",
            # --no-rate-limit: every script logs in from 127.0.0.1, and the
            # sixth login in a minute would otherwise be refused.
            "--fresh", "--no-reload", "--no-rate-limit", "--fake-gpubox",
            "--port", str(PORT), "--data", "/tmp/shots-devserver.json",
        ],
        cwd=REPO,
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def wait_for_port(timeout: float = 90.0) -> bool:
    # --no-reload takes several seconds to bind; the reloader is what is quick.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def seed(log: Path) -> bool:
    """Load the demo story through the real APIs, as ``devserver --seed`` does."""
    env = seed_env(BASE)
    with log.open("w") as out:
        for script in SEEDS:
            out.write(f"== {script}\n")
            out.flush()
            done = subprocess.run(
                [sys.executable, str(HERE / script)],
                cwd=REPO, env=env, stdout=out, stderr=subprocess.STDOUT,
                timeout=300, check=False,
            )
            if done.returncode != 0:
                out.write(f"== {script} failed ({done.returncode})\n")
                return False
    return True


def stop(server: subprocess.Popen) -> None:
    try:
        os.killpg(server.pid, signal.SIGINT)
        server.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(server.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# -- the scripts -------------------------------------------------------------


def run_script(script: Script, run_dir: Path, stack_ready: bool) -> dict:
    folder = run_dir / script.name
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "log.txt"
    result = {
        "script": script.name,
        "title": script.title,
        "log": log.relative_to(run_dir).as_posix(),
    }
    if script.served and not stack_ready:
        log.write_text("Skipped: the dev server did not start or its seed "
                       "failed. See devserver.log and seed.log.\n")
        return {**result, "status": SKIPPED, "exit_code": None, "seconds": 0,
                "shots": []}

    env = {
        **os.environ,
        "SHOTS": str(folder),
        # smoke_logos_writer defaults to WebKit; one engine draws every picture.
        "PLAYWRIGHT_BROWSER": "chromium",
    }
    # Only for the scripts that drive the dev server. To the self-contained
    # ones, BASE means "drive this instead of your own app", and they would log
    # in to the demo story with their own seed's password.
    if script.served:
        env["BASE"] = BASE
        # The dev server's account, under both names the scripts read it by:
        # some default to it already, smoke_service_nav to an admin of its own.
        env.update(SEED_USER=DEV_USER, SEED_PASSWORD=DEV_PASSWORD,
                   USER_NAME=DEV_USER, USER_PASSWORD=DEV_PASSWORD)
    started = time.monotonic()
    with log.open("w") as out:
        try:
            done = subprocess.run(
                [sys.executable, str(HERE / f"{script.name}.py")],
                cwd=HERE, env=env, stdout=out, stderr=subprocess.STDOUT,
                timeout=SCRIPT_TIMEOUT, check=False,
            )
            status = PASSED if done.returncode == 0 else FAILED
            code = done.returncode
        except subprocess.TimeoutExpired:
            out.write(f"\nshots: stopped after {SCRIPT_TIMEOUT}s\n")
            status, code = TIMED_OUT, None
    # In the order they were taken: some scripts number their screens and some
    # name them, and only the clock agrees across both.
    pictures = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime)
    return {
        **result,
        "status": status,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 1),
        "shots": [p.relative_to(run_dir).as_posix() for p in pictures],
    }


# -- the contact sheets ------------------------------------------------------

# The stack's own palette (src/visualizer/static/tokens.css), copied rather than
# linked: a contact sheet is opened from File Station or a share, far from any
# server that could serve the original.
CSS = """
:root{--bg:#f5f6fb;--surface:#fff;--surface-3:#eef0f6;--border:#e7e9f1;
--text:#1f2430;--muted:#6b7280;--accent:#6366f1;--danger:#dc2626;
--danger-soft:#fdecec;--warn:#b45309;--warn-soft:#fef3c7;--ok:#16a34a;
--ok-soft:#e5f6ec;--shadow:0 1px 2px rgba(16,24,40,.04),0 6px 20px rgba(16,24,40,.06);
--radius:14px;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#0e1016;--surface:#171a22;
--surface-3:#232838;--border:#282d3a;--text:#e6e8ee;--muted:#98a1b2;
--accent:#818cf8;--danger:#f87171;--danger-soft:#3a1f24;--warn:#fbbf24;
--warn-soft:#37300f;--ok:#4ade80;--ok-soft:#16311f;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 28px rgba(0,0,0,.4)}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{padding:2.5rem clamp(1rem,4vw,3rem) 1.5rem;max-width:90rem;margin:0 auto}
h1{font-size:1.9rem;letter-spacing:-.02em;margin:0 0 .35rem}
.meta{color:var(--muted);margin:0;display:flex;flex-wrap:wrap;gap:.35rem 1.1rem}
.meta code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
.summary{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.25rem 0 0;padding:0;list-style:none}
.summary a{display:inline-flex;align-items:center;gap:.45rem;padding:.35rem .75rem;
border-radius:999px;background:var(--surface);border:1px solid var(--border);
color:var(--text);font-size:.9rem}
main{max-width:90rem;margin:0 auto;padding:0 clamp(1rem,4vw,3rem) 4rem}
section{margin-top:2.5rem;scroll-margin-top:1rem}
.head{display:flex;align-items:baseline;flex-wrap:wrap;gap:.4rem .9rem;
border-bottom:1px solid var(--border);padding-bottom:.6rem;margin-bottom:1.1rem}
h2{font-size:1.2rem;margin:0}
.head .detail{color:var(--muted);font-size:.9rem}
.pill{font-size:.75rem;font-weight:600;letter-spacing:.02em;padding:.15rem .55rem;
border-radius:999px;text-transform:uppercase}
.passed{color:var(--ok);background:var(--ok-soft)}
.failed,.timed-out{color:var(--danger);background:var(--danger-soft)}
.skipped{color:var(--warn);background:var(--warn-soft)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:1.1rem}
figure{margin:0;background:var(--surface);border:1px solid var(--border);
border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
figure a{display:block;background:var(--surface-3)}
figure img{display:block;width:100%;height:12rem;object-fit:cover;object-position:top}
figcaption{padding:.55rem .8rem;font-size:.85rem;color:var(--muted);
overflow-wrap:anywhere}
.empty{color:var(--muted);font-style:italic;margin:0}
table{width:100%;border-collapse:collapse;background:var(--surface);
border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;
box-shadow:var(--shadow)}
th,td{text-align:left;padding:.7rem 1rem;border-bottom:1px solid var(--border)}
th{font-size:.8rem;color:var(--muted);font-weight:600;text-transform:uppercase;
letter-spacing:.04em}
tr:last-child td{border-bottom:0}
"""


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>\n"
    )


def _pill(status: str) -> str:
    return f'<span class="pill {status.replace(" ", "-")}">{status}</span>'


def _caption(path: str) -> str:
    """``smoke_story_map/02-band-unfolded.png`` -> ``band unfolded``."""
    stem = Path(path).stem
    head, _, rest = stem.partition("-")
    words = rest if head.isdigit() and rest else stem
    return words.replace("-", " ").replace("_", " ")


def contact_sheet(manifest: dict) -> str:
    """One run: every screen, grouped by the script that reached it."""
    results = manifest["scripts"]
    screens = sum(len(r["shots"]) for r in results)
    when = manifest["started"].replace("T", " ")[:16] + " UTC"
    commit = html.escape(manifest["commit"])
    branch = html.escape(manifest["branch"])
    meta = [
        f"<span>Commit <code>{commit}</code>{' on ' + branch if branch else ''}</span>",
        f"<span>{when}</span>",
        f"<span>{screens} screens</span>",
        f"<span>{manifest['seconds']:.0f} s</span>",
        '<span><a href="../index.html">All runs</a></span>',
    ]
    summary = "".join(
        f'<li><a href="#{r["script"]}">{_pill(r["status"])}'
        f'{html.escape(r["title"])}</a></li>'
        for r in results
    )
    sections = []
    for r in results:
        figures = "".join(
            f'<figure><a href="{html.escape(s)}"><img loading="lazy" '
            f'src="{html.escape(s)}" alt="{html.escape(r["title"])}: '
            f'{html.escape(_caption(s))}"></a>'
            f"<figcaption>{html.escape(_caption(s))}</figcaption></figure>"
            for s in r["shots"]
        )
        grid = (f'<div class="grid">{figures}</div>' if figures else
                '<p class="empty">No screenshots from this script.</p>')
        sections.append(
            f'<section id="{r["script"]}"><div class="head">'
            f'<h2>{html.escape(r["title"])}</h2>{_pill(r["status"])}'
            f'<span class="detail"><code>{r["script"]}.py</code> · '
            f'{r["seconds"]:.0f} s · <a href="{html.escape(r["log"])}">log</a>'
            f"</span></div>{grid}</section>"
        )
    body = (
        f'<header><h1>Screenshots</h1><p class="meta">{"".join(meta)}</p>'
        f'<ul class="summary">{summary}</ul></header>'
        f'<main>{"".join(sections)}</main>'
    )
    return _page(f"Screenshots · {manifest['commit']}", body)


def runs_index(out: Path) -> str:
    """Every run under ``out``, newest first."""
    rows = []
    for path in sorted(out.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        results = manifest.get("scripts", [])
        passed = sum(r["status"] == PASSED for r in results)
        screens = sum(len(r["shots"]) for r in results)
        verdict = PASSED if passed == len(results) else FAILED
        name = html.escape(path.parent.name)
        rows.append(
            f'<tr><td><a href="{name}/index.html">'
            f'{html.escape(manifest["started"].replace("T", " ")[:16])}</a></td>'
            f'<td><code>{html.escape(manifest["commit"])}</code></td>'
            f"<td>{_pill(verdict)} {passed} of {len(results)}</td>"
            f"<td>{screens}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>Run (UTC)</th><th>Commit</th><th>Scripts</th>"
        f'<th>Screens</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )
    body = (f"<header><h1>Screenshot runs</h1><p class=\"meta\"><span>"
            f"{len(rows)} runs, newest first</span></p></header>"
            f"<main>{table}</main>")
    return _page("Screenshot runs", body)


# -- handing the files over --------------------------------------------------


def hand_over(paths) -> None:
    """Give what this root container wrote to whoever owns the repo.

    Otherwise every screenshot on the NAS belongs to root, and File Station can
    show it but not tidy it away.
    """
    if os.geteuid() != 0:
        return
    try:
        owner = GIT.stat()
    except OSError:
        return
    for path in paths:
        try:
            os.chown(path, owner.st_uid, owner.st_gid)
        except OSError:
            pass


# -- the run -----------------------------------------------------------------


def main() -> int:
    only = {n.strip() for n in os.environ.get("SHOTS_ONLY", "").split(",") if n.strip()}
    unknown = only - {s.name for s in SCRIPTS}
    if unknown:
        say(f"no such script: {', '.join(sorted(unknown))}; "
            f"choose from {', '.join(s.name for s in SCRIPTS)}")
        return 2
    chosen = [s for s in SCRIPTS if not only or s.name in only]

    commit, branch = read_commit(GIT)
    started = datetime.now(UTC)
    run_dir = OUT / f"{started:%Y-%m-%d-%H%M%S}-{commit}"
    run_dir.mkdir(parents=True)
    say(f"commit {commit}{' on ' + branch if branch else ''}; "
        f"writing to screenshots/{run_dir.name}/")

    server = None
    stack_ready = True
    if any(s.served for s in chosen):
        say("starting the dev server and seeding the demo story")
        server = start_server(run_dir / "devserver.log")
        stack_ready = wait_for_port() and seed(run_dir / "seed.log")
        if not stack_ready:
            say("the stack did not come up; see devserver.log and seed.log")

    results = []
    try:
        for script in chosen:
            result = run_script(script, run_dir, stack_ready)
            results.append(result)
            say(f"{result['status']:>9}  {script.title}  "
                f"({result['seconds']:.0f} s, {len(result['shots'])} screens)")
    finally:
        if server is not None:
            stop(server)

    finished = datetime.now(UTC)
    manifest = {
        "commit": commit,
        "branch": branch,
        "started": started.isoformat(timespec="seconds"),
        "finished": finished.isoformat(timespec="seconds"),
        "seconds": round((finished - started).total_seconds(), 1),
        "base": BASE,
        "scripts": results,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (run_dir / "index.html").write_text(contact_sheet(manifest))
    (OUT / "index.html").write_text(runs_index(OUT))
    hand_over([OUT, OUT / "index.html", run_dir, *run_dir.rglob("*")])

    passed = sum(r["status"] == PASSED for r in results)
    say(f"{passed} of {len(results)} scripts passed; open "
        f"screenshots/{run_dir.name}/index.html")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
