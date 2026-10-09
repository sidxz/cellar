from cellar.domain.screening_assay.assay_format import (
    ASSAY_FORMAT_BY_TARGET_TYPE,
    assay_format_for_targets,
)
from cellar.domain.screening_assay.enums import TargetType

BAO = "http://www.bioassayontology.org/bao#"


def test_every_target_type_is_mapped():
    assert set(ASSAY_FORMAT_BY_TARGET_TYPE) == set(TargetType)


def test_single_and_complex_targets():
    assert assay_format_for_targets([TargetType.SINGLE_PROTEIN]).term_id == f"{BAO}BAO_0000357"
    assert assay_format_for_targets([TargetType.PROTEIN_COMPLEX]).term_id == f"{BAO}BAO_0000223"
    assert (
        assay_format_for_targets([TargetType.DOMAIN, TargetType.SINGLE_PROTEIN]).label
        == "single protein format"
    )


def test_mixed_unknown_or_no_targets_give_no_format():
    assert assay_format_for_targets([TargetType.SINGLE_PROTEIN, TargetType.NUCLEIC_ACID]) is None
    assert assay_format_for_targets([TargetType.UNKNOWN]) is None
    assert assay_format_for_targets([]) is None
