# ABOUTME: Stage 4 - Export ML-ready dataset from enriched clinical trials

import os
import json
from typing import List, Dict, Optional
from tinydb import TinyDB, Query
import argparse
from utils import extract_uniprot_ids, get_ic50_values, classify_sponsor


class MLDatasetExporter:
    """Export enriched trials as ML dataset"""

    def __init__(self, db_path: str = "data/clinical_trials.json"):
        """
        Initialize exporter

        Args:
            db_path: Path to TinyDB database
        """
        self.db = TinyDB(db_path)
        self.trials_table = self.db.table('trials')

    def export_rich_dataset(self, output_file: str,
                           min_confidence: str = 'low',
                           require_targets: bool = False,
                           validation_mode: bool = False):
        """
        Export all trials with complete enrichment

        Args:
            output_file: Output JSON file path
            min_confidence: Minimum confidence level (low/medium/high)
            require_targets: If True, only export trials with UniProt targets
            validation_mode: If True, enforce strict completeness for validation dataset
        """
        Trial = Query()

        # Filter: Must have LLM analysis completed
        complete_trials = self.trials_table.search(
            Trial.enrichment_status.stage3_llm_analysis == 'completed'
        )

        print("="*50)
        print("STAGE 4: ML DATASET EXPORT")
        print("="*50)
        print(f"\nTotal enriched trials: {len(complete_trials)}")

        # Apply filters
        filtered_trials = complete_trials
        dropped_reasons = {}

        if min_confidence != 'low':
            confidence_order = {'low': 0, 'medium': 1, 'high': 2}
            min_level = confidence_order[min_confidence]
            filtered_trials = [
                t for t in filtered_trials
                if confidence_order.get(t.get('llm_analysis', {}).get('confidence', 'low'), 0) >= min_level
            ]
            print(f"After confidence filter (>={min_confidence}): {len(filtered_trials)}")

        if require_targets:
            filtered_trials = [
                t for t in filtered_trials
                if t.get('chembl_enrichment', {}).get('has_uniprot_targets', False)
            ]
            print(f"After targets filter: {len(filtered_trials)}")

        # Validation mode: Strict completeness enforcement
        if validation_mode:
            print("\n🔒 VALIDATION MODE: Enforcing completeness requirements")
            validated_trials = []
            for trial in filtered_trials:
                is_complete, reason = self._check_validation_completeness(trial)
                if is_complete:
                    validated_trials.append(trial)
                else:
                    dropped_reasons[reason] = dropped_reasons.get(reason, 0) + 1

            print(f"After validation completeness: {len(validated_trials)}/{len(filtered_trials)}")
            if dropped_reasons:
                print("\nDropped trials by reason:")
                for reason, count in sorted(dropped_reasons.items(), key=lambda x: -x[1]):
                    print(f"  {reason}: {count}")

            filtered_trials = validated_trials

        # Build ML dataset
        ml_dataset = []
        for trial in filtered_trials:
            ml_record = self._build_ml_record(trial)
            ml_dataset.append(ml_record)

        # Write to file
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(ml_dataset, f, indent=2)

        print(f"\n✅ Exported {len(ml_dataset)} trials to {output_file}")
        self.print_statistics(ml_dataset)

    def _check_validation_completeness(self, trial: Dict) -> tuple[bool, str]:
        """
        Check if trial meets validation dataset completeness requirements

        Args:
            trial: Trial document from TinyDB

        Returns:
            (is_complete, drop_reason) tuple
        """
        chembl_enrichment = trial.get('chembl_enrichment', {})
        ppi_enrichment = trial.get('ppi_enrichment', {})
        llm_analysis = trial.get('llm_analysis', {})

        # Requirement 1: Must have UniProt targets
        if not chembl_enrichment.get('has_uniprot_targets'):
            return (False, 'missing_uniprot_targets')

        # Requirement 2: Must have PPI network data
        if ppi_enrichment.get('uniprot_count', 0) == 0:
            return (False, 'missing_ppi_network')

        # Requirement 3: FAILURE_SAFETY trials must have safety classification
        failure_category = llm_analysis.get('classification', '')
        if not failure_category.startswith('FAILURE_'):
            return (False, 'invalid_failure_category')

        # Requirement 4: Must have at least medium confidence for FAILURE_SAFETY
        if failure_category == 'FAILURE_SAFETY':
            confidence = llm_analysis.get('confidence', 'low')
            if confidence == 'low':
                return (False, 'low_confidence_safety_classification')

        # Requirement 5: Must have target IC50 or assay data (at least one target)
        targets = chembl_enrichment.get('targets', [])
        if len(targets) == 0:
            return (False, 'no_target_data')

        return (True, None)

    def _build_ml_record(self, trial: Dict) -> Dict:
        """
        Build ML record from trial document

        Args:
            trial: Trial document from TinyDB

        Returns:
            ML-ready record dictionary
        """
        # Extract features
        chembl_enrichment = trial.get('chembl_enrichment', {})
        ppi_enrichment = trial.get('ppi_enrichment', {})
        llm_analysis = trial.get('llm_analysis', {})

        # UniProt IDs
        uniprot_ids = extract_uniprot_ids(trial)

        # IC50 aggregations
        ic50_values = get_ic50_values(trial)
        min_ic50 = min(ic50_values) if ic50_values else None
        max_ic50 = max(ic50_values) if ic50_values else None
        avg_ic50 = sum(ic50_values) / len(ic50_values) if ic50_values else None

        # PPI features
        interactions = ppi_enrichment.get('interactions', [])
        network_features = ppi_enrichment.get('network_features', {})

        return {
            # Identifiers
            'nct_id': trial['nct_id'],
            'drug_name': trial['drug_name'],

            # Labels
            'failure_category': llm_analysis.get('classification', 'UNKNOWN'),
            'confidence': llm_analysis.get('confidence', 'low'),
            'label_reasoning': llm_analysis.get('reasoning', ''),

            # Target Features
            'target_count': len(chembl_enrichment.get('targets', [])),
            'has_uniprot_targets': chembl_enrichment.get('has_uniprot_targets', False),
            'uniprot_ids': uniprot_ids,

            # IC50 Features
            'ic50_count': len(ic50_values),
            'min_ic50': min_ic50,
            'max_ic50': max_ic50,
            'avg_ic50': avg_ic50,

            # PPI Features
            'ppi_network_size': len(interactions),
            'ppi_avg_degree': network_features.get('avg_degree', 0),
            'ppi_clustering_coefficient': network_features.get('clustering_coefficient', 0),

            # Trial Metadata
            'sponsor': trial.get('sponsor'),
            'sponsor_type': classify_sponsor(trial.get('sponsor')),
            'phase': trial.get('phase'),
            'overall_status': trial.get('overall_status'),
            'why_stopped': trial.get('why_stopped'),
            'start_date': trial.get('start_date'),
            'completion_date': trial.get('completion_date'),

            # Raw Data (for advanced features)
            'ppi_interactions': interactions,
            'chembl_targets': chembl_enrichment.get('targets', [])
        }

    def print_statistics(self, dataset: List[Dict]):
        """
        Print dataset quality statistics

        Args:
            dataset: List of ML records
        """
        total = len(dataset)
        with_targets = sum(1 for t in dataset if t['has_uniprot_targets'])
        with_ppi = sum(1 for t in dataset if t['ppi_network_size'] > 0)

        # Category distribution
        categories = {}
        for trial in dataset:
            cat = trial['failure_category']
            categories[cat] = categories.get(cat, 0) + 1

        # Confidence distribution
        confidences = {}
        for trial in dataset:
            conf = trial['confidence']
            confidences[conf] = confidences.get(conf, 0) + 1

        # Sponsor type distribution
        sponsor_types = {}
        for trial in dataset:
            stype = trial['sponsor_type']
            sponsor_types[stype] = sponsor_types.get(stype, 0) + 1

        # IC50 statistics
        ic50_counts = [t['ic50_count'] for t in dataset if t['ic50_count'] > 0]
        avg_ic50_count = sum(ic50_counts) / len(ic50_counts) if ic50_counts else 0

        print("\n" + "="*50)
        print("DATASET STATISTICS")
        print("="*50)
        print(f"\nTotal Trials: {total}")
        print(f"With UniProt Targets: {with_targets} ({with_targets/total*100:.1f}%)")
        print(f"With PPI Networks: {with_ppi} ({with_ppi/total*100:.1f}%)")
        print(f"Avg IC50 Measurements/Trial: {avg_ic50_count:.1f}")

        print("\nFailure Categories:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count} ({count/total*100:.1f}%)")

        print("\nConfidence Levels:")
        for conf, count in sorted(confidences.items()):
            print(f"  {conf}: {count} ({count/total*100:.1f}%)")

        print("\nSponsor Types:")
        for stype, count in sorted(sponsor_types.items()):
            print(f"  {stype}: {count} ({count/total*100:.1f}%)")

    def export_for_synthyra_ppi(self, output_file: str):
        """
        Export specialized dataset for Synthyra PPI prediction

        Args:
            output_file: Output JSON file path
        """
        # Filter to trials with:
        # 1. UniProt targets
        # 2. PPI networks
        # 3. High/medium confidence classifications
        Trial = Query()

        high_quality_trials = self.trials_table.search(
            (Trial.enrichment_status.stage3_llm_analysis == 'completed') &
            (Trial.chembl_enrichment.has_uniprot_targets == True)
        )

        # Further filter by PPI and confidence
        filtered = [
            t for t in high_quality_trials
            if (t.get('ppi_enrichment', {}).get('uniprot_count', 0) > 0 and
                t.get('llm_analysis', {}).get('confidence') in ['high', 'medium'])
        ]

        print(f"\nSynthyra PPI Dataset: {len(filtered)} trials")
        print("  (UniProt targets + PPI networks + high/medium confidence)")

        # Build specialized records
        synthyra_dataset = []
        for trial in filtered:
            synthyra_record = self._build_synthyra_record(trial)
            synthyra_dataset.append(synthyra_record)

        with open(output_file, 'w') as f:
            json.dump(synthyra_dataset, f, indent=2)

        print(f"✅ Exported to {output_file}")

    def _build_synthyra_record(self, trial: Dict) -> Dict:
        """
        Build specialized record for Synthyra PPI prediction

        Args:
            trial: Trial document

        Returns:
            Synthyra-specific record
        """
        base_record = self._build_ml_record(trial)

        # Add Synthyra-specific features
        synthyra_features = {
            # PPI network topology
            'ppi_protein_count': len(set(
                [i['protein_a'] for i in base_record['ppi_interactions']] +
                [i['protein_b'] for i in base_record['ppi_interactions']]
            )),
            'ppi_edge_count': len(base_record['ppi_interactions']),

            # Target binding strength
            'strong_binder_count': sum(
                1 for t in base_record['chembl_targets']
                for ic50 in t.get('ic50_values', [])
                if ic50.get('units') == 'nM' and ic50.get('value', float('inf')) < 100
            ),

            # Failure type for training
            'is_safety_failure': base_record['failure_category'] == 'FAILURE_SAFETY',
            'is_efficacy_failure': base_record['failure_category'] == 'FAILURE_EFFICACY'
        }

        return {**base_record, **synthyra_features}

    def close(self):
        """Close database connection"""
        self.db.close()


