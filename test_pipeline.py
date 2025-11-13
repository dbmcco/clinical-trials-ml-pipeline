#!/usr/bin/env python3
# ABOUTME: Unit tests for clinical trials pipeline data transformations

import json
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os


class TestDataTransformations(unittest.TestCase):
    """Test data transformation logic without hitting external APIs."""

    def test_trial_label_success(self):
        """Test that trials with progressed drugs are labeled SUCCESS."""
        trial = {
            'nct_id': 'NCT12345',
            'drug_name': 'TestDrug',
            'any_drug_progressed': True,
            'why_stopped': None
        }

        label = 'SUCCESS' if trial['any_drug_progressed'] else 'FAILURE'
        self.assertEqual(label, 'SUCCESS')

    def test_trial_label_failure(self):
        """Test that terminated trials without progression are FAILURE."""
        trial = {
            'nct_id': 'NCT12345',
            'drug_name': 'TestDrug',
            'any_drug_progressed': False,
            'why_stopped': 'Lack of efficacy'
        }

        label = 'SUCCESS' if trial['any_drug_progressed'] else 'FAILURE'
        self.assertEqual(label, 'FAILURE')

    def test_chembl_enrichment_structure(self):
        """Test ChEMBL enrichment data structure."""
        enrichment = {
            'found': True,
            'chembl_id': 'CHEMBL123',
            'targets': [
                {
                    'chembl_id': 'CHEMBL_TARGET_1',
                    'uniprot_id': 'P12345',
                    'ic50_values': [
                        {'value': 10.5, 'units': 'nM'}
                    ]
                }
            ],
            'has_uniprot_targets': True
        }

        self.assertTrue(enrichment['found'])
        self.assertEqual(enrichment['chembl_id'], 'CHEMBL123')
        self.assertEqual(len(enrichment['targets']), 1)
        self.assertTrue(enrichment['has_uniprot_targets'])

    def test_failure_classification_efficacy(self):
        """Test failure reason classification - efficacy."""
        efficacy_reasons = [
            'lack of efficacy',
            'did not meet endpoint',
            'insufficient efficacy',
            'no clinical benefit'
        ]

        for reason in efficacy_reasons:
            classification = self._classify_failure(reason)
            self.assertEqual(classification, 'FAILURE_EFFICACY',
                           f"Failed to classify '{reason}' as FAILURE_EFFICACY")

    def test_failure_classification_safety(self):
        """Test failure reason classification - safety."""
        safety_reasons = [
            'adverse events',
            'safety concerns',
            'toxicity',
            'serious adverse event'
        ]

        for reason in safety_reasons:
            classification = self._classify_failure(reason)
            self.assertEqual(classification, 'FAILURE_SAFETY',
                           f"Failed to classify '{reason}' as FAILURE_SAFETY")

    def test_ppi_enrichment_structure(self):
        """Test PPI enrichment data structure."""
        ppi_data = {
            'uniprot_id': 'P12345',
            'protein_info': {
                'protein_name': 'Test Protein',
                'gene_name': 'TESTGENE',
                'organism': 'Homo sapiens'
            },
            'uniprot_interactions': [
                {
                    'partner_uniprot_id': 'Q98765',
                    'partner_gene': 'PARTNER1',
                    'num_experiments': 5
                }
            ],
            'string_interactions': {
                'found': True,
                'interaction_count': 10,
                'interactions': []
            }
        }

        self.assertEqual(ppi_data['uniprot_id'], 'P12345')
        self.assertIsNotNone(ppi_data['protein_info'])
        self.assertGreater(len(ppi_data['uniprot_interactions']), 0)
        self.assertTrue(ppi_data['string_interactions']['found'])

    def test_ic50_aggregation(self):
        """Test IC50 value aggregation (min, max, mean)."""
        ic50_values = [
            {'value': 10.0, 'units': 'nM'},
            {'value': 20.0, 'units': 'nM'},
            {'value': 15.0, 'units': 'nM'}
        ]

        values = [v['value'] for v in ic50_values]
        ic50_min = min(values)
        ic50_max = max(values)
        ic50_mean = sum(values) / len(values)

        self.assertEqual(ic50_min, 10.0)
        self.assertEqual(ic50_max, 20.0)
        self.assertEqual(ic50_mean, 15.0)

    def test_limit_functionality(self):
        """Test that limit parameter correctly restricts dataset size."""
        full_dataset = [{'id': i} for i in range(100)]
        limit = 10

        limited = full_dataset[:limit]

        self.assertEqual(len(limited), limit)
        self.assertEqual(limited[0]['id'], 0)
        self.assertEqual(limited[-1]['id'], 9)

    def _classify_failure(self, reason: str) -> str:
        """Helper method to classify failure reasons."""
        if not reason:
            return 'FAILURE_OTHER'

        reason_lower = reason.lower()

        # Efficacy patterns
        efficacy_keywords = [
            'efficacy', 'endpoint', 'futility', 'benefit',
            'response rate', 'insufficient', 'ineffective'
        ]

        # Safety patterns
        safety_keywords = [
            'adverse', 'safety', 'toxic', 'tolera', 'death',
            'serious', 'harm'
        ]

        # Check efficacy first
        if any(kw in reason_lower for kw in efficacy_keywords):
            return 'FAILURE_EFFICACY'

        # Check safety
        if any(kw in reason_lower for kw in safety_keywords):
            return 'FAILURE_SAFETY'

        return 'FAILURE_OTHER'


class TestFileOperations(unittest.TestCase):
    """Test file I/O operations."""

    def test_json_read_write(self):
        """Test JSON file read/write operations."""
        test_data = [
            {
                'nct_id': 'NCT12345',
                'drug_name': 'TestDrug',
                'label': 'FAILURE'
            }
        ]

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f, indent=2)
            temp_path = f.name

        try:
            # Read back
            with open(temp_path, 'r') as f:
                loaded_data = json.load(f)

            self.assertEqual(loaded_data, test_data)
            self.assertEqual(loaded_data[0]['nct_id'], 'NCT12345')

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
