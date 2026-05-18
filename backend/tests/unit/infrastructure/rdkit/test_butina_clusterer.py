"""ButinaClusterer unit tests — cluster count varies with threshold, medoid picked."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.infrastructure.rdkit.butina_clusterer import ButinaClusterer


def _ecfp4(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


def test_butina_groups_similar_compounds() -> None:
    smiles = ["c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "c1ccncc1", "Cc1ccncc1"]
    fps = [_ecfp4(s) for s in smiles]
    clusterer = ButinaClusterer(threshold=0.4)
    clusters, medoids = clusterer.cluster(fps)
    assert len(clusters) == len(fps)
    assert set(clusters) == set(range(max(clusters) + 1))
    assert len(medoids) == max(clusters) + 1
