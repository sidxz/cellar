"""Common organism names and lab abbreviations -> NCBITaxon terms, resolved without BioPortal."""

from __future__ import annotations

from cellar.domain.shared.ontology import OntologyTerm

_TAXON_URI = "http://purl.bioontology.org/ontology/NCBITAXON/"

# alias (lowercase) -> (NCBITaxon id, preferred label).
# Preferred labels are not aliases unless listed.
COMMON_ORGANISM_NAMES: dict[str, tuple[str, str]] = {
    "human": ("9606", "Homo sapiens"),
    "mouse": ("10090", "Mus musculus"),
    "rat": ("10116", "Rattus norvegicus"),
    "dog": ("9615", "Canis lupus familiaris"),
    "cynomolgus": ("9541", "Macaca fascicularis"),
    "cyno": ("9541", "Macaca fascicularis"),
    "rabbit": ("9986", "Oryctolagus cuniculus"),
    "zebrafish": ("7955", "Danio rerio"),
    "yeast": ("4932", "Saccharomyces cerevisiae"),
    "e. coli": ("562", "Escherichia coli"),
    "ecoli": ("562", "Escherichia coli"),
    "mtb": ("1773", "Mycobacterium tuberculosis"),
    "pf": ("5833", "Plasmodium falciparum"),
    "pv": ("5855", "Plasmodium vivax"),
    "pb": ("5821", "Plasmodium berghei"),
    "p. berghei": ("5821", "Plasmodium berghei"),
    "s. aureus": ("1280", "Staphylococcus aureus"),
    "mrsa": ("1280", "Staphylococcus aureus"),
    "p. aeruginosa": ("287", "Pseudomonas aeruginosa"),
    "k. pneumoniae": ("573", "Klebsiella pneumoniae"),
    "a. baumannii": ("470", "Acinetobacter baumannii"),
    "m. abscessus": ("36809", "Mycobacteroides abscessus"),
    "mabs": ("36809", "Mycobacteroides abscessus"),
    "sars-cov-2": ("2697049", "Severe acute respiratory syndrome coronavirus 2"),
}


def match_common_organism(query: str) -> OntologyTerm | None:
    """The NCBITaxon term whose alias equals the query (trimmed, case-insensitive), if any."""
    hit = COMMON_ORGANISM_NAMES.get(query.strip().lower())
    if hit is None:
        return None
    taxon_id, label = hit
    uri = f"{_TAXON_URI}{taxon_id}"
    return OntologyTerm(term_id=uri, label=label, ontology_source="NCBITAXON", uri=uri)
