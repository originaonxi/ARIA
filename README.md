# ARIA — Autonomous Relationship Intelligence Agent

**Built by [Aonxi](https://aonxi.com) to raise $250K pre-seed.**

$650,458 ARR | 5 months | $0 raised | 40 customers | zero sales reps.

ARIA finds investors, scores them by thesis fit, researches each one, writes personalized 3-sentence emails, verifies deliverability, and sends — all autonomously. No human writes a single email. No investor gets contacted twice.

This is not a CRM. This is not a mail merge tool. This is an autonomous agent that runs your entire fundraise.

---

## The 5 Generations of ARIA

Each generation makes the next one smarter. By Gen 5, ARIA runs a full fundraise with zero human input.

### Gen 1 — The Pipeline (current)
**Status: LIVE — sending emails now.**

What it does:
- Loads investor lists from CSV or Apollo API
- Scores every investor by thesis fit (Tier 1: operator angels from Gong/HubSpot/Salesforce, Tier 2: SMB operators, Tier 3: AI/GTM investors)
- Verifies every email via Millionverifier before sending (bouncing an investor email is fatal)
- Researches Tier 1+2 investors via SerpAPI — finds their blog posts, portfolio companies, thesis statements
- Writes 3-sentence cold emails via Claude (Michael Seibel structure: traction, why them, the ask)
- Sends via Instantly API with warming, rotation, and automatic stop-on-reply
- Classifies replies with Claude (INTERESTED / OBJECTION / NOT_NOW / REFERRAL / NEGATIVE)
- Alerts founder immediately on HOT replies
- SQLite dedup engine ensures no investor is ever contacted twice
- Daily briefing email at 7am with full pipeline stats

One command: `python aria.py run`

Stack: Claude Haiku (writing) · SerpAPI (research) · Millionverifier (verification) · Instantly (sending) · Airtable (CRM) · SQLite (dedup) · Apollo/Hunter (enrichment)

### Gen 2 — The Learner
**Target: Week 4**

What changes:
- Weekly analysis of what worked: which subject lines got opens, which hooks got replies, which investor profiles converted
- Auto-adjusts scoring weights based on reply data — if ex-Salesforce angels reply 3x more than AI fund partners, the scorer learns this
- A/B testing built into every send: two subject lines per investor, system tracks winner
- Follow-up sequencing with new data points (never repeats the first email)
- Reply-aware timing: learns which days/hours get responses, shifts send windows automatically
- Outcome feedback loop: meetings booked feed back into scorer, writer, and researcher

The system gets smarter every week it runs. Week 1 reply rate: 5%. Week 8 target: 12%.

### Gen 3 — The Researcher
**Target: Week 8**

What changes:
- Real-time monitoring of investor Twitter/X, LinkedIn, blog posts, podcast appearances
- Trigger-based outreach: investor tweets about "AI agents" → ARIA emails them within 2 hours with a personalized hook referencing that exact tweet
- Portfolio company tracking: when an investor's portfolio company raises or exits, ARIA uses that as a personalization signal
- Conference/event detection: investor speaking at SaaStr? ARIA sends a pre-conference email
- News-aware writing: Claude references specific, recent events in each email — not generic hooks
- Multi-channel orchestration: LinkedIn connection request → email 3 days later → follow-up 5 days after that

Every email feels like a human who spent 20 minutes researching. Because an AI spent 20 seconds doing the same thing.

### Gen 4 — The Negotiator
**Target: Week 12**

What changes:
- Objection handling: when an investor says "too early" or "not my thesis," ARIA generates a contextual response (not a template)
- Warm intro mapping: ARIA identifies mutual connections between founder and investor, suggests intro paths
- Term sheet analysis: when interest is confirmed, ARIA pulls comparable pre-seed deals from the last 6 months and suggests terms
- Meeting prep: before every investor call, ARIA generates a 1-page brief — their portfolio, thesis, what they care about, what to say, what to avoid
- Pipeline intelligence: ARIA tracks which investors talk to each other, avoids sending to competing funds simultaneously
- Referral chains: when investor A says "talk to investor B," ARIA automatically researches B, writes a warm email mentioning A, and queues it

ARIA doesn't just find meetings. It helps you close them.

### Gen 5 — The Autonomous Fundraiser
**Target: Week 16**

What changes:
- ARIA runs the entire fundraise end-to-end with zero human input
- Self-sourcing: no CSV imports needed — ARIA continuously discovers new investors from AngelList, Crunchbase, Twitter, podcast guest lists, conference speaker lists, and portfolio company announcements
- Self-qualifying: ARIA scores, researches, writes, sends, follows up, handles objections, books meetings — all without approval
- Self-optimizing: every metric feeds back into every decision — scoring weights, email structure, send timing, channel selection, follow-up cadence
- Founder gets one daily briefing: "3 meetings booked today. 2 term sheets in discussion. Pipeline at 47 active conversations."
- Multi-round capable: ARIA handles seed, Series A, Series B — each round learns from the last
- White-label ready: any founder can deploy ARIA for their own fundraise in under 10 minutes

The founder's job becomes: show up to meetings and close. Everything else is ARIA.

---

## Why This Works

Most founders raise money by sending the same pitch deck to 50 investors and waiting. That process takes 6-12 months, depends on warm introductions, and fails 95% of the time because investors delete generic emails in 3 seconds.

ARIA does something fundamentally different. It treats investor outreach the same way Aonxi treats customer outreach — with intelligence, signals, and personalization at scale.

The math:
- 25 emails/day × 90 days = 2,250 email touches
- 25 LinkedIn connections/day × 90 days = 2,250 LinkedIn touches
- At 8% reply rate with personalization = 360 replies
- At 25% meeting conversion = 90 meetings
- You need 3-5 yeses for a $250K pre-seed
- 90 meetings gets you there in 90 days or less

Compare that to the average founder who sends 50 emails manually, gets 3 replies, books 1 meeting, and gives up.

---

## The Numbers

```
Aonxi (the company ARIA is raising for):
  $650,458 ARR
  5 months
  $0 raised
  40 customers
  $147,626 collected
  Fully autonomous — zero sales reps

AROS (the product):
  $0.50/day vs Gong $100,000/year
  Built in 1 day — code is public
  3,016 prospects scored
  $455K pipeline

Raising: $250K pre-seed to build v2-v5
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   aria.py (CLI)                  │
│  run · status · replies · followup · briefing   │
├─────────────┬───────────────┬───────────────────┤
│  FIND       │  QUALIFY      │  EXECUTE          │
│             │               │                   │
│  Apollo API │  Scorer       │  Writer (Claude)  │
│  Hunter API │  Researcher   │  Instantly API    │
│  CSV Import │  Millionverif │  Airtable Sync    │
│             │               │  LinkedIn Prep    │
├─────────────┴───────────────┴───────────────────┤
│              SQLite (aria_db.py)                 │
│         Source of truth · Dedup engine           │
│      No investor ever contacted twice            │
└─────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/originaonxi/ARIA.git
cd ARIA

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run full pipeline
python aria.py run

# Or step by step:
python aria.py load investors.csv   # Import CSV
python aria.py verify               # Verify emails
python aria.py score                # Score by thesis fit
python aria.py research 10          # Research top 10
python aria.py write 25             # Write emails
python aria.py send                 # Push to Instantly
python aria.py replies              # Check for replies
python aria.py status               # Pipeline dashboard
python aria.py briefing             # Send daily briefing
```

---

## Files

| File | What it does |
|------|-------------|
| `aria.py` | Main CLI — 13 commands, full pipeline in one `run` |
| `aria_db.py` | SQLite dedup engine — no investor contacted twice |
| `apollo_client.py` | Apollo API — find + enrich investors automatically |
| `millionverifier.py` | Email verification — bouncing is catastrophic |
| `investor_scorer.py` | Score by thesis fit — Tier 1/2/3 with hooks |
| `investor_researcher.py` | SerpAPI — find what investors actually said |
| `investor_writer.py` | Claude writes 3-sentence emails (Seibel structure) |
| `instantly_client.py` | Instantly API — send, warm, rotate, stop-on-reply |
| `airtable_sync.py` | Visual CRM layer on top of SQLite |
| `linkedin_prep.py` | HeyReach CSV export for LinkedIn outreach |
| `reply_processor.py` | Claude classifies replies, alerts on HOT |
| `briefing.py` | Daily 7am email with full pipeline stats |
| `config.py` | Loads all secrets from .env only |

---

## Contact

**Anmol Sam** — CTO, Aonxi
- Email: origin@aonxi.com
- Calendar: [Book 20 minutes](https://calendar.app.google/gZ6V9ry93SQizZye8)
- Code (AROS): [github.com/originaonxi/aros-agent](https://github.com/originaonxi/aros-agent)

---

*ARIA is the fundraising agent. AROS is the sales agent. Together they are Aonxi — fully autonomous revenue infrastructure for the 400M businesses that can't afford enterprise GTM.*
