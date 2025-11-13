#!/usr/bin/env python3
# ABOUTME: Monitor pipeline progress in real-time

import sys
import time
from pathlib import Path
from tinydb import TinyDB, Query

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def monitor_progress(db_path: str = "data/clinical_trials.json",
                     queue_path: str = "data/enrichment_queue.json",
                     refresh_interval: int = 5):
    """
    Monitor pipeline progress

    Args:
        db_path: Path to main database
        queue_path: Path to retry queue
        refresh_interval: Seconds between updates
    """
    print("="*60)
    print("CLINICAL TRIALS PIPELINE - PROGRESS MONITOR")
    print("="*60)
    print(f"\nDatabase: {db_path}")
    print(f"Refresh: Every {refresh_interval} seconds (Ctrl+C to exit)\n")

    try:
        while True:
            # Load databases
            db = TinyDB(db_path)
            queue_db = TinyDB(queue_path)
            trials_table = db.table('trials')
            retry_table = queue_db.table('retry_queue')

            # Count totals
            total_trials = len(trials_table.all())

            # Count by stage
            Trial = Query()

            stage2_pending = len(trials_table.search(
                Trial.enrichment_status.stage2_targets == 'pending'
            ))
            stage2_completed = len(trials_table.search(
                Trial.enrichment_status.stage2_targets == 'completed'
            ))
            stage2_failed = len(trials_table.search(
                Trial.enrichment_status.stage2_targets == 'failed'
            ))

            stage3_pending = len(trials_table.search(
                Trial.enrichment_status.stage3_llm_analysis == 'pending'
            ))
            stage3_completed = len(trials_table.search(
                Trial.enrichment_status.stage3_llm_analysis == 'completed'
            ))

            # Retry queue
            retry_count = len(retry_table.all())

            # Clear screen and display
            print("\033[2J\033[H")  # Clear screen
            print("="*60)
            print(f"PIPELINE PROGRESS - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)

            print(f"\n📊 Total Trials: {total_trials}")

            print("\n[Stage 2: Enrichment]")
            print(f"  ✅ Completed: {stage2_completed} ({stage2_completed/total_trials*100:.1f}%)")
            print(f"  ⏳ Pending: {stage2_pending} ({stage2_pending/total_trials*100:.1f}%)")
            print(f"  ❌ Failed: {stage2_failed} ({stage2_failed/total_trials*100:.1f}%)")

            print("\n[Stage 3: LLM Analysis]")
            print(f"  ✅ Completed: {stage3_completed} ({stage3_completed/total_trials*100:.1f}%)")
            print(f"  ⏳ Pending: {stage3_pending} ({stage3_pending/total_trials*100:.1f}%)")

            print(f"\n[Retry Queue]")
            print(f"  🔄 Pending Retries: {retry_count}")

            # Progress bars
            if total_trials > 0:
                stage2_pct = (stage2_completed / total_trials) * 100
                stage3_pct = (stage3_completed / total_trials) * 100

                print("\nProgress:")
                print(f"  Stage 2: [{'=' * int(stage2_pct/2)}{' ' * (50-int(stage2_pct/2))}] {stage2_pct:.1f}%")
                print(f"  Stage 3: [{'=' * int(stage3_pct/2)}{' ' * (50-int(stage3_pct/2))}] {stage3_pct:.1f}%")

            db.close()
            queue_db.close()

            time.sleep(refresh_interval)

    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor pipeline progress")
    parser.add_argument('--db', default='data/clinical_trials.json', help='Database path')
    parser.add_argument('--queue', default='data/enrichment_queue.json', help='Queue path')
    parser.add_argument('--refresh', type=int, default=5, help='Refresh interval (seconds)')

    args = parser.parse_args()

    monitor_progress(db_path=args.db, queue_path=args.queue, refresh_interval=args.refresh)
