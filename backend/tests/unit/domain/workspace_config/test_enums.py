from cellar.domain.workspace_config.enums import FieldDataType, FieldTarget


class TestFieldDataType:
    def test_values(self) -> None:
        assert FieldDataType.TEXT == "text"
        assert FieldDataType.NUMBER == "number"
        assert FieldDataType.DATE == "date"
        assert FieldDataType.PICKLIST == "picklist"
        assert FieldDataType.FILE == "file"
        assert FieldDataType.BATCH_LINK == "batch_link"

    def test_is_str_enum(self) -> None:
        assert isinstance(FieldDataType.TEXT, str)


class TestFieldTarget:
    def test_values(self) -> None:
        assert FieldTarget.MOLECULE == "molecule"
        assert FieldTarget.BATCH == "batch"
        assert FieldTarget.SAMPLE == "sample"

    def test_is_str_enum(self) -> None:
        assert isinstance(FieldTarget.MOLECULE, str)
