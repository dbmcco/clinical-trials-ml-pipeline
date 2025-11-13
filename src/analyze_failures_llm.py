# ABOUTME: Stage 3 - LLM-based failure classification using Claude SDK with self-verification

import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
from tinydb import TinyDB, Query
import argparse
from dotenv import load_dotenv
from anthropic import Anthropic
from utils import format_timestamp

# Load environment variables
load_dotenv()

class FailureAnalyzer:
    """LLM-based failure classification with self-verification"""

    def __init__(self, db_path: str = "data/clinical_trials.json",
                 cache_path: str = "data/llm_analysis_cache.json",
                 api_key: Optional[str] = None):
        """
        Initialize analyzer with Claude SDK

        Args:
            db_path: Path to main TinyDB database
            cache_path: Path to LLM response cache
            api_key: Anthropic API key (default: from environment)
        """
        self.db = TinyDB(db_path)
        self.cache_db = TinyDB(cache_path)
        self.trials_table = self.db.table('trials')
        self.cache_table = self.cache_db.table('llm_cache')

        # Initialize Claude client
        api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20250929"

        # Statistics
        self.total_tokens = 0
        self.total_cost = 0.0

    def analyze_all_pending(self, limit: Optional[int] = None):
        """
        Analyze all trials pending LLM classification

        Args:
            limit: Optional limit for testing
        """
        Trial = Query()
        pending = self.trials_table.search(
            (Trial.enrichment_status.stage2_failure_details == 'completed') &
            (Trial.enrichment_status.stage3_llm_analysis == 'pending')
        )

        if limit:
            pending = pending[:limit]

        print("="*50)
        print("STAGE 3: LLM FAILURE CLASSIFICATION")
        print("="*50)
        print(f"\nTotal trials for analysis: {len(pending)}")
        print(f"Model: {self.model}")
        print(f"Strategy: Self-verification (2 API calls per trial)\n")

        for i, trial in enumerate(pending, 1):
            print(f"\n[{i}/{len(pending)}] Analyzing {trial['nct_id']} ({trial['drug_name']})")
            self.analyze_trial(trial)

        self.print_statistics()

    def analyze_trial(self, trial: Dict):
        """
        Two-pass LLM analysis with self-verification and heuristic overrides

        Args:
            trial: Trial document from TinyDB
        """
        try:
            # Check cache first
            cached = self.check_cache(trial['nct_id'])
            if cached:
                print("  ✓ Using cached analysis")
                self.trials_table.update(
                    {'llm_analysis': cached,
                     'enrichment_status': {
                         **trial['enrichment_status'],
                         'stage3_llm_analysis': 'completed',
                         'last_updated': format_timestamp()
                     }},
                    doc_ids=[trial.doc_id]
                )
                return

            # Check for heuristic safety override BEFORE LLM analysis
            heuristic_override = self.check_safety_heuristics(trial)
            if heuristic_override:
                print(f"  🛑 HEURISTIC OVERRIDE: {heuristic_override['reason']}")
                llm_analysis = {
                    'classification': 'FAILURE_SAFETY',
                    'confidence': 'high',
                    'reasoning': heuristic_override['reason'],
                    'heuristic_override': True,
                    'sae_summary': heuristic_override.get('sae_summary'),
                    'analysis_timestamp': format_timestamp(),
                    'claude_model': None,
                    'tokens_used': 0
                }

                # Cache and update database
                self.cache_analysis(trial['nct_id'], llm_analysis)
                self.trials_table.update(
                    {'llm_analysis': llm_analysis,
                     'enrichment_status': {
                         **trial['enrichment_status'],
                         'stage3_llm_analysis': 'completed',
                         'last_updated': format_timestamp()
                     }},
                    doc_ids=[trial.doc_id]
                )
                print("  ✅ Heuristic classification complete (no LLM needed)")
                return

            # Pass 1: Initial Classification
            print("  → Pass 1: Initial classification...")
            classification_prompt = self.build_classification_prompt(trial)
            classification_response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": classification_prompt}
                ]
            )

            initial_classification = self.parse_classification(
                classification_response.content[0].text
            )
            print(f"    Classification: {initial_classification['category']} ({initial_classification['confidence']} confidence)")

            # Pass 2: Self-Verification
            print("  → Pass 2: Self-verification...")
            verification_prompt = self.build_verification_prompt(
                trial,
                initial_classification
            )
            verification_response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": verification_prompt}
                ]
            )

            verification = self.parse_verification(
                verification_response.content[0].text
            )
            print(f"    Verification: {'PASSED' if verification['passed'] else 'FAILED'}")

            # Combine results
            tokens_used = (
                classification_response.usage.input_tokens +
                classification_response.usage.output_tokens +
                verification_response.usage.input_tokens +
                verification_response.usage.output_tokens
            )

            self.total_tokens += tokens_used
            self.total_cost += self.calculate_cost(tokens_used)

            llm_analysis = {
                'classification': verification.get('revised_category', initial_classification['category']),
                'confidence': verification['confidence'],
                'reasoning': initial_classification['reasoning'],
                'verification_passed': verification['passed'],
                'contradictions_found': verification['contradictions'],
                'analysis_timestamp': format_timestamp(),
                'claude_model': self.model,
                'tokens_used': tokens_used
            }

            # Cache result
            self.cache_analysis(trial['nct_id'], llm_analysis)

            # Update database
            self.trials_table.update(
                {'llm_analysis': llm_analysis,
                 'enrichment_status': {
                     **trial['enrichment_status'],
                     'stage3_llm_analysis': 'completed',
                     'last_updated': format_timestamp()
                 }},
                doc_ids=[trial.doc_id]
            )

            print(f"  ✅ Analysis complete (tokens: {tokens_used})")

        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")
            # Mark as failed but don't crash
            self.trials_table.update(
                {'enrichment_status': {
                     **trial['enrichment_status'],
                     'stage3_llm_analysis': 'failed',
                     'last_updated': format_timestamp()
                 }},
                doc_ids=[trial.doc_id]
            )

    def check_safety_heuristics(self, trial: Dict) -> Optional[Dict]:
        """
        Check for deterministic safety signals that override LLM classification

        Args:
            trial: Trial document

        Returns:
            Override dict with reason if safety signal found, None otherwise
        """
        failure_enrichment = trial.get('failure_enrichment', {})
        ct_api_data = failure_enrichment.get('clinicaltrials_api', {})
        adverse_events = ct_api_data.get('adverse_events', {})

        if not adverse_events.get('found'):
            return None

        sae_summary = adverse_events.get('summary', {})

        # Heuristic 1: Any trial-related deaths
        if sae_summary.get('total_deaths', 0) > 0:
            return {
                'reason': f"Heuristic override: {sae_summary['total_deaths']} death(s) reported in trial",
                'sae_summary': sae_summary
            }

        # Heuristic 2: SAE rate > 10% (high safety signal)
        if sae_summary.get('sae_rate', 0) > 0.1:
            sae_rate_pct = sae_summary['sae_rate'] * 100
            return {
                'reason': f"Heuristic override: SAE rate {sae_rate_pct:.1f}% exceeds 10% threshold",
                'sae_summary': sae_summary
            }

        # Heuristic 3: Generic safety signal flag from SAE calculation
        if sae_summary.get('has_safety_signal', False):
            affected = sae_summary.get('total_serious_affected', 0)
            at_risk = sae_summary.get('total_serious_at_risk', 0)
            return {
                'reason': f"Heuristic override: Serious adverse events ({affected}/{at_risk} affected)",
                'sae_summary': sae_summary
            }

        return None

    def build_classification_prompt(self, trial: Dict) -> str:
        """
        Build comprehensive classification prompt

        Args:
            trial: Trial document

        Returns:
            Prompt string for Claude
        """
        failure_enrichment = trial.get('failure_enrichment', {})
        description = failure_enrichment.get('aact_description', 'None')
        if description:
            description = description[:1000]  # Limit to 1000 chars

        pubmed_count = len(failure_enrichment.get('pubmed_results', []))

        return f"""You are analyzing a Phase 1 clinical trial that was terminated, suspended, or withdrawn.

**Trial Information:**
- NCT ID: {trial['nct_id']}
- Drug: {trial['drug_name']}
- Title: {trial['title']}
- Status: {trial['overall_status']}
- Official Reason: {trial.get('why_stopped', 'Not provided')}

**Additional Context:**
- Detailed Description: {description}
- PubMed Publications: {pubmed_count} found
- Sponsor: {trial.get('sponsor', 'Unknown')}

**Task:**
Classify the reason for trial failure into ONE of these categories:

1. **FAILURE_SAFETY**: Terminated due to safety concerns, adverse events, toxicity, or tolerability issues
2. **FAILURE_EFFICACY**: Terminated due to lack of efficacy, poor results, or inability to meet endpoints
3. **FAILURE_ADMINISTRATIVE**: Terminated due to enrollment issues, funding, strategic decisions, or operational problems

**Output Format:**
Category: [FAILURE_SAFETY | FAILURE_EFFICACY | FAILURE_ADMINISTRATIVE]
Confidence: [high | medium | low]
Reasoning: [2-3 sentences explaining your classification based on the evidence]

**Example:**
Category: FAILURE_SAFETY
Confidence: high
Reasoning: The detailed description mentions "unexpected toxicity events" and "safety concerns leading to early termination." The official reason states "adverse events," confirming safety-related failure.
"""

    def build_verification_prompt(self, trial: Dict, classification: Dict) -> str:
        """
        Build self-verification prompt

        Args:
            trial: Trial document
            classification: Initial classification result

        Returns:
            Verification prompt string
        """
        failure_enrichment = trial.get('failure_enrichment', {})
        description = failure_enrichment.get('aact_description', 'None')
        if description:
            description = description[:500]

        return f"""You previously classified this clinical trial as:
Category: {classification['category']}
Confidence: {classification['confidence']}
Reasoning: {classification['reasoning']}

**Re-examine the evidence and check for:**
1. Any contradictions in the data
2. Whether the confidence level is appropriate
3. If a different category might be more accurate

**Trial Data:**
- Official Reason: {trial.get('why_stopped', 'Not provided')}
- Description Excerpt: {description}...
- Sponsor: {trial.get('sponsor', 'Unknown')}

**Output Format:**
Verification: [PASS | FAIL]
Final Confidence: [high | medium | low]
Contradictions Found: [List any contradictions, or "None"]
Revised Category (if needed): [Same category or new one]

**Example:**
Verification: PASS
Final Confidence: high
Contradictions Found: None
Revised Category: FAILURE_SAFETY
"""

    def parse_classification(self, text: str) -> Dict:
        """
        Parse Claude's classification response

        Args:
            text: Response text from Claude

        Returns:
            Parsed classification dictionary
        """
        lines = text.strip().split('\n')
        result = {'category': 'FAILURE_ADMINISTRATIVE', 'confidence': 'low', 'reasoning': ''}

        for line in lines:
            if line.startswith('Category:'):
                result['category'] = line.split(':')[1].strip()
            elif line.startswith('Confidence:'):
                result['confidence'] = line.split(':')[1].strip()
            elif line.startswith('Reasoning:'):
                result['reasoning'] = line.split(':', 1)[1].strip()

        return result

    def parse_verification(self, text: str) -> Dict:
        """
        Parse Claude's verification response

        Args:
            text: Response text from Claude

        Returns:
            Parsed verification dictionary
        """
        lines = text.strip().split('\n')
        result = {
            'passed': True,
            'confidence': 'medium',
            'contradictions': [],
            'revised_category': None
        }

        for line in lines:
            if line.startswith('Verification:'):
                result['passed'] = 'PASS' in line
            elif line.startswith('Final Confidence:'):
                result['confidence'] = line.split(':')[1].strip()
            elif line.startswith('Contradictions Found:'):
                contradictions = line.split(':', 1)[1].strip()
                result['contradictions'] = [] if contradictions == 'None' else [contradictions]
            elif line.startswith('Revised Category'):
                revised = line.split(':', 1)[1].strip()
                if 'FAILURE_' in revised:
                    result['revised_category'] = revised

        return result

    def calculate_cost(self, tokens: int) -> float:
        """
        Calculate cost for Claude API usage

        Args:
            tokens: Total tokens used

        Returns:
            Cost in USD
        """
        # Claude 3.5 Sonnet pricing (approximate)
        # Input: $3/MTok, Output: $15/MTok
        # Assume 50/50 split for simplicity
        cost_per_1k_tokens = 0.009  # Average
        return (tokens / 1000) * cost_per_1k_tokens

    def check_cache(self, nct_id: str) -> Optional[Dict]:
        """
        Check if analysis is cached

        Args:
            nct_id: Trial NCT ID

        Returns:
            Cached analysis or None
        """
        Cache = Query()
        cached = self.cache_table.search(Cache.nct_id == nct_id)
        return cached[0]['analysis'] if cached else None

    def cache_analysis(self, nct_id: str, analysis: Dict):
        """
        Cache LLM analysis result

        Args:
            nct_id: Trial NCT ID
            analysis: Analysis result
        """
        self.cache_table.insert({
            'nct_id': nct_id,
            'analysis': analysis,
            'cached_at': format_timestamp()
        })

    def print_statistics(self):
        """Print analysis statistics"""
        print("\n" + "="*50)
        print("ANALYSIS STATISTICS")
        print("="*50)
        print(f"Total Tokens Used: {self.total_tokens:,}")
        print(f"Estimated Cost: ${self.total_cost:.2f}")
        print(f"Average Tokens/Trial: {self.total_tokens // max(1, len(self.trials_table.all()))}")

    def close(self):
        """Close database connections"""
        self.db.close()
        self.cache_db.close()


def main():
    """Main entry point for LLM analysis"""
    parser = argparse.ArgumentParser(
        description="LLM-based failure classification with self-verification"
    )
    parser.add_argument(
        '--db',
        default='data/clinical_trials.json',
        help='Path to TinyDB database'
    )
    parser.add_argument(
        '--cache',
        default='data/llm_analysis_cache.json',
        help='Path to LLM cache database'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of trials for testing'
    )

    args = parser.parse_args()

    analyzer = FailureAnalyzer(db_path=args.db, cache_path=args.cache)

    try:
        analyzer.analyze_all_pending(limit=args.limit)
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
