# ARIA — Autonomous Relationship Intelligence Agent

> One of two permanent intelligence cores at Aonxi.
> ARIA finds capital. AROS finds revenue.
> Both learn from the same brain. Both compound forever.

[![Status](https://img.shields.io/badge/Status-Production-green?style=for-the-badge)]()
[![PKM](https://img.shields.io/badge/PKM-10_Defense_Modes-purple?style=for-the-badge)](https://github.com/originaonxi/pkm-analyzer)
[![Brain](https://img.shields.io/badge/Brain-Airtable-blue?style=for-the-badge)]()
[![Raising](https://img.shields.io/badge/Raising-$250K_pre--seed-orange?style=for-the-badge)]()

**[Read the full Aonxi vision](./VISION.md)**

---

## What ARIA does

ARIA finds investors, scores them by thesis fit,
verifies every email, profiles their psychological
defense mode, writes a message calibrated to bypass
that defense, creates the campaign, and sends it.

Autonomously. The same system that finds revenue now finds capital.

**First deployment — March 2026:**

```
Investors contacted:  General Catalyst, Bessemer, Antler,
                      Blume VC, Kae Capital + 14 more
Emails sent:          19
Bounces caught:       4 (before sending — domain reputation protected)
Raising:              $250K pre-seed
Product:              $199K collected, $0 raised, 40 customers
```

The product being used to raise money is being used to raise the money.
Every investor who receives an ARIA email is watching it work before they reply.

---

## Why VCs are the hardest defense mode to bypass

VCs are **MOTIVE_INFERENCE** — awareness score 9/10.

They spend their careers evaluating pitches. They have read 10,000 cold emails. They decoded your intent before you finished the subject line.

Most founder emails look like this:

> Hi Sarah — I'm really excited to share what we're building at Aonxi. I think there's a great opportunity here and would love to connect for a quick call.

Every word triggers a defense. *Excited* — detected. *Great opportunity* — detected. *Quick call* — detected. Email deleted before the second paragraph.

**ARIA sends emails that look like this:**

> $199K collected. $8K peak day. $0.50/day to run. Zero sales reps. Code is public. You backed [company] — autonomous GTM at the SMB layer. This is that, built and verified. 20 minutes. No deck.

No "I". No pitch language. No excitement. Data, a specific signal, a specific ask.

That is **PURE_DATA bypass** for **MOTIVE_INFERENCE defense**.

---

## The PKM layer in investor outreach

Same 10 defense modes. Different population distribution.
[PKM Analyzer](https://github.com/originaonxi/pkm-analyzer) — [try it live](https://originaonxi.github.io/pkm-analyzer/) (free, no key needed).

| Investor type | Defense mode | Bypass | What changes |
|--------------|-------------|--------|-------------|
| VC partner (ex-GTM) | MOTIVE_INFERENCE | PURE_DATA | Opens with a number, never "I'm excited to" |
| Operator angel | TACTIC_RECOGNITION | SIGNAL_HOOK | References their specific portfolio company |
| Technical investor | SOCIAL_PROOF_SKEPTICISM | CREDIBILITY_FIRST | Verifiable numbers only, no "trusted by" |
| First-time angel | AUTHORITY_DEFERENCE | PEER_PROOF | Names other angels who committed |
| Busy SMB operator | OVERLOAD_AVOIDANCE | ULTRA_SHORT | 60-word hard cap, specific calendar slot |

ARIA detects which one. ARIA writes for that one. Every time.

All defense profiles are cached in Airtable — shared across ARIA and AROS. A prospect analyzed by one agent is instantly available to the other.

Based on [Friestad & Wright (1994)](https://doi.org/10.1086/209380) — 30 years of persuasion psychology.

---

## The brain — Airtable

Every investor ARIA contacts is recorded.

- Which thesis keywords converted
- Which defense mode each investor was running
- Which bypass strategy got the reply
- Which time of day a specific fund partner opens emails
- Which portfolio signal triggered the conversation

This pattern library compounds every raise. The next founder who uses ARIA gets the benefit of every raise that came before them.

---

## Architecture

```
aria.py               CLI entry — 13 commands, one pipeline
aria_db.py            SQLite dedup engine (source of truth)
apollo_client.py      Investor finding + enrichment
millionverifier.py    Email verification before send
investor_scorer.py    Thesis fit scoring (Tier 1/2/3)
investor_researcher.py SerpAPI research
investor_writer.py    Claude Haiku email generation (PKM applied)
instantly_client.py   Campaign creation + send + tracking
airtable_sync.py      Visual CRM dashboard sync
linkedin_prep.py      HeyReach CSV for LinkedIn outreach
reply_processor.py    Claude reply classification + HOT alerts
briefing.py           Daily 7am pipeline email
```

**One command:**
```bash
python aria.py run
```

Find → Score → Verify → Research → Profile → Write → Send → Track → Learn.

**Stack:** Claude Haiku / Apollo / Millionverifier / SerpAPI / Instantly / Airtable / SQLite

---

## The 5-generation roadmap

| Gen | Name | Status | What it adds |
|-----|------|--------|-------------|
| 1 | Pipeline | **LIVE** | Find → Score → Verify → Research → Profile → Write → Send |
| 2 | Learner | Week 4 | A/B testing, auto-adjust scoring from reply data |
| 3 | Researcher | Week 8 | Real-time portfolio moves, trigger-based outreach |
| 4 | Negotiator | Week 12 | Objection handling, warm intro path mapping |
| 5 | Autonomous | Week 16 | Zero human input, self-sourcing, self-qualifying |

---

## All commands

| Command | What it does |
|---------|-------------|
| `aria run` | Full pipeline: find → verify → score → research → write → send |
| `aria run --auto` | Same but skip preview — send all automatically |
| `aria status` | Pipeline dashboard |
| `aria replies` | Check Instantly for replies, classify, alert on HOT |
| `aria followup` | Day 5-8 follow-ups for non-responders |
| `aria linkedin` | Generate HeyReach CSV for LinkedIn outreach |
| `aria briefing` | Send daily pipeline email |
| `aria load FILE` | Import CSV manually |
| `aria verify` | Run Millionverifier on unverified emails |
| `aria score` | Score all unscored investors |
| `aria research N` | Research top N investors via SerpAPI |
| `aria write` | Write emails for top scored investors |
| `aria sync` | Sync to Airtable CRM dashboard |

---

## Run locally

```bash
git clone https://github.com/originaonxi/ARIA
cd ARIA
pip install -r requirements.txt
cp .env.example .env
# Add your keys to .env
python aria.py run
```

---

## Related

| Repo | What it does |
|------|-------------|
| [AROS](https://github.com/originaonxi/aros-agent) | Finds revenue — the other intelligence core |
| [PKM Analyzer](https://github.com/originaonxi/pkm-analyzer) | Defense profiling — [try it live](https://originaonxi.github.io/pkm-analyzer/) |
| [VISION.md](./VISION.md) | The full Aonxi vision — AGI revenue layer for 400M businesses |

---

**Built by [Anmol Sam](https://github.com/originaonxi)** — origin@aonxi.com / [originaonxi.github.io](https://originaonxi.github.io) / [aonxi.app](https://aonxi.app)
