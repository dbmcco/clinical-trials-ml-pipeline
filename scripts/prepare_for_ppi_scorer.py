#!/usr/bin/env python3
# ABOUTME: Prepare validation dataset for SynteractTurbo PPI scorer submission

import json
import argparse
from pathlib import Path
from typing import List, Dict


def load_validation_dataset(input_file: str) -> List[Dict]:
    """Load validation dataset from JSON"""
    with open(input_file, 'r') as f:
        return json.load(f)


def prepare_ppi_scorer_input(trials: List[Dict], output_file: str):
    """
    Prepare input format for SynteractTurbo PPI scorer

    Args:
        trials: List of validation trials
        output_file: Output file path
    """
    ppi_input = []

    for trial in trials:
        # Skip trials without safety failures
        if trial['failure_category'] != 'FAILURE_SAFETY':
            continue

        # Build PPI scorer input record
        record = {
            'nct_id': trial['nct_id'],
            'drug_name': trial['drug_name'],
            'uniprot_targets': trial['uniprot_ids'],
            'ppi_network': trial['ppi_interactions'],

            # Metadata for analysis
            'actual_outcome': 'FAILURE_SAFETY',
            'sae_summary': {
                'deaths': trial['sae_total_deaths'],
                'sae_rate': trial['sae_rate'],
                'has_safety_signal': trial['sae_has_safety_signal']
            },
            'confidence': trial['confidence'],
            'heuristic_override': trial['heuristic_override'],

            # Additional context
            'phase': trial['phase'],
            'sponsor_type': trial['sponsor_type']
        }

        ppi_input.append(record)

    # Write to output file
    with open(output_file, 'w') as f:
        json.dump(ppi_input, f, indent=2)

    return len(ppi_input)


def generate_analysis_template(trials: List[Dict], output_file: str):
    """
    Generate analysis template for comparing PPI predictions vs actual outcomes

    Args:
        trials: List of validation trials
        output_file: Output template file path
    """
    template = {
        'validation_study': {
            'objective': 'Test if SynteractTurbo could have predicted safety failures based on PPI patterns',
            'total_safety_failures': sum(1 for t in trials if t['failure_category'] == 'FAILURE_SAFETY'),
            'total_trials': len(trials),
            'analysis_date': None  # To be filled when PPI scores are available
        },
        'trials_for_scoring': [],
        'results': {
            'true_positives': 0,   # Predicted safety risk + actual safety failure
            'false_positives': 0,  # Predicted safety risk + no actual safety failure
            'true_negatives': 0,   # No safety risk predicted + no actual failure
            'false_negatives': 0,  # No safety risk predicted + actual safety failure
            'accuracy': None,
            'precision': None,
            'recall': None,
            'notes': []
        }
    }

    # Add trials for scoring
    for trial in trials:
        if trial['failure_category'] == 'FAILURE_SAFETY':
            template['trials_for_scoring'].append({
                'nct_id': trial['nct_id'],
                'drug_name': trial['drug_name'],
                'actual_outcome': 'FAILURE_SAFETY',
                'ppi_prediction': None,  # To be filled with SynteractTurbo score
                'confidence': trial['confidence'],
                'sae_deaths': trial['sae_total_deaths'],
                'sae_rate': trial['sae_rate']
            })

    with open(output_file, 'w') as f:
        json.dump(template, f, indent=2)


def main():
    """Main entry point for PPI scorer preparation"""
    parser = argparse.ArgumentParser(
        description="Prepare validation dataset for SynteractTurbo PPI scorer"
    )
    parser.add_argument(
        '--input',
        required=True,
        help='Input validation dataset (JSON)'
    )
    parser.add_argument(
        '--output-dir',
        default='data/ppi_scorer',
        help='Output directory for PPI scorer files'
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*50)
    print("PPI SCORER PREPARATION")
    print("="*50)

    # Load validation dataset
    print(f"\nLoading validation dataset from {args.input}...")
    trials = load_validation_dataset(args.input)
    print(f"Loaded {len(trials)} trials")

    # Prepare PPI scorer input
    ppi_input_file = output_dir / 'ppi_scorer_input.json'
    print(f"\nPreparing PPI scorer input...")
    safety_trial_count = prepare_ppi_scorer_input(trials, str(ppi_input_file))
    print(f"✅ {safety_trial_count} FAILURE_SAFETY trials prepared")
    print(f"   Output: {ppi_input_file}")

    # Generate analysis template
    template_file = output_dir / 'analysis_template.json'
    print(f"\nGenerating analysis template...")
    generate_analysis_template(trials, str(template_file))
    print(f"✅ Analysis template created")
    print(f"   Output: {template_file}")

    # Print summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Total trials: {len(trials)}")
    print(f"Safety failures: {safety_trial_count}")
    print(f"\nNext steps:")
    print(f"1. Submit {ppi_input_file} to SynteractTurbo PPI scorer")
    print(f"2. Collect PPI predictions and add to {template_file}")
    print(f"3. Calculate validation metrics (accuracy, precision, recall)")


if __name__ == "__main__":
    main()
