"""
parth — command-line ops tool for whoever is running the pilot day to day.

Talks to a running Parth server over HTTP (same way any external client
would — see server/start.sh for how the server itself is run), not by
importing server internals directly.

Usage:
    export PARTH_SERVER_URL=http://localhost:8000
    export PARTH_API_KEY=...        # only if the server sets PARTH_API_KEY
    python cli.py funnel
    python cli.py learner show <id>
    python cli.py survey link --school my-school
    python cli.py notify send --to teacher@example.com --channel email --template pilot_welcome --param name=Asha --param school="DAV Public School"
"""
import os
from typing import Optional
from urllib.parse import quote

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Parth pilot ops CLI")
survey_app = typer.Typer(help="Manage trackable teacher-form survey links")
notify_app = typer.Typer(help="Send pilot comms over email / SMS / WhatsApp")
app.add_typer(survey_app, name="survey")
app.add_typer(notify_app, name="notify")

console = Console()


def _client() -> httpx.Client:
    base_url = os.getenv("PARTH_SERVER_URL", "http://localhost:8000")
    api_key = os.getenv("PARTH_API_KEY", "")
    headers = {"X-Parth-Key": api_key} if api_key else {}
    return httpx.Client(base_url=base_url, headers=headers, timeout=15.0)


def _fail(resp: httpx.Response) -> None:
    console.print(f"[bold red]Error {resp.status_code}[/bold red]: {resp.text}")
    raise typer.Exit(code=1)


@app.command()
def funnel(school: Optional[str] = typer.Option(None, "--school", help="Filter to one school_id")):
    """Registration -> onboarding -> portrait -> first-chat counts."""
    with _client() as client:
        params = {"school_id": school} if school else {}
        resp = client.get("/pilot/funnel", params=params)
        if resp.is_error:
            _fail(resp)
        data = resp.json()

    table = Table(title=f"Pilot funnel — {data['school_id']}")
    table.add_column("Stage")
    table.add_column("Count", justify="right")
    table.add_row("Registered", str(data["registered"]))
    table.add_row("Onboarding complete", str(data["onboarding_complete"]))
    table.add_row("Portrait revealed", str(data["portrait_revealed"]))
    table.add_row("First chat", str(data["first_chat"]))
    console.print(table)


learner_app = typer.Typer(help="Look up a single learner")
app.add_typer(learner_app, name="learner")


@learner_app.command("show")
def learner_show(learner_id: str):
    """Identity + pilot gate metrics for one learner."""
    with _client() as client:
        identity = client.get(f"/learner/{learner_id}")
        gates = client.get(f"/metrics/pilot/{learner_id}")
        if identity.is_error:
            _fail(identity)

    body = [f"[bold]{k}[/bold]: {v}" for k, v in identity.json().items()]
    if not gates.is_error:
        body.append("")
        body.append("[bold]pilot gates[/bold]")
        for gate, val in gates.json().get("gates", {}).items():
            body.append(f"  {gate}: {val}")
    console.print(Panel("\n".join(body), title=f"Learner {learner_id}"))


@survey_app.command("link")
def survey_link(
    school: str = typer.Option(..., "--school", help="School / cohort id"),
    teacher_phone: Optional[str] = typer.Option(None, "--teacher-phone"),
    hours: int = typer.Option(72, "--hours", help="Link validity in hours"),
):
    """Issue a tokenized, trackable teacher-form link."""
    with _client() as client:
        resp = client.post("/survey/link", json={
            "school_id": school,
            "teacher_phone": teacher_phone,
            "expires_in_hours": hours,
        })
        if resp.is_error:
            _fail(resp)
        data = resp.json()

    server_url = os.getenv("PARTH_SERVER_URL", "http://localhost:8000")
    full_url = f"{server_url}{data['url']}"
    share_text = f"Please fill in a quick learning portrait for your student: {full_url}"
    wa_link = f"https://wa.me/?text={quote(share_text)}"
    mailto_link = f"mailto:?subject={quote('Parth student portrait')}&body={quote(share_text)}"

    console.print(Panel(
        f"[bold]URL[/bold]      {full_url}\n"
        f"[bold]WhatsApp[/bold] {wa_link}\n"
        f"[bold]Email[/bold]    {mailto_link}\n"
        f"[bold]Expires[/bold]  {data['expires_at']}",
        title=f"Survey link — {school}",
    ))


@notify_app.command("templates")
def notify_templates():
    """List available notification templates."""
    with _client() as client:
        resp = client.get("/notify/templates")
        if resp.is_error:
            _fail(resp)
        data = resp.json()

    table = Table(title="Notify templates")
    table.add_column("Name")
    table.add_column("Subject")
    table.add_column("Body")
    for name, t in data.items():
        table.add_row(name, t["subject"], t["body"])
    console.print(table)


@notify_app.command("send")
def notify_send(
    to: str = typer.Option(..., "--to"),
    channel: str = typer.Option(..., "--channel", help="email | sms | whatsapp"),
    template: str = typer.Option(..., "--template"),
    param: list[str] = typer.Option([], "--param", help="key=value, repeatable"),
):
    """Send a templated reminder over one channel."""
    params = {}
    for p in param:
        if "=" not in p:
            console.print(f"[bold red]--param must be key=value, got: {p}[/bold red]")
            raise typer.Exit(code=1)
        k, v = p.split("=", 1)
        params[k] = v

    with _client() as client:
        resp = client.post("/notify/send", json={
            "to": to, "channel": channel, "template": template, "params": params,
        })
        if resp.is_error:
            _fail(resp)

    console.print(f"[bold green]Sent[/bold green] via {channel} to {to}")


if __name__ == "__main__":
    app()
