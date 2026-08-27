"""Enrichissement optionnel du transcript à partir du lexique RAG."""

import re

def enrich_transcript_with_acronyms(transcript: str, lexique_utile: list) -> str:
    """Injecte les définitions uniquement pour les correspondances exactes de casse."""
    if not lexique_utile or not transcript:
        return transcript

    enriched_transcript = transcript

    for definition in lexique_utile:
        if ":" in definition:
            parties = definition.split(":", 1)
            termes_bruts = parties[0].strip().split()
            
            if not termes_bruts:
                continue
                
            # On s'assure d'utiliser la version officielle (ex: "VA")
            terme_principal = termes_bruts[0]
            
            signification_complete = parties[1].strip()
            signification_courte = signification_complete.split(".")[0].strip()

            # Regex STRICTE (sensible à la casse par défaut)
            pattern = rf'\b({re.escape(terme_principal)})\b(?!\s*\()'
            replacement = rf'\1 ({signification_courte})'
            
            enriched_transcript = re.sub(pattern, replacement, enriched_transcript)

    return enriched_transcript