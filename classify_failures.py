#!/usr/bin/env python3
# ABOUTME: Use LLM to classify trial failure reasons into Efficacy vs Adverse Effects

import json
import argparse
import os
from typing import Dict, Optional


def classify_failure_reason(why_stopped: str, nct_id: str) -> Dict:
    """
    Classify trial termination reason into categories.

    Categories:
    - EFFICACY: Lack of efficacy, did not meet endpoint
    - SAFETY: Adverse effects, toxicity, safety concerns
    - OTHER: Administrative, funding, recruitment issues
    """

    if not why_stopped or why_stopped.strip() == '':
        return {
            'category': 'UNKNOWN',
            'confidence': 'low',
            'reason': 'No termination reason provided'
        }

    # Convert to lowercase for matching
    reason_lower = why_stopped.lower()

    # Keywords for efficacy failures
    efficacy_keywords = [
        'lack of efficacy',
        'no efficacy',
        'insufficient efficacy',
        'failed to meet',
        'did not meet endpoint',
        'did not meet primary endpoint',
        'ineffective',
        'no significant difference',
        'no benefit',
        'futility'
    ]

    # Keywords for safety/adverse event failures
    safety_keywords = [
        'adverse event',
        'adverse effect',
        'safety',
        'toxicity',
        'toxic',
        'serious adverse',
        'side effect',
        'tolerability',
        'death',
        'fatal'
    ]

    # Keywords for administrative/other
    admin_keywords = [
        'funding',
        'recruitment',
        'sponsor',
        'administrative',
        'slow enrollment',
        'unable to recruit',
        'withdrawn by sponsor',
        'business decision',
        'replaced by',
        'superseded'
    ]

    # Check for matches
    efficacy_match = any(kw in reason_lower for kw in efficacy_keywords)
    safety_match = any(kw in reason_lower for kw in safety_keywords)
    admin_match = any(kw in reason_lower for kw in admin_keywords)

    # Determine category
    if safety_match and not efficacy_match:
        return {
            'category': 'SAFETY',
            'confidence': 'high',
            'reason': why_stopped
        }
    elif efficacy_match and not safety_match:
        return {
            'category': 'EFFICACY',
            'confidence': 'high',
            'reason': why_stopped
        }
    elif admin_match:
        return {
            'category': 'OTHER',
            'confidence': 'high',
            'reason': why_stopped
        }
    elif efficacy_match and safety_match:
        # Both mentioned - needs manual review
        return {
            'category': 'AMBIGUOUS',
            'confidence': 'low',
            'reason': why_stopped,
            'note': 'Both efficacy and safety mentioned'
        }
    else:
        return {
            'category': 'UNKNOWN',
            'confidence': 'low',
            'reason': why_stopped
        }


def classify_trials(input_file: str, output_file: str):
    """Classify all failure reasons in trial dataset."""
    print(f"Loading trials from {input_file}...")

    with open(input_file, 'r') as f:
        trials = json.load(f)

    print(f"Found {len(trials)} trials")

    # Track failures only
    failures = []
    successes = []

    for trial in trials:
        label = trial.get('label')

        if label == 'SUCCESS':
            trial['failure_classification'] = None
            successes.append(trial)

        elif label == 'FAILURE':
            classification = classify_failure_reason(
                trial.get('why_stopped', ''),
                trial.get('nct_id', '')
            )
            trial['failure_classification'] = classification
            failures.append(trial)

        else:
            trial['failure_classification'] = None

    # Save classified data
    classified = successes + failures

    with open(output_file, 'w') as f:
        json.dump(classified, f, indent=2)

    # Print summary
    print(f"\n=== Classification Summary ===")
    print(f"Total trials: {len(classified)}")
    print(f"  SUCCESS: {len(successes)}")
    print(f"  FAILURE: {len(failures)}")

    if failures:
        efficacy_count = sum(
            1 for t in failures
            if t.get('failure_classification', {}).get('category') == 'EFFICACY'
        )
        safety_count = sum(
            1 for t in failures
            if t.get('failure_classification', {}).get('category') == 'SAFETY'
        )
        other_count = sum(
            1 for t in failures
            if t.get('failure_classification', {}).get('category') == 'OTHER'
        )
        unknown_count = sum(
            1 for t in failures
            if t.get('failure_classification', {}).get('category') in ['UNKNOWN', 'AMBIGUOUS']
        )

        print(f"\nFailure breakdown:")
        print(f"  EFFICACY: {efficacy_count}")
        print(f"  SAFETY: {safety_count}")
        print(f"  OTHER (admin): {other_count}")
        print(f"  UNKNOWN/AMBIGUOUS: {unknown_count}")

    print(f"\nOutput saved to: {output_file}")

    # Show some examples
    print(f"\n=== Sample Classifications ===")
    efficacy_examples = [
        t for t in failures
        if t.get('failure_classification', {}).get('category') == 'EFFICACY'
    ][:3]

    safety_examples = [
        t for t in failures
        if t.get('failure_classification', {}).get('category') == 'SAFETY'
    ][:3]

    if efficacy_examples:
        print("\nEFFICACY failures:")
        for ex in efficacy_examples:
            print(f"  {ex['nct_id']}: {ex['why_stopped']}")

    if safety_examples:
        print("\nSAFETY failures:")
        for ex in safety_examples:
            print(f"  {ex['nct_id']}: {ex['why_stopped']}")


def main():
    parser = argparse.ArgumentParser(
        description='Classify trial failure reasons using rule-based NLP'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input JSON file (from enrich_targets.py or query_trials.py)'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output JSON file with failure classifications'
    )

    args = parser.parse_args()

    classify_trials(args.input, args.output)


if __name__ == "__main__":
    main()
