"""Protocol naming settings: code prefix/width, home organism."""

import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings

MTB = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
    "label": "Mycobacterium tuberculosis",
    "ontology_source": "NCBITAXON",
}
HUMAN = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/9606",
    "label": "Homo sapiens",
    "ontology_source": "NCBITAXON",
}


class TestProtocolNamingSettings:
    def _settings(self):
        return WorkspaceSettings.create_default(workspace_id=uuid.uuid4())

    def test_defaults(self):
        s = self._settings()
        assert s.protocol_code_prefix == "PRT-"
        assert s.protocol_code_width == 5
        assert s.home_organisms == [] and s.home_organism_labels == frozenset()

    def test_update_merges_code_settings(self):
        s = self._settings()
        s.update(protocol_naming={"code_prefix": "ASY-"})
        s.update(protocol_naming={"code_width": 6})
        assert (s.protocol_code_prefix, s.protocol_code_width) == ("ASY-", 6)

    @pytest.mark.parametrize(
        "bad",
        [
            {"code_prefix": "prt-"},
            {"code_prefix": "P-"},
            {"code_width": 2},
            {"code_width": 9},
            {"code_width": True},
            {"colour": "red"},
        ],
    )
    def test_update_rejects_bad_values(self, bad):
        with pytest.raises(ValidationError):
            self._settings().update(protocol_naming=bad)

    def test_home_organism_is_not_set_through_update(self):
        with pytest.raises(ValidationError, match="home organism"):
            self._settings().update(
                protocol_naming={"home_organisms": [{"term_id": "x", "label": "y"}]}
            )
        with pytest.raises(ValidationError, match="home organism"):
            self._settings().update(
                protocol_naming={"home_organism": {"term_id": "x", "label": "y"}}
            )

    def test_set_home_organisms_and_clear(self):
        s = self._settings()
        s.set_home_organisms([MTB, HUMAN])
        labels = [t["label"] for t in s.home_organisms]
        assert labels == ["Mycobacterium tuberculosis", "Homo sapiens"]
        assert s.home_organism_labels == frozenset({"mycobacterium tuberculosis", "homo sapiens"})
        assert s.home_organism_count == 2
        s.update(protocol_naming={"code_width": 4})
        assert s.home_organism_count == 2  # update keeps them
        s.set_home_organisms([])
        assert s.home_organisms == [] and s.home_organism_count == 0

    def test_legacy_single_home_organism_reads_as_a_one_item_list(self):
        s = self._settings()
        s.protocol_naming = {"home_organism": MTB}
        assert s.home_organisms == [MTB]
        assert s.home_organism_labels == frozenset({"mycobacterium tuberculosis"})
        assert s.home_organism_count == 1

    def test_writing_the_list_removes_the_legacy_key(self):
        s = self._settings()
        s.protocol_naming = {"home_organism": MTB, "code_width": 6}
        s.set_home_organisms([HUMAN])
        assert "home_organism" not in s.protocol_naming
        assert s.protocol_naming["code_width"] == 6
        assert [t["label"] for t in s.home_organisms] == ["Homo sapiens"]

    def test_the_list_wins_over_a_stale_legacy_key(self):
        s = self._settings()
        s.protocol_naming = {"home_organism": MTB, "home_organisms": [HUMAN]}
        assert [t["label"] for t in s.home_organisms] == ["Homo sapiens"]

    def test_duplicates_collapse(self):
        s = self._settings()
        s.set_home_organisms([MTB, dict(MTB)])
        assert s.home_organism_count == 1

    def test_set_home_organisms_needs_id_and_label(self):
        with pytest.raises(ValidationError):
            self._settings().set_home_organisms([{"term_id": "", "label": "x"}])
