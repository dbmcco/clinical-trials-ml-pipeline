#!/usr/bin/env python3
# ABOUTME: Search for detailed trial failure information from company websites and press releases

import json
import argparse
import time
from typing import Dict, List, Optional
import requests
from urllib.parse import quote_plus


class FailureDetailSearcher:
    """Search for additional trial failure details from web sources."""

    def __init__(self):
        self.session = requests.Session()
        # Set a reasonable user agent
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Research Bot'
        })

    def search_google_news(self, nct_id: str, drug_name: str) -> List[Dict]:
        """
        Search Google News for press releases about trial termination.
        Note: This uses a basic approach - could enhance with NewsAPI or similar.
        """
        search_query = f'"{nct_id}" OR "{drug_name}" trial terminated OR failed'

        # For production, you'd want to use:
        # - NewsAPI (https://newsapi.org/)
        # - Google Custom Search API
        # - Bing News API
        # For now, return structure for manual enrichment

        return {
            'search_query': search_query,
            'google_url': f'https://www.google.com/search?q={quote_plus(search_query)}&tbm=nws',
            'note': 'Manual review recommended - use Google News search URL'
        }

    def search_pubmed(self, nct_id: str, drug_name: str) -> Optional[Dict]:
        """Search PubMed for trial results publications."""
        try:
            # PubMed E-utilities API
            base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

            # Search for articles
            search_url = f"{base_url}/esearch.fcgi"
            search_params = {
                'db': 'pubmed',
                'term': f'({nct_id}[SI]) OR ({drug_name}[Title/Abstract] AND clinical trial[Title/Abstract])',
                'retmode': 'json',
                'retmax': 10
            }

            response = self.session.get(search_url, params=search_params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                id_list = data.get('esearchresult', {}).get('idlist', [])

                if id_list:
                    # Fetch article details
                    fetch_url = f"{base_url}/esummary.fcgi"
                    fetch_params = {
                        'db': 'pubmed',
                        'id': ','.join(id_list),
                        'retmode': 'json'
                    }

                    fetch_response = self.session.get(fetch_url, params=fetch_params, timeout=10)

                    if fetch_response.status_code == 200:
                        articles = fetch_response.json().get('result', {})

                        # Extract article titles and PMIDs
                        results = []
                        for pmid in id_list:
                            article = articles.get(pmid, {})
                            if article:
                                results.append({
                                    'pmid': pmid,
                                    'title': article.get('title', ''),
                                    'pubdate': article.get('pubdate', ''),
                                    'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'
                                })

                        return {
                            'found': True,
                            'count': len(results),
                            'articles': results
                        }

            return None

        except Exception as e:
            print(f"  Error searching PubMed: {e}")
            return None

    def search_clinicaltrials_docs(self, nct_id: str) -> Optional[Dict]:
        """
        Check if trial has detailed results posted on ClinicalTrials.gov.
        """
        try:
            # ClinicalTrials.gov API
            url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Check for detailed results
                has_results = data.get('protocolSection', {}).get('statusModule', {}).get('resultsFirstPostDate')

                # Get study documents
                docs = data.get('documentSection', {}).get('largeDocumentModule', {}).get('largeDocs', [])

                # Get design details
                design = data.get('protocolSection', {}).get('designModule', {})

                # Get adverse events if available
                adverse_events = data.get('resultsSection', {}).get('adverseEventsModule', {})

                return {
                    'has_posted_results': bool(has_results),
                    'documents': [
                        {
                            'type': doc.get('typeAbbrev'),
                            'url': doc.get('url'),
                            'date': doc.get('date')
                        }
                        for doc in docs
                    ],
                    'adverse_events_summary': {
                        'serious_events': adverse_events.get('seriousEvents', {}),
                        'other_events': adverse_events.get('otherEvents', {})
                    } if adverse_events else None
                }

            return None

        except Exception as e:
            print(f"  Error fetching trial docs: {e}")
            return None

    def enrich_trial_details(self, trial: Dict) -> Dict:
        """Enrich a trial with additional failure detail sources."""
        nct_id = trial.get('nct_id', '')
        drug_name = trial.get('drug_name', '')

        print(f"\nSearching additional sources for: {nct_id} - {drug_name}")

        enrichment = {}

        # Search PubMed
        print("  - Searching PubMed...")
        pubmed_results = self.search_pubmed(nct_id, drug_name)
        if pubmed_results and pubmed_results.get('found'):
            print(f"    ✓ Found {pubmed_results['count']} publications")
            enrichment['pubmed'] = pubmed_results
        else:
            print("    - No publications found")

        # Get detailed trial docs
        print("  - Checking ClinicalTrials.gov for detailed results...")
        trial_docs = self.search_clinicaltrials_docs(nct_id)
        if trial_docs:
            has_results = trial_docs.get('has_posted_results', False)
            doc_count = len(trial_docs.get('documents', []))
            print(f"    {'✓' if has_results else '-'} Posted results: {has_results}")
            print(f"    {'✓' if doc_count > 0 else '-'} Documents: {doc_count}")
            enrichment['clinicaltrials_details'] = trial_docs

        # Add Google News search URL for manual review
        news_search = self.search_google_news(nct_id, drug_name)
        enrichment['news_search'] = news_search
        print(f"    ℹ Manual review URL: {news_search['google_url']}")

        trial['failure_detail_enrichment'] = enrichment

        # Rate limiting (reduced from 0.5s to 0.1s for faster processing)
        time.sleep(0.1)

        return trial

    def enrich_failed_trials(self, input_file: str, output_file: str, limit: Optional[int] = None):
        """Enrich all failed trials with additional detail sources."""
        print(f"Loading trials from {input_file}...")

        with open(input_file, 'r') as f:
            trials = json.load(f)

        # Filter to failures only
        failures = [t for t in trials if t.get('label') == 'FAILURE']

        print(f"Found {len(failures)} failed trials")

        if limit:
            print(f"Limiting to first {limit} trials for testing")
            failures = failures[:limit]

        enriched = []

        for i, trial in enumerate(failures):
            print(f"\n[{i+1}/{len(failures)}]", end=' ')

            enriched_trial = self.enrich_trial_details(trial)
            enriched.append(enriched_trial)

            # Save progress every 20 trials
            if (i + 1) % 20 == 0:
                with open(output_file, 'w') as f:
                    json.dump(enriched, f, indent=2)
                print(f"\n  💾 Progress saved")

        # Final save
        with open(output_file, 'w') as f:
            json.dump(enriched, f, indent=2)

        # Summary
        print(f"\n\n=== Summary ===")
        print(f"Enriched {len(enriched)} failed trials")

        with_pubmed = sum(
            1 for t in enriched
            if t.get('failure_detail_enrichment', {}).get('pubmed', {}).get('found')
        )
        with_docs = sum(
            1 for t in enriched
            if t.get('failure_detail_enrichment', {}).get('clinicaltrials_details', {}).get('has_posted_results')
        )

        print(f"  Trials with PubMed publications: {with_pubmed}")
        print(f"  Trials with posted results: {with_docs}")
        print(f"\nOutput saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Search for additional trial failure details from web sources'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input JSON file (from classify_failures.py or enrich_targets.py)'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output JSON file with enriched failure details'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of trials to process (for testing)'
    )

    args = parser.parse_args()

    searcher = FailureDetailSearcher()
    searcher.enrich_failed_trials(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
