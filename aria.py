"""
ARIA v1 — Autonomous Relationship Intelligence Agent
Main CLI for investor outreach.

Commands:
  aria run          Full pipeline: find → verify → score → research → write → send
  aria run --auto   Same but skip email preview (send all automatically)
  aria status       Full pipeline dashboard
  aria replies      Check Instantly for new replies, classify, alert on HOT
  aria followup     Process day 5-8 follow-ups
  aria linkedin     Generate HeyReach CSV for today
  aria briefing     Send daily briefing now
  aria load PATH    Manual CSV import fallback
  aria stats        Detailed analytics
  aria verify       Run Millionverifier on unverified emails
  aria score        Score all unscored investors
  aria research N   Research top N Tier 1+2 investors
  aria write N      Write emails for top N scored investors
  aria send         Push today's batch to Instantly
"""

import argparse
import sys
import os
from datetime import datetime

import aria_db as db
from investor_scorer import score_investor
from investor_researcher import research_investor
from investor_writer import write_cold_email, write_linkedin_message, write_followup
from millionverifier import verify_batch
from instantly_client import get_or_create_campaign, add_lead, get_campaign_stats
from airtable_sync import sync_investor
from apollo_client import daily_prospect_harvest
from linkedin_prep import prep_heyreach_csv
from reply_processor import process_replies
from briefing import send_daily_briefing
from config import DATA_DIR, INSTANTLY_CAMPAIGN_ID


