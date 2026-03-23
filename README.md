# ARIA — Autonomous Relationship Intelligence Agent

> An AI agent that runs your entire fundraise. Find investors, research them, write personalized emails, verify deliverability, send at scale, classify replies, book meetings. One command. Zero manual work.

**First deploy: 19 investor emails sent to General Catalyst, Bessemer, Antler, Blume VC, Kae Capital, Array Ventures, and 13 more. All personalized. All verified. All autonomous.**

```
$650,458 ARR · 5 months · $0 raised · 40 customers · zero sales reps
```

Built by [Aonxi](https://aonxi.com) to raise $250K pre-seed.

---

## What ARIA Does in One Command

```bash
python aria.py run
```

```
[1/7] FINDING INVESTORS (Apollo)...
  Found: 150 | Added: 142 | Dups: 8

[2/7] VERIFYING EMAILS (Millionverifier)...
  Valid: 119 | Invalid: 23 | Saved your domain from 23 bounces

[3/7] SCORING INVESTORS...
  Tier 1 (Operator Angels):  12   ← ex-Gong, ex-HubSpot, ex-Salesforce
  Tier 2 (SMB Operators):     8   ← know the pain personally
  Tier 3 (VC/AI Investors):  94   ← thesis match
  Skipped:                   28   ← recruiters, designers, no fit

[4/7] RESEARCHING TOP INVESTORS (SerpAPI)...
  HIGH confidence:  4   ← found their blog posts, tweets, talks
  MEDIUM confidence: 6  ← found portfolio companies
  LOW confidence:    2  ← thesis match only

[5/7] WRITING EMAILS (Claude)...
  Written: 25 personalized cold emails
  Each under 100 words. Michael Seibel 3-sentence structure.

[6/7] SENDING TO INSTANTLY...
  ✓ Sarah Chen        → sarah@chenventures.com    (Tier 1, HOT)
  ✓ Marcus Williams   → marcus@homewell.com       (Tier 2, WARM)
  ✓ Priya Kumar       → priya@aiseedfund.vc       (Tier 3, COLD)
  ... 22 more
  Total sent: 25/25

[7/7] LINKEDIN PREP...
  HeyReach CSV: data/heyreach_2026-03-23.csv (25 investors)
```

**That's it.** 25 personalized investor emails, researched, verified, and sent. Every day. Automatically.

---

## The Email ARIA Writes

ARIA doesn't send templates. Every email is unique. Here's a real one:

> **Subject:** $650K ARR, 5 months, $0 raised
>
> Sarah — we built an autonomous revenue agent that hit $650K ARR in 5 months with zero funding. Given your time at Gong, you've seen exactly what enterprise GTM costs. We replaced it for $0.50/day. 20 minutes, no deck.
>
> Anmol
> origin@aonxi.com
> calendar.app.google/gZ6V9ry93SQizZye8

3 sentences. Under 100 words. Traction first. Why them specifically. The ask. Done.

---

## The 5 Generations

Each generation makes the next smarter. By Gen 5, zero human input needed.

```
GEN 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ NOW (live, sending emails)
│
│  Find → Score → Verify → Research → Write → Send → Track
│  SQLite dedup: no investor contacted twice. Ever.
│  19 emails sent. General Catalyst, Bessemer, Antler, Blume, Kae.
│
GEN 2 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ THE LEARNER (Week 4)
│
│  System watches what works. Adjusts.
│  A/B tests every subject line. Tracks opens, replies, meetings.
│  Scoring weights auto-update from real reply data.
│  Week 1: 5% reply rate → Week 8: 12% reply rate.
│
GEN 3 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ THE RESEARCHER (Week 8)
│
│  Monitors investor Twitter, LinkedIn, blogs in real time.
│  Investor tweets about AI agents → ARIA emails them in 2 hours.
│  Conference detection. Portfolio tracking. News-aware hooks.
│  Every email feels like a human spent 20 minutes researching.
│
GEN 4 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ THE NEGOTIATOR (Week 12)
│
│  Handles objections autonomously. Maps warm intro paths.
│  Generates meeting prep briefs. Tracks competing funds.
│  When investor A says "talk to B" → ARIA researches B,
│  writes warm email mentioning A, queues it. Automatically.
│
GEN 5 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ AUTONOMOUS (Week 16)
│
│  Zero human input. Self-sourcing. Self-qualifying.
│  Self-optimizing. Multi-round capable (Seed → A → B).
│  Founder gets one briefing: "3 meetings today. 2 term sheets."
│  The founder's only job: show up and close.
```

---

## Why This Exists

Most founders raise money like this:
1. Write a pitch deck
2. Send it to 50 investors they found on LinkedIn
3. Wait 6-12 months
4. Get 3 replies, 1 meeting, 0 checks
5. Give up or try again

ARIA does this:
1. **Find** 5,000 investors automatically (Apollo API)
2. **Score** each one — ex-Gong VP who angel invests = 10/10, random LinkedIn connection = 2/10, skip
3. **Verify** every email (Millionverifier) — bouncing an investor email is fatal
4. **Research** each one (SerpAPI) — find what they actually said last month, not their job title
5. **Write** a 3-sentence email (Claude) — traction, why them, the ask
6. **Send** at 9am in their timezone (Instantly) — stop on reply, never send twice
7. **Track** every reply (Claude classification) — INTERESTED, OBJECTION, NOT_NOW, REFERRAL
8. **Learn** what worked — update scoring, writing, timing every week

The math:
```
25 emails/day × 90 days           = 2,250 touches
8% reply rate (personalized)      = 180 replies
25% meeting rate                  = 45 meetings
You need 3-5 yeses for $250K      = Done in 90 days
```

Average founder: 50 manual emails → 3 replies → 1 meeting → gives up.

---

## Architecture

```
                         ┌──────────────────┐
                         │    aria.py CLI    │
                         │  One command to   │
                         │  run everything   │
                         └────────┬─────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
    ┌────▼────┐            ┌──────▼──────┐          ┌──────▼──────┐
    │  FIND   │            │  QUALIFY    │          │  EXECUTE    │
    │         │            │            │          │             │
    │ Apollo  │            │ Scorer     │          │ Writer      │
    │ Hunter  │            │ Researcher │          │ (Claude)    │
    │ CSV     │            │ Verifier   │          │ Instantly   │
    └────┬────┘            └──────┬──────┘          │ Airtable   │
         │                        │                │ LinkedIn   │
         │                        │                └──────┬──────┘
         │                        │                       │
         └────────────────────────┼───────────────────────┘
                                  │
                         ┌────────▼─────────┐
                         │   SQLite (dedup)  │
                         │                   │
                         │ No investor ever  │
                         │ contacted twice.  │
                         └───────────────────┘
```

---

## Quick Start

```bash
git clone https://github.com/originaonxi/ARIA.git
cd ARIA
pip install -r requirements.txt
cp .env.example .env
# Add your API keys to .env
python aria.py run
```

## All Commands

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
| `aria write N` | Write emails for top N with Claude |
| `aria send` | Push batch to Instantly |
| `aria send --dry-run` | Preview what would be sent |
| `aria stats` | Reply rates by tier, projections, analytics |

---

## Stack

| Tool | What | Cost |
|------|------|------|
| Claude Haiku | Writes every email | ~$0.02/email |
| SerpAPI | Researches each investor | ~$0.01/search |
| Millionverifier | Verifies deliverability | ~$0.001/email |
| Instantly | Sends, warms, rotates, tracks | ~$30/mo |
| Apollo | Finds investors automatically | Free tier works |
| Hunter | Email enrichment fallback | Free tier works |
| Airtable | Visual CRM dashboard | Free tier works |
| SQLite | Dedup + source of truth | Free forever |

**Total cost to run ARIA: ~$2/day.** Compare to a fundraising advisor at $5,000/month.

---

## The Dedup Engine

This is the most important piece. Every investor who has ever been contacted lives in SQLite forever. Import a new Apollo list next month with the same names? ARIA skips them automatically.

```python
def is_safe_to_contact(investor_id) -> tuple:
    # Returns (False, reason) if ANY of:
    # - status not in NEW/QUEUED/VERIFIED
    # - email_count >= 3
    # - email_valid = 0 (bounced)
    # - replied = 1 (already replied)
    # - meeting_booked = 1
    # - last_contacted within 5 days
    # Returns (True, "safe") otherwise
```

Most founders accidentally email the same investor 4 times across different tools and lists. ARIA makes that impossible.

---

## Files

```
aria.py                 Main CLI — 13 commands, full pipeline
aria_db.py              SQLite dedup engine — source of truth
apollo_client.py        Apollo API — find + enrich investors
millionverifier.py      Email verification before any send
investor_scorer.py      Score by thesis fit (Tier 1/2/3)
investor_researcher.py  SerpAPI — find what investors said
investor_writer.py      Claude writes 3-sentence emails
instantly_client.py     Instantly API — send + warm + track
airtable_sync.py        Visual CRM on top of SQLite
linkedin_prep.py        HeyReach CSV for LinkedIn outreach
reply_processor.py      Claude classifies replies + HOT alerts
briefing.py             Daily 7am pipeline email
config.py               Loads secrets from .env only
```

---

## Real Numbers

```
AONXI (the company):
  $650,458 ARR
  5 months from zero
  $0 raised
  40 customers
  $147,626 collected
  Zero sales reps — fully autonomous

AROS (the product ARIA is raising for):
  $0.50/day vs Gong $100,000/year
  Built in 1 day
  3,016 prospects scored
  $455K pipeline
  Code: github.com/originaonxi/aros-agent

ARIA (this repo):
  19 investor emails sent on first deploy
  4 bounces caught before sending (saved domain reputation)
  Raising: $250K pre-seed
```

---

## Contact

**Anmol Sam** — CTO, Aonxi

origin@aonxi.com · [Book 20 minutes](https://calendar.app.google/gZ6V9ry93SQizZye8) · [AROS source code](https://github.com/originaonxi/aros-agent)

---

*ARIA raises the money. AROS makes the money. Together they are Aonxi — fully autonomous revenue infrastructure for the 400M businesses that can't afford enterprise GTM.*
