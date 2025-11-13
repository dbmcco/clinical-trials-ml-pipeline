# ABOUTME: Shared utilities for clinical trials ML pipeline

import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


def safe_sleep(seconds: float):
    """Sleep with rate limiting for API calls"""
    time.sleep(seconds)


def calculate_exponential_backoff(retry_count: int, base_minutes: int = 5) -> datetime:
    """
    Calculate next retry time with exponential backoff

    Args:
        retry_count: Number of retries so far
        base_minutes: Base backoff time in minutes

    Returns:
        Next retry timestamp
    """
    backoff_minutes = base_minutes * (2 ** retry_count)
    return datetime.utcnow() + timedelta(minutes=backoff_minutes)


def extract_uniprot_ids(trial: Dict) -> List[str]:
    """
    Extract all UniProt IDs from trial enrichment data

    Args:
        trial: Trial document from TinyDB

    Returns:
        List of unique UniProt IDs
    """
    uniprot_ids = []

    chembl_enrichment = trial.get('chembl_enrichment', {})
    if chembl_enrichment.get('has_uniprot_targets'):
        for target in chembl_enrichment.get('targets', []):
            uid = target.get('uniprot_id')
            if uid and uid not in uniprot_ids:
                uniprot_ids.append(uid)

    return uniprot_ids


def get_ic50_values(trial: Dict) -> List[float]:
    """
    Extract all IC50 values from trial targets

    Args:
        trial: Trial document from TinyDB

    Returns:
        List of IC50 values in nM
    """
    ic50_values = []

    chembl_enrichment = trial.get('chembl_enrichment', {})
    for target in chembl_enrichment.get('targets', []):
        for ic50 in target.get('ic50_values', []):
            if ic50.get('units') == 'nM':
                ic50_values.append(ic50.get('value'))

    return ic50_values


def classify_sponsor(sponsor_name: Optional[str]) -> str:
    """
    Classify sponsor as industry, academic, or government

    Args:
        sponsor_name: Sponsor name from AACT

    Returns:
        Sponsor type classification
    """
    if not sponsor_name:
        return "unknown"

    sponsor_lower = sponsor_name.lower()

    # Industry keywords
    industry_keywords = [
        'pharma', 'therapeutics', 'biotech', 'inc', 'ltd',
        'corporation', 'labs', 'gmbh', 'ag', 'sa'
    ]
    if any(kw in sponsor_lower for kw in industry_keywords):
        return "industry"

    # Academic keywords
    academic_keywords = [
        'university', 'college', 'institute', 'medical center',
        'hospital', 'clinic'
    ]
    if any(kw in sponsor_lower for kw in academic_keywords):
        return "academic"

    # Government keywords
    govt_keywords = ['nih', 'niaid', 'nci', 'nhlbi', 'national']
    if any(kw in sponsor_lower for kw in govt_keywords):
        return "government"

    return "other"


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """
    Format timestamp for consistent database storage

    Args:
        dt: Datetime object (default: current time)

    Returns:
        ISO format timestamp string
    """
    if dt is None:
        dt = datetime.utcnow()
    return dt.isoformat()


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO format timestamp string

    Args:
        timestamp_str: ISO format timestamp

    Returns:
        Datetime object
    """
    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