def main():
    """Main entry point for ML dataset export"""
    parser = argparse.ArgumentParser(
        description="Export ML-ready dataset from enriched trials"
    )
    parser.add_argument(
        '--db',
        default='data/clinical_trials.json',
        help='Path to TinyDB database'
    )
    parser.add_argument(
        '--output',
        default='data/ml_dataset.json',
        help='Output dataset file'
    )
    parser.add_argument(
        '--min-confidence',
        choices=['low', 'medium', 'high'],
        default='low',
        help='Minimum confidence level for inclusion'
    )
    parser.add_argument(
        '--require-targets',
        action='store_true',
        help='Only export trials with UniProt targets'
    )
    parser.add_argument(
        '--synthyra-ppi',
        action='store_true',
        help='Export specialized Synthyra PPI dataset'
    )
    parser.add_argument(
        '--validation-mode',
        action='store_true',
        help='Enforce strict completeness for validation dataset (requires targets + PPI + quality classifications)'
    )

    args = parser.parse_args()

    exporter = MLDatasetExporter(db_path=args.db)

    try:
        if args.synthyra_ppi:
            synthyra_output = args.output.replace('.json', '_synthyra_ppi.json')
            exporter.export_for_synthyra_ppi(synthyra_output)
        else:
            exporter.export_rich_dataset(
                output_file=args.output,
                min_confidence=args.min_confidence,
                require_targets=args.require_targets,
                validation_mode=args.validation_mode
            )
    finally:
        exporter.close()


if __name__ == "__main__":
    main()
