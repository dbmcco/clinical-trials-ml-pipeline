# ABOUTME: Comprehensive test suite for clinical trials ML pipeline

import os
import sys
import pytest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from tinydb import TinyDB, Query
from extract_aact_bulk import AACTBulkExtractor
from enrich_incremental import IncrementalEnricher
from analyze_failures_llm import FailureAnalyzer
from export_ml_dataset import MLDatasetExporter


class TestPipeline:
    """Integration tests for full pipeline"""

    @pytest.fixture(scope="class")
    def test_db_path(self, tmp_path_factory):
        """Create temporary database path"""
        return str(tmp_path_factory.mktemp("data") / "test_trials.json")

    @pytest.fixture(scope="class")
    def test_queue_path(self, tmp_path_factory):
        """Create temporary queue path"""
        return str(tmp_path_factory.mktemp("data") / "test_queue.json")

    def test_stage1_extraction(self, test_db_path):
        """Test Stage 1: AACT extraction"""
        extractor = AACTBulkExtractor(db_path=test_db_path)

        try:
            count = extractor.extract_all_trials(
                start_year=2020,
                limit=10  # Small sample for testing
            )

            assert count == 10, "Should extract 10 trials"

            # Verify database structure
            db = TinyDB(test_db_path)
            trials = db.table('trials').all()

            assert len(trials) == 10
            assert all('nct_id' in t for t in trials)
            assert all('enrichment_status' in t for t in trials)
            assert all(t['enrichment_status']['stage2_targets'] == 'pending' for t in trials)

            db.close()

        finally:
            extractor.close()

    def test_stage2_target_enrichment(self, test_db_path, test_queue_path):
        """Test Stage 2: Target enrichment"""
        enricher = IncrementalEnricher(db_path=test_db_path, queue_path=test_queue_path)

        try:
            # Run target enrichment only
            Trial = Query()
            pending = enricher.trials_table.search(
                Trial.enrichment_status.stage2_targets == 'pending'
            )

            assert len(pending) > 0, "Should have pending trials"

            # Enrich first trial
            enricher.enrich_targets(pending[0])

            # Verify enrichment
            updated = enricher.trials_table.get(doc_id=pending[0].doc_id)
            assert 'chembl_enrichment' in updated
            assert updated['enrichment_status']['stage2_targets'] in ['completed', 'failed']

        finally:
            enricher.close()

    def test_stage3_llm_analysis_mock(self, test_db_path):
        """Test Stage 3: LLM analysis (without actual API call)"""
        # This test verifies the structure without calling Claude API
        db = TinyDB(test_db_path)
        trials_table = db.table('trials')

        # Mock LLM analysis result
        mock_analysis = {
            'classification': 'FAILURE_SAFETY',
            'confidence': 'high',
            'reasoning': 'Test reasoning',
            'verification_passed': True,
            'contradictions_found': [],
            'analysis_timestamp': '2025-11-13T00:00:00',
            'claude_model': 'claude-3-5-sonnet-20250929',
            'tokens_used': 1000
        }

        # Update first trial with mock analysis
        Trial = Query()
        trials = trials_table.all()
        if trials:
            trials_table.update(
                {'llm_analysis': mock_analysis,
                 'enrichment_status': {
                     **trials[0]['enrichment_status'],
                     'stage3_llm_analysis': 'completed'
                 }},
                doc_ids=[trials[0].doc_id]
            )

            # Verify
            updated = trials_table.get(doc_id=trials[0].doc_id)
            assert 'llm_analysis' in updated
            assert updated['llm_analysis']['classification'] == 'FAILURE_SAFETY'

        db.close()

    def test_stage4_export(self, test_db_path, tmp_path):
        """Test Stage 4: ML dataset export"""
        output_file = str(tmp_path / "test_export.json")

        exporter = MLDatasetExporter(db_path=test_db_path)

        try:
            exporter.export_rich_dataset(
                output_file=output_file,
                min_confidence='low',
                require_targets=False
            )

            # Verify export file
            assert os.path.exists(output_file)

            import json
            with open(output_file, 'r') as f:
                dataset = json.load(f)

            assert len(dataset) > 0
            assert all('nct_id' in record for record in dataset)
            assert all('failure_category' in record for record in dataset)

        finally:
            exporter.close()


class TestDataTransformations:
    """Unit tests for data transformation functions"""

    def test_extract_uniprot_ids(self):
        """Test UniProt ID extraction"""
        from utils import extract_uniprot_ids

        trial = {
            'chembl_enrichment': {
                'has_uniprot_targets': True,
                'targets': [
                    {'uniprot_id': 'P12345'},
                    {'uniprot_id': 'Q67890'},
                    {'uniprot_id': None}
                ]
            }
        }

        ids = extract_uniprot_ids(trial)
        assert len(ids) == 2
        assert 'P12345' in ids
        assert 'Q67890' in ids

    def test_ic50_extraction(self):
        """Test IC50 value extraction"""
        from utils import get_ic50_values

        trial = {
            'chembl_enrichment': {
                'targets': [
                    {'ic50_values': [
                        {'value': 10.0, 'units': 'nM'},
                        {'value': 50.0, 'units': 'nM'}
                    ]},
                    {'ic50_values': [
                        {'value': 100.0, 'units': 'uM'}  # Different units, should be skipped
                    ]}
                ]
            }
        }

        values = get_ic50_values(trial)
        assert len(values) == 2
        assert 10.0 in values
        assert 50.0 in values

    def test_sponsor_classification(self):
        """Test sponsor type classification"""
        from utils import classify_sponsor

        assert classify_sponsor("Pfizer Inc") == "industry"
        assert classify_sponsor("University of California") == "academic"
        assert classify_sponsor("National Cancer Institute") == "government"
        assert classify_sponsor("Unknown Sponsor") == "other"
        assert classify_sponsor(None) == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