def cmd_run(auto: bool = False, per_query: int = 50, send_limit: int = 25):
    """Full pipeline: find → verify → score → research → write → send."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ARIA RUN — Full Pipeline")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Step 1: Apollo harvest
    print("\n[1/7] FINDING INVESTORS (Apollo)...")
    harvest_stats = daily_prospect_harvest(per_query=per_query)
    print(f"  Found: {harvest_stats['found']} | Added: {harvest_stats['added']} | Dups: {harvest_stats['duplicates']}")

    # Step 2: Verify emails
    print("\n[2/7] VERIFYING EMAILS (Millionverifier)...")
    verify_stats = verify_batch(limit=100)
    print(f"  Valid: {verify_stats['valid']} | Invalid: {verify_stats['invalid']} | Unknown: {verify_stats['unknown']}")

    # Step 3: Score
    print("\n[3/7] SCORING INVESTORS...")
    unscored = db.get_unscored(limit=500)
    tier_counts = {1: 0, 2: 0, 3: 0, 0: 0}
    for inv in unscored:
        scored = score_investor(inv)
        if scored["go"]:
            db.mark_scored(
                inv["id"], scored["tier"], scored["score"],
                scored["investor_type"], scored["channel"],
                scored["personalization_hook"],
            )
            tier_counts[scored["tier"]] = tier_counts.get(scored["tier"], 0) + 1
        else:
            db.update_investor(inv["id"], {"tier": 0, "score": scored.get("score", 0), "status": "SKIPPED"})
            tier_counts[0] += 1
    print(f"  Scored: {len(unscored)} | T1: {tier_counts[1]} | T2: {tier_counts[2]} | T3: {tier_counts[3]} | Skip: {tier_counts[0]}")

    # Step 4: Research Tier 1+2
    print("\n[4/7] RESEARCHING TOP INVESTORS (SerpAPI)...")
    unresearched = db.get_unresearched(limit=10)
    for inv in unresearched:
        result = research_investor(inv)
        db.mark_researched(
            inv["id"],
            result.get("research_hook") or "",
            result.get("research_confidence", "LOW"),
            result.get("recent_activity") or "",
            result.get("portfolio_signal") or "",
        )
    print(f"  Researched: {len(unresearched)} investors")

    # Step 5: Write emails
    print("\n[5/7] WRITING EMAILS (Claude)...")
    unwritten = db.get_unwritten(limit=send_limit)
    written = 0
    for inv in unwritten:
        try:
            email = write_cold_email(inv)
            li_msg = None
            if inv.get("channel") in ("BOTH", "LINKEDIN"):
                li_msg = write_linkedin_message(inv)

            db.mark_written(
                inv["id"],
                email["subject_a"], email["subject_b"],
                email["body"], li_msg,
                email["predicted_reply_tier"],
            )
            written += 1
        except Exception as e:
            print(f"  [write] Error for {inv.get('first_name', '?')}: {e}")
    print(f"  Written: {written} emails")

    # Step 6: Preview and send
    print("\n[6/7] SENDING TO INSTANTLY...")
    ready = db.get_ready_to_contact(limit=send_limit)

    if not ready:
        print("  No investors ready to send.")
    else:
        campaign_id = INSTANTLY_CAMPAIGN_ID or get_or_create_campaign()
        if not campaign_id:
            print("  [send] Could not get/create campaign — skipping send")
        else:
            sent = 0
            for i, inv in enumerate(ready, 1):
                if not auto:
                    # Show preview
                    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    tier_label = {1: "HOT", 2: "WARM", 3: "COLD"}.get(inv["tier"], "?")
                    print(f"INVESTOR [{i}/{len(ready)}] | TIER {inv['tier']} | {tier_label}")
                    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    print(f"{inv['first_name']} {inv['last_name']} | {inv['company']}")
                    print(f"Score: {inv['score']}/10 | Type: {inv['investor_type']}")
                    if inv.get("research_hook"):
                        print(f"Research: \"{inv['research_hook'][:80]}\" ({inv.get('research_confidence', 'LOW')})")
                    print(f"\nSUBJECT A: {inv['subject_a']}")
                    print(f"SUBJECT B: {inv['subject_b']}")
                    print(f"──────────────────────────────────")
                    print(inv["email_body"])
                    print(f"──────────────────────────────────")

                    choice = input("Send? (y/n/s=stop/e=edit subject): ").strip().lower()
                    if choice == "s":
                        print("  Stopping sends.")
                        break
                    elif choice == "n":
                        continue
                    elif choice == "e":
                        new_subj = input("  New subject: ").strip()
                        if new_subj:
                            inv["subject_a"] = new_subj
                            db.update_investor(inv["id"], {"subject_a": new_subj})

                # Send to Instantly
                lead_id = add_lead(campaign_id, inv)
                if lead_id:
                    db.mark_contacted(inv["id"], "EMAIL", inv["subject_a"], inv["email_body"], lead_id)
                    # Sync to Airtable
                    inv_fresh = db.get_investor(inv["id"])
                    airtable_id = sync_investor(inv_fresh)
                    if airtable_id:
                        db.update_investor(inv["id"], {"airtable_id": airtable_id})
                    sent += 1
                    if not auto:
                        print(f"  ✓ Sent to {inv['email']}")
                else:
                    if not auto:
                        print(f"  ✗ Failed for {inv['email']}")

            print(f"\n  Total sent: {sent}/{len(ready)}")

    # Step 7: LinkedIn prep
    print("\n[7/7] LINKEDIN PREP...")
    li_path = prep_heyreach_csv(limit=25)
    if li_path:
        print(f"  HeyReach CSV: {li_path}")

    # Final stats
    print("\n")
    cmd_status()


def cmd_status():
    """Full pipeline dashboard."""
    stats = db.get_stats()
    today = datetime.now().strftime("%B %d, %Y")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"ARIA STATUS — {today}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n  Total investors: {stats['total']}")
    print(f"  Verified emails: {stats['verified']}")
    print(f"  Tier 1 (Operator Angels):  {stats['by_tier'].get(1, 0)}")
    print(f"  Tier 2 (SMB Operators):    {stats['by_tier'].get(2, 0)}")
    print(f"  Tier 3 (AI/GTM Investors): {stats['by_tier'].get(3, 0)}")
    print(f"\n  Pipeline:")
    for status, count in stats["by_status"].items():
        if count > 0:
            print(f"    {status:12s}: {count}")
    print(f"\n  Contacted: {stats['contacted']}")
    print(f"  Replied:   {stats['replied']} ({stats['reply_rate']:.1f}%)")
    print(f"  Meetings:  {stats['meetings']} ({stats['meeting_rate']:.1f}%)")
    print(f"\n  Ready to send today: {stats['ready_today']}")
    print(f"  Follow-ups due:      {stats['followups_due']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_load(csv_path: str):
    """Load CSV into database."""
    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    print(f"Loading {csv_path}...")
    stats = db.load_from_csv(csv_path)
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("CSV IMPORT COMPLETE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Added:      {stats['added']}")
    print(f"  Duplicates: {stats['duplicates']}")
    print(f"  Skipped:    {stats['skipped']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_verify():
    """Run Millionverifier on unverified emails."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("EMAIL VERIFICATION")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    stats = verify_batch(limit=500)
    print(f"\n  Valid:   {stats['valid']}")
    print(f"  Invalid: {stats['invalid']}")
    print(f"  Unknown: {stats['unknown']}")
    print(f"  Checked: {stats['total_checked']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_score():
    """Score all unscored investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("SCORING INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    unscored = db.get_unscored(limit=5000)
    tier_counts = {1: 0, 2: 0, 3: 0, 0: 0}

    for inv in unscored:
        scored = score_investor(inv)
        if scored["go"]:
            db.mark_scored(
                inv["id"], scored["tier"], scored["score"],
                scored["investor_type"], scored["channel"],
                scored["personalization_hook"],
            )
        else:
            db.update_investor(inv["id"], {"tier": 0, "score": scored.get("score", 0), "status": "SKIPPED"})
        tier_counts[scored.get("tier", 0)] = tier_counts.get(scored.get("tier", 0), 0) + 1

    print(f"  Scored: {len(unscored)}")
    print(f"  Tier 1 (Operator Angels):  {tier_counts.get(1, 0)}")
    print(f"  Tier 2 (SMB Operators):    {tier_counts.get(2, 0)}")
    print(f"  Tier 3 (AI/GTM Investors): {tier_counts.get(3, 0)}")
    print(f"  Skipped:                   {tier_counts.get(0, 0)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_research(n: int):
    """Research top N Tier 1+2 investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"RESEARCHING TOP {n} INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    unresearched = db.get_unresearched(limit=n)
    high = medium = low = 0

    for inv in unresearched:
        result = research_investor(inv)
        conf = result.get("research_confidence", "LOW")
        db.mark_researched(
            inv["id"],
            result.get("research_hook") or "",
            conf,
            result.get("recent_activity") or "",
            result.get("portfolio_signal") or "",
        )
        if conf == "HIGH":
            high += 1
        elif conf == "MEDIUM":
            medium += 1
        else:
            low += 1

    print(f"\n  Researched: {len(unresearched)}")
    print(f"  HIGH confidence:   {high}")
    print(f"  MEDIUM confidence: {medium}")
    print(f"  LOW confidence:    {low}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_write(n: int):
    """Write emails for top N scored investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"WRITING EMAILS FOR TOP {n}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    unwritten = db.get_unwritten(limit=n)
    written = 0

    for inv in unwritten:
        name = f"{inv.get('first_name', '')} {inv.get('last_name', '')}"
        print(f"\n  Writing for {name}...")
        try:
            email = write_cold_email(inv)
            li_msg = None
            if inv.get("channel") in ("BOTH", "LINKEDIN"):
                li_msg = write_linkedin_message(inv)

            # Show preview
            print(f"  Subject A: {email['subject_a']}")
            print(f"  Subject B: {email['subject_b']}")
            print(f"  ──────────────────────────────────")
            print(f"  {email['body']}")
            print(f"  ──────────────────────────────────")

            choice = input("  Save? (y/n): ").strip().lower()
            if choice == "y":
                db.mark_written(
                    inv["id"],
                    email["subject_a"], email["subject_b"],
                    email["body"], li_msg,
                    email["predicted_reply_tier"],
                )
                written += 1
                print(f"  ✓ Saved")
            else:
                print(f"  Skipped")
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\n  Written: {written}/{len(unwritten)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_send(dry_run: bool = False):
    """Push today's batch to Instantly."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if dry_run:
        print("SEND — DRY RUN (nothing will be sent)")
    else:
        print("SENDING TO INSTANTLY")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    ready = db.get_ready_to_contact(limit=25)
    if not ready:
        print("  No investors ready to send.")
        return

    print(f"  {len(ready)} investors ready\n")

    if dry_run:
        for i, inv in enumerate(ready, 1):
            tier_label = {1: "HOT", 2: "WARM", 3: "COLD"}.get(inv["tier"], "?")
            print(f"  [{i:2d}] {inv['first_name']:10s} {inv['last_name']:12s} | {inv['company']:20s} | T{inv['tier']} {tier_label} | {inv['score']}/10")
            print(f"       Subject: {inv.get('subject_a', 'N/A')}")
        print(f"\n  Would send {len(ready)} emails. Run without --dry-run to send.")
        return

    campaign_id = INSTANTLY_CAMPAIGN_ID or get_or_create_campaign()
    if not campaign_id:
        print("  Could not get/create campaign.")
        return

    sent = 0
    for inv in ready:
        lead_id = add_lead(campaign_id, inv)
        if lead_id:
            db.mark_contacted(inv["id"], "EMAIL", inv["subject_a"], inv["email_body"], lead_id)
            inv_fresh = db.get_investor(inv["id"])
            airtable_id = sync_investor(inv_fresh)
            if airtable_id:
                db.update_investor(inv["id"], {"airtable_id": airtable_id})
            sent += 1
            print(f"  ✓ {inv['email']}")
        else:
            print(f"  ✗ {inv['email']}")

    print(f"\n  Sent: {sent}/{len(ready)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_followup():
    """Process follow-ups for day 5-8 no-reply investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("FOLLOW-UPS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    candidates = db.get_followup_candidates()

    if not candidates:
        print("  No follow-up candidates right now.")
        return

    print(f"  {len(candidates)} candidates\n")
    campaign_id = INSTANTLY_CAMPAIGN_ID or get_or_create_campaign()
    sent = 0

    for inv in candidates:
        name = f"{inv['first_name']} {inv['last_name']}"
        print(f"  {name} | {inv['company']} | T{inv['tier']}")

        try:
            fu = write_followup(inv, followup_num=1)
            print(f"    Subject: {fu['subject']}")
            print(f"    {fu['body'][:100]}...")

            choice = input("    Send follow-up? (y/n): ").strip().lower()
            if choice == "y" and campaign_id:
                inv["subject_a"] = fu["subject"]
                inv["email_body"] = fu["body"]
                lead_id = add_lead(campaign_id, inv)
                if lead_id:
                    db.mark_contacted(inv["id"], "EMAIL", fu["subject"], fu["body"], lead_id)
                    sent += 1
                    print(f"    ✓ Sent")
        except Exception as e:
            print(f"    Error: {e}")

    print(f"\n  Follow-ups sent: {sent}/{len(candidates)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_replies():
    """Check Instantly for new replies."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("CHECKING REPLIES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    stats = process_replies(INSTANTLY_CAMPAIGN_ID)
    print(f"\n  Processed:  {stats['processed']}")
    print(f"  Interested: {stats['interested']}")
    print(f"  Objections: {stats['objections']}")
    print(f"  Other:      {stats['other']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_linkedin():
    """Generate HeyReach CSV."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("LINKEDIN PREP")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    path = prep_heyreach_csv(limit=25)
    if path:
        print(f"  Output: {path}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_stats():
    """Detailed analytics."""
    stats = db.get_stats()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ARIA ANALYTICS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Reply rate by tier
    conn = db._connect()
    c = conn.cursor()
    for tier in (1, 2, 3):
        c.execute("SELECT COUNT(*) FROM investors WHERE tier = ? AND status = 'CONTACTED'", (tier,))
        contacted = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM investors WHERE tier = ? AND replied = 1", (tier,))
        replied = c.fetchone()[0]
        total_t = contacted + replied
        rate = (replied / total_t * 100) if total_t > 0 else 0
        print(f"  Tier {tier}: {replied}/{total_t} replied ({rate:.1f}%)")

    # Reply rate by investor type
    print()
    c.execute("SELECT DISTINCT investor_type FROM investors WHERE investor_type IS NOT NULL")
    types = [r[0] for r in c.fetchall()]
    for itype in types:
        c.execute("SELECT COUNT(*) FROM investors WHERE investor_type = ? AND email_count > 0", (itype,))
        contacted = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM investors WHERE investor_type = ? AND replied = 1", (itype,))
        replied = c.fetchone()[0]
        rate = (replied / contacted * 100) if contacted > 0 else 0
        print(f"  {itype}: {replied}/{contacted} ({rate:.1f}%)")

    conn.close()

    # Projections
    if stats["contacted"] > 0:
        print(f"\n  Current reply rate: {stats['reply_rate']:.1f}%")
        projected_replies = int(2250 * stats["reply_rate"] / 100)
        projected_meetings = int(projected_replies * 0.25)
        print(f"  Projected replies (90 days): {projected_replies}")
        print(f"  Projected meetings (90 days): {projected_meetings}")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def main():
    parser = argparse.ArgumentParser(
        description="ARIA v1 — Autonomous Relationship Intelligence Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Full pipeline")
    p_run.add_argument("--auto", action="store_true", help="Skip email preview")
    p_run.add_argument("--per-query", type=int, default=50, help="Results per Apollo query")
    p_run.add_argument("--limit", type=int, default=25, help="Max emails to send")

    # status
    sub.add_parser("status", help="Pipeline dashboard")

    # load
    p_load = sub.add_parser("load", help="Import CSV")
    p_load.add_argument("path", help="Path to CSV file")

    # verify
    sub.add_parser("verify", help="Verify emails")

    # score
    sub.add_parser("score", help="Score investors")

    # research
    p_research = sub.add_parser("research", help="Research investors")
    p_research.add_argument("n", type=int, help="Number to research")

    # write
    p_write = sub.add_parser("write", help="Write emails")
    p_write.add_argument("n", type=int, help="Number to write")

    # send
    p_send = sub.add_parser("send", help="Send to Instantly")
    p_send.add_argument("--dry-run", action="store_true", help="Show what would be sent")

    # followup
    sub.add_parser("followup", help="Process follow-ups")

    # replies
    sub.add_parser("replies", help="Check for replies")

    # linkedin
    sub.add_parser("linkedin", help="Generate HeyReach CSV")

    # briefing
    sub.add_parser("briefing", help="Send daily briefing")

    # stats
    sub.add_parser("stats", help="Detailed analytics")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(auto=args.auto, per_query=args.per_query, send_limit=args.limit)
    elif args.command == "status":
        cmd_status()
    elif args.command == "load":
        cmd_load(args.path)
    elif args.command == "verify":
        cmd_verify()
    elif args.command == "score":
        cmd_score()
    elif args.command == "research":
        cmd_research(args.n)
    elif args.command == "write":
        cmd_write(args.n)
    elif args.command == "send":
        cmd_send(dry_run=args.dry_run)
    elif args.command == "followup":
        cmd_followup()
    elif args.command == "replies":
        cmd_replies()
    elif args.command == "linkedin":
        cmd_linkedin()
    elif args.command == "briefing":
        send_daily_briefing()
    elif args.command == "stats":
        cmd_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
