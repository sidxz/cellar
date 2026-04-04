"""Chemistry test helpers — known molecules for testing."""

from __future__ import annotations

# Well-known molecules for predictable test data
# Each tuple: (name, SMILES, InChI Key)
ASPIRIN = ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
CAFFEINE = ("caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O", "RYYVLZVUVIJVGH-UHFFFAOYSA-N")
ETHANOL = ("ethanol", "CCO", "LFQSCWFLJHTTHZ-UHFFFAOYSA-N")
BENZENE = ("benzene", "c1ccccc1", "UHOVQNZJYSORNB-UHFFFAOYSA-N")
GLUCOSE = ("glucose", "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O", "WQZGKKKJIJFFOK-GASJEMHNSA-N")


def known_smiles(name: str = "ethanol") -> str:
    """Return a known-valid SMILES for testing."""
    molecules = {m[0]: m[1] for m in [ASPIRIN, CAFFEINE, ETHANOL, BENZENE, GLUCOSE]}
    return molecules.get(name, ETHANOL[1])


def known_inchi_key(name: str = "ethanol") -> str:
    """Return a known InChI Key for testing."""
    molecules = {m[0]: m[2] for m in [ASPIRIN, CAFFEINE, ETHANOL, BENZENE, GLUCOSE]}
    return molecules.get(name, ETHANOL[2])
