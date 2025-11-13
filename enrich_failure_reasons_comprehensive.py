#!/usr/bin/env python3
# ABOUTME: Comprehensive failure reason enrichment from multiple automated sources

import json
import argparse
import time
import os
import re
from typing import Dict, List, Optional
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from urllib.parse import quote_plus

load_dotenv()


class ComprehensiveFailureEnricher:
    """Enrich trials with failure reasons from multiple automated sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 Research Bot (Clinical Trials Analysis)'
        })

        # Database connection for AACT data
        self.db_conn = psycopg2.connect(
            host=os.getenv('AACT_DB_HOST'),
            port=os.getenv('AACT_DB_PORT'),
            database=os.getenv('AACT_DB_NAME'),
            user=os.getenv('AACT_DB_USER'),
            password=os.getenv('AACT_DB_PASSWORD')
        )

    def get_aact_detailed_description(self, nct_id: str) -> Optional[str]:
        """Get detailed study description from AACT database."""
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT description FROM ctgov.detailed_descriptions WHERE nct_id = %s",
                (nct_id,)
            )
            result = cursor.fetchone()
            cursor.close()

            if result and result['description']:
                return result['description']
            return None

        except Exception as e:
            print(f"      Error getting description: {e}")
            return None

    def get_aact_documents(self, nct_id: str) -> List[Dict]:
        """Get study documents URLs from AACT."""
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT document_type, url, comment
                FROM ctgov.documents
                WHERE nct_id = %s
            """, (nct_id,))
            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            print(f"      Error getting documents: {e}")
            return []

    def get_aact_sponsor(self, nct_id: str) -> Optional[Dict]:
        """Get lead sponsor information from AACT."""
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT name, agency_class
                FROM ctgov.sponsors
                WHERE nct_id = %s AND lead_or_collaborator = 'lead'
                LIMIT 1
            """, (nct_id,))
            result = cursor.fetchone()
            cursor.close()

            if result:
                return dict(result)
            return None

        except Exception as e:
            print(f"      Error getting sponsor: {e}")
            return None

    def search_pubmed(self, nct_id: str, drug_name: str) -> Optional[Dict]:
        """Enhanced PubMed search with better queries."""
        try:
            base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

            # Try multiple search strategies
            search_terms = [
                f'{nct_id}[SI]',  # Secondary ID search
                f'({nct_id}[Title/Abstract]) AND (clinical trial[Publication Type])',
                f'({drug_name}[Title/Abstract]) AND ({nct_id}[Text Word])'
            ]

            all_articles = []

            for term in search_terms:
                search_url = f"{base_url}/esearch.fcgi"
                search_params = {
                    'db': 'pubmed',
                    'term': term,
                    'retmode': 'json',
                    'retmax': 5
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

                            for pmid in id_list:
                                article = articles.get(pmid, {})
                                if article:
                                    all_articles.append({
                                        'pmid': pmid,
                                        'title': article.get('title', ''),
                                        'pubdate': article.get('pubdate', ''),
                                        'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                                        'search_strategy': term
                                    })

                time.sleep(0.1)  # Rate limiting

            if all_articles:
                # Deduplicate by PMID
                unique_articles = {a['pmid']: a for a in all_articles}.values()
                return {
                    'found': True,
                    'count': len(unique_articles),
                    'articles': list(unique_articles)
                }

            return None

        except Exception as e:
            print(f"      Error searching PubMed: {e}")
            return None

    def search_clinicaltrials_api(self, nct_id: str) -> Optional[Dict]:
        """Get detailed results from ClinicalTrials.gov API v2."""
        try:
            url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"

            response = self.session.get(url, timeout=15)

            if response.status_code == 200:
                data = response.json()

                protocol = data.get('protocolSection', {})
                status_module = protocol.get('statusModule', {})
                design_module = protocol.get('designModule', {})

                # Extract key information
                enrichment = {
                    'has_results': bool(status_module.get('resultsFirstPostDate')),
                    'why_stopped': status_module.get('whyStopped'),
                    'study_type': design_module.get('studyType'),
                    'phase_detail': design_module.get('phases', []),
                    'enrollment': status_module.get('statusVerificationDate')
                }

                # Get adverse events if available
                results_section = data.get('resultsSection', {})
                adverse_module = results_section.get('adverseEventsModule', {})

                if adverse_module:
                    enrichment['adverse_events'] = {
                        'frequency_threshold': adverse_module.get('frequencyThreshold'),
                        'serious_events_count': len(adverse_module.get('seriousEvents', {}).get('seriousEvents', [])),
                        'other_events_count': len(adverse_module.get('otherEvents', {}).get('otherEvents', []))
                    }

                # Get outcome measures
                outcomes_module = protocol.get('outcomesModule', {})
                if outcomes_module:
                    enrichment['primary_outcomes_count'] = len(outcomes_module.get('primaryOutcomes', []))
                    enrichment['secondary_outcomes_count'] = len(outcomes_module.get('secondaryOutcomes', []))

                return enrichment

            return None

        except Exception as e:
            print(f"      Error fetching ClinicalTrials.gov data: {e}")
            return None

    def search_company_website(self, sponsor_name: str, nct_id: str, drug_name: str) -> Dict:
        """Generate search URLs for company press releases."""
        if not sponsor_name:
            return {'status': 'no_sponsor'}

        # Clean sponsor name for searching
        clean_sponsor = re.sub(r'\(.*?\)', '', sponsor_name).strip()

        # Generate search URLs
        search_urls = {
            'google_news': f'https://www.google.com/search?q={quote_plus(f"{clean_sponsor} {nct_id} trial terminated OR failed")}&tbm=nws',
            'google_general': f'https://www.google.com/search?q={quote_plus(f"{clean_sponsor} {drug_name} {nct_id} clinical trial")}&tbm=nws',
            'company_search': f'https://www.google.com/search?q=site:{quote_plus(clean_sponsor.lower().replace(" ", ""))}.com+{nct_id}',
        }

        return {
            'status': 'search_urls_generated',
            'sponsor': sponsor_name,
            'search_urls': search_urls,
            'note': 'Automated scraping not implemented - use URLs for manual review if needed'
        }

    def classify_failure_reason(self, combined_text: str, why_stopped: str) -> Dict:
        """
        NLP-based classification of failure reason using combined text sources.
        Categories: EFFICACY, SAFETY, ADMINISTRATIVE, UNKNOWN
        """
        if not combined_text:
            combined_text = ''

        text_lower = combined_text.lower()
        why_stopped_lower = (why_stopped or '').lower()

        # Efficacy failure keywords
        efficacy_keywords = [
            'lack of efficacy', 'insufficient efficacy', 'no efficacy',
            'did not meet', 'failed to meet', 'endpoint not met',
            'futility', 'no clinical benefit', 'ineffective',
            'poor response', 'low response rate', 'no response',
            'no significant difference', 'did not demonstrate'
        ]

        # Safety failure keywords
        safety_keywords = [
            'adverse event', 'adverse effect', 'toxicity', 'toxic',
            'safety concern', 'safety issue', 'tolerability',
            'serious adverse', 'death', 'died', 'fatal',
            'unacceptable safety', 'safety signal', 'harm'
        ]

        # Administrative keywords
        admin_keywords = [
            'funding', 'sponsor', 'resource', 'enrollment',
            'recruitment', 'administrative', 'business decision',
            'slow enrollment', 'insufficient enrollment', 'accrual',
            'strategic', 'portfolio', 'business reasons'
        ]

        # Score each category
        efficacy_score = sum(1 for kw in efficacy_keywords if kw in text_lower or kw in why_stopped_lower)
        safety_score = sum(1 for kw in safety_keywords if kw in text_lower or kw in why_stopped_lower)
        admin_score = sum(1 for kw in admin_keywords if kw in text_lower or kw in why_stopped_lower)

        # Determine classification
        scores = {
            'FAILURE_EFFICACY': efficacy_score,
            'FAILURE_SAFETY': safety_score,
            'FAILURE_ADMINISTRATIVE': admin_score
        }

        max_score = max(scores.values())

        if max_score == 0:
            return {
                'category': 'FAILURE_UNKNOWN',
                'confidence': 'none',
                'scores': scores,
                'reasoning': 'No clear failure indicators found in text'
            }

        category = max(scores, key=scores.get)
        confidence = 'high' if max_score >= 3 else 'medium' if max_score >= 2 else 'low'

        return {
            'category': category,
            'confidence': confidence,
            'scores': scores,
            'reasoning': f'Matched {max_score} {category.lower()} keywords'
        }

    def enrich_trial(self, trial: Dict) -> Dict:
        """Comprehensive enrichment of a single trial."""
        nct_id = trial.get('nct_id', '')
        drug_name = trial.get('drug_name', '')

        print(f"\n[ENRICHING] {nct_id} - {drug_name}")

        enrichment = {
            'sources_checked': [],
            'sources_found': [],
            'combined_text': '',
            'data': {}
        }

        # Source 1: AACT Detailed Description
        print("  1. AACT detailed description...", end=' ')
        description = self.get_aact_detailed_description(nct_id)
        enrichment['sources_checked'].append('aact_description')
        if description and description.lower() != 'none':
            enrichment['sources_found'].append('aact_description')
            enrichment['data']['description'] = description[:500]  # First 500 chars
            enrichment['combined_text'] += f" {description}"
            print(f"✓ ({len(description)} chars)")
        else:
            print("✗")

        # Source 2: AACT Documents
        print("  2. AACT documents...", end=' ')
        documents = self.get_aact_documents(nct_id)
        enrichment['sources_checked'].append('aact_documents')
        if documents:
            enrichment['sources_found'].append('aact_documents')
            enrichment['data']['documents'] = documents
            print(f"✓ ({len(documents)} docs)")
        else:
            print("✗")

        # Source 3: AACT Sponsor
        print("  3. AACT sponsor...", end=' ')
        sponsor = self.get_aact_sponsor(nct_id)
        enrichment['sources_checked'].append('aact_sponsor')
        if sponsor:
            enrichment['sources_found'].append('aact_sponsor')
            enrichment['data']['sponsor'] = sponsor
            print(f"✓ ({sponsor['name']})")
        else:
            print("✗")

        # Source 4: PubMed Enhanced
        print("  4. PubMed search...", end=' ')
        pubmed = self.search_pubmed(nct_id, drug_name)
        enrichment['sources_checked'].append('pubmed')
        if pubmed and pubmed.get('found'):
            enrichment['sources_found'].append('pubmed')
            enrichment['data']['pubmed'] = pubmed
            # Add article titles to combined text
            for article in pubmed['articles']:
                enrichment['combined_text'] += f" {article['title']}"
            print(f"✓ ({pubmed['count']} articles)")
        else:
            print("✗")

        time.sleep(0.1)

        # Source 5: ClinicalTrials.gov API
        print("  5. ClinicalTrials.gov API...", end=' ')
        ct_data = self.search_clinicaltrials_api(nct_id)
        enrichment['sources_checked'].append('clinicaltrials_api')
        if ct_data:
            enrichment['sources_found'].append('clinicaltrials_api')
            enrichment['data']['clinicaltrials'] = ct_data
            if ct_data.get('why_stopped'):
                enrichment['combined_text'] += f" {ct_data['why_stopped']}"
            print(f"✓ (results={ct_data.get('has_results', False)})")
        else:
            print("✗")

        time.sleep(0.1)

        # Source 6: Company Website Search URLs
        print("  6. Company website search...", end=' ')
        if sponsor:
            company_search = self.search_company_website(
                sponsor.get('name'), nct_id, drug_name
            )
            enrichment['sources_checked'].append('company_website')
            enrichment['data']['company_search'] = company_search
            print(f"✓ (URLs generated)")
        else:
            print("✗ (no sponsor)")

        # NLP Classification
        print("  7. NLP classification...", end=' ')
        classification = self.classify_failure_reason(
            enrichment['combined_text'],
            trial.get('why_stopped')
        )
        enrichment['classification'] = classification
        print(f"{classification['category']} ({classification['confidence']} confidence)")

        # Add enrichment to trial
        trial['comprehensive_failure_enrichment'] = enrichment

        print(f"  ✓ Complete: {len(enrichment['sources_found'])}/{len(enrichment['sources_checked'])} sources found")

        return trial

    def enrich_trials(self, input_file: str, output_file: str, limit: Optional[int] = None):
        """Enrich all trials in file."""
        print(f"\n=== Comprehensive Failure Reason Enrichment ===")
        print(f"Loading from: {input_file}\n")

        with open(input_file, 'r') as f:
            trials = json.load(f)

        if limit:
            trials = trials[:limit]
            print(f"Limited to {len(trials)} trials\n")

        enriched = []

        for i, trial in enumerate(trials, 1):
            print(f"\n[{i}/{len(trials)}]", "="*60)
            enriched_trial = self.enrich_trial(trial)
            enriched.append(enriched_trial)

            # Save progress every 10 trials
            if i % 10 == 0:
                with open(output_file, 'w') as f:
                    json.dump(enriched, f, indent=2)
                print(f"\n  💾 Progress saved ({i} trials)")

        # Final save
        with open(output_file, 'w') as f:
            json.dump(enriched, f, indent=2)

        # Summary
        print(f"\n\n{'='*60}")
        print(f"=== SUMMARY ===")
        print(f"Total trials processed: {len(enriched)}")

        # Classification breakdown
        classifications = {}
        confidences = {'high': 0, 'medium': 0, 'low': 0, 'none': 0}

        for trial in enriched:
            enrichment = trial.get('comprehensive_failure_enrichment', {})
            classification = enrichment.get('classification', {})
            category = classification.get('category', 'UNKNOWN')
            confidence = classification.get('confidence', 'none')

            classifications[category] = classifications.get(category, 0) + 1
            confidences[confidence] = confidences.get(confidence, 0) + 1

        print(f"\nClassification breakdown:")
        for cat, count in sorted(classifications.items()):
            pct = (count / len(enriched)) * 100
            print(f"  {cat}: {count} ({pct:.1f}%)")

        print(f"\nConfidence levels:")
        for conf, count in sorted(confidences.items(), reverse=True):
            pct = (count / len(enriched)) * 100
            print(f"  {conf}: {count} ({pct:.1f}%)")

        print(f"\nOutput saved to: {output_file}")

        # Close database connection
        self.db_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Comprehensive failure reason enrichment from multiple sources'
    )
    parser.add_argument('--input', required=True, help='Input JSON file')
    parser.add_argument('--output', required=True, help='Output JSON file')
    parser.add_argument('--limit', type=int, help='Limit number of trials')

    args = parser.parse_args()

    enricher = ComprehensiveFailureEnricher()
    enricher.enrich_trials(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
