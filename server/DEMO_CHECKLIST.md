# Tuition-center demo — pre-flight checklist

Written 2026-08-11 for the IIT/NEET tuition-center visit. Do this the
night before, not the morning of.

## 1. Switch the tutor backend to Anthropic (recommended, not done for you)

Right now `TUTOR_BACKEND=auto` in `.env`, and no `ANTHROPIC_API_KEY` is
set — so the server is running on local Ollama (`gemma3:12b`). That means
**the demo currently depends on your laptop's Ollama process staying up
and responsive**, on top of everything else. If you have an Anthropic
API key:

1. Add `ANTHROPIC_API_KEY=sk-...` to `server/.env`.
2. Restart: `./restart-mac.sh`.
3. Confirm: `curl http://localhost:8000/health` should show
   `"tutor_backend":"anthropic"`.

This removes one dependency (Ollama) and — based on testing today —
should meaningfully improve the quality and reliability of the new
"tell Parth something you noticed" feature specifically. The local
Ollama model (gemma3:12b) produced good results on the cat/dog example
but a noticeably weaker one (a shaky "biofilm" biology claim, a stretched
philosophy angle) on a second, unrelated test observation. Claude is
very likely to do better here, but this wasn't verified today — no key
was available to test against.

If you don't have a key or don't want to switch: the app still works on
Ollama, but you must keep Ollama running the whole day (`ollama serve`)
in addition to the Parth server and Postgres.

## 2. Connectivity — rehearse this, don't discover it on-site

Tailscale is installed on this machine but **not currently running**
(`tailscale status` fails). Before the venue:

1. `tailscale up` and confirm you're logged into your tailnet.
2. `tailscale ip -4` — note the IP.
3. On your phone, install Tailscale, log into the same account, confirm
   it shows connected.
4. In the Parth app's Settings, enter `http://<tailscale-ip>:8000` as the
   server URL and confirm a test message goes through.

Do this rehearsal from a *different* network than your home wifi (a
coffee shop, mobile hotspot) to actually prove it works across networks,
not just on your home LAN where a plain IP would work anyway.

**Backup plan if the venue's wifi has client isolation** (common at
institutions — devices on the same wifi can't see each other): use your
phone as a mobile hotspot for the laptop instead of the venue's wifi.
Tailscale then still works over the hotspot's connection, or — simplest —
phone and laptop are both on the same hotspot, so a plain LAN IP works too.

## 3. Before you leave

- [ ] `ANTHROPIC_API_KEY` added (§1), or you're committed to running
      Ollama all day
- [ ] Tailscale rehearsed on a foreign network (§2), IP written down
      somewhere you can find it without wifi
- [ ] `sudo pmset -c sleep 0` run (already in `deploy.sh` — confirm it
      actually took: `pmset -g` should show `sleep 0`) so the laptop
      doesn't sleep mid-demo
- [ ] Postgres running and reachable: `pg_isready`
- [ ] A test learner already past onboarding/consent on the demo phone,
      so you're not doing the consent flow live in front of the tuition
      center's staff
- [ ] Run the actual cat/dog observation (or your own fresh example)
      through the app on the demo phone at least once, end to end, the
      night before — not just via curl

## 4. What's genuinely new since the last time you looked at this app

- A "🧭 Tell Parth something you noticed" button in the chat input bar.
  A student describes something real, and the server finds 3-5 genuinely
  different academic angles on it (biology/physics/chemistry/philosophy/
  economics — whichever actually fit, not padded to a fixed count), each
  phrased as a question, never a lecture. The strongest one becomes
  Parth's next message; the rest are remembered and can resurface
  naturally in later conversation (same mechanism Parth already used for
  "open loops" — nothing new architecturally, just a new way to seed one).
- Grade 11-12 students now get a different register from Parth: no
  "Shabash!", no exclamation marks, leads with a question before
  explaining. Confirmed via `grade` in the chat request — the demo
  learner should be set to grade 11 or 12 for this to apply.
- Two "AI mentor" strings were softened in the app's copy (the chat
  welcome message and the home screen banner). This is a tone change,
  not a concealment — if a student directly asks whether Parth is an AI,
  it's instructed to say so honestly. Not touched: the client-side
  Anthropic-fallback prompt used only when no server is configured at
  all (out of scope for tonight, and not on the demo's critical path
  since the observation feature requires the local server regardless).
