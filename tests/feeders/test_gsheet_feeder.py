from typing import Type

import gspread
import pytest
from auto_archiver.modules.gsheet_feeder_db import GsheetsFeederDB
from auto_archiver.core import Metadata, Feeder


def test_setup_without_sheet_and_sheet_id(setup_module, mocker):
    # Ensure setup() raises AssertionError if neither sheet nor sheet_id is set.
    mocker.patch("gspread.service_account")
    with pytest.raises(ValueError):
        setup_module(
            "gsheet_feeder_db",
            {"service_account": "dummy.json", "sheet": None, "sheet_id": None},
        )


@pytest.fixture
def gsheet_feeder(setup_module, mocker) -> GsheetsFeederDB:
    config: dict = {
        "service_account": "dummy.json",
        "sheet": "test-auto-archiver",
        "sheet_id": None,
        "header": 1,
        "columns": {
            "url": "link",
            "status": "archive status",
            "folder": "destination folder",
            "archive": "archive location",
            "date": "archive date",
            "thumbnail": "thumbnail",
            "timestamp": "upload timestamp",
            "title": "upload title",
            "text": "text content",
            "screenshot": "screenshot",
            "hash": "hash",
            "pdq_hash": "perceptual hashes",
            "wacz": "wacz",
            "replaywebpage": "replaywebpage",
        },
        "allow_worksheets": set(),
        "block_worksheets": set(),
        "use_sheet_names_in_stored_paths": True,
    }
    mocker.patch("gspread.service_account")
    feeder = setup_module("gsheet_feeder_db", config)
    feeder.gsheets_client = mocker.MagicMock()
    return feeder


class MockWorksheet:
    """
    mimics the bits we need from gworksheet
    """

    class SheetSheet:
        title = "TestSheet"

    rows = [
        {"row": 2, "url": "http://example.com", "status": "", "folder": ""},
        {"row": 3, "url": "http://example.com", "status": "", "folder": ""},
        {"row": 4, "url": "", "status": "", "folder": ""},
        {"row": 5, "url": "https://another.com", "status": None, "folder": ""},
        {
            "row": 6,
            "url": "https://another.com",
            "status": "success",
            "folder": "some_folder",
        },
    ]

    def __init__(self):
        self.wks = self.SheetSheet()

    def count_rows(self):
        if not self.rows:
            return 0
        return max(r["row"] for r in self.rows)

    def get_cell(self, row, col_name, fresh=False):
        matching = next((r for r in self.rows if r["row"] == row), {})
        return matching.get(col_name, "")

    def get_cell_or_default(self, row, col_name, default):
        matching = next((r for r in self.rows if r["row"] == row), {})
        return matching.get(col_name, default)


def test__process_rows(gsheet_feeder: GsheetsFeederDB):
    testworksheet = MockWorksheet()
    metadata_items = list(gsheet_feeder._process_rows(testworksheet))
    assert len(metadata_items) == 3
    assert isinstance(metadata_items[0], Metadata)
    assert metadata_items[0].get("url") == "http://example.com"


def test__set_metadata(gsheet_feeder: GsheetsFeederDB):
    worksheet = MockWorksheet()
    metadata = Metadata()
    gsheet_feeder._set_context(metadata, worksheet, 1)
    assert metadata.get_context("gsheet") == {"row": 1, "worksheet": worksheet}


@pytest.mark.skip(reason="Not recognising folder column")
def test__set_metadata_with_folder_pickled(gsheet_feeder: GsheetsFeederDB, worksheet):
    gsheet_feeder._set_context(worksheet, 7)
    assert Metadata.get_context("gsheet") == {"row": 1, "worksheet": worksheet}


def test__set_metadata_with_folder(gsheet_feeder: GsheetsFeederDB):
    testworksheet = MockWorksheet()
    metadata = Metadata()
    testworksheet.wks.title = "TestSheet"
    gsheet_feeder._set_context(metadata, testworksheet, 6)
    assert metadata.get_context("gsheet") == {"row": 6, "worksheet": testworksheet}
    assert metadata.get_context("folder") == "some-folder/test-auto-archiver/testsheet"


@pytest.mark.usefixtures("setup_module")
@pytest.mark.parametrize(
    "sheet, sheet_id, expected_method, expected_arg, description",
    [
        ("TestSheet", None, "open", "TestSheet", "opening by sheet name"),
        (None, "ABC123", "open_by_key", "ABC123", "opening by sheet ID"),
    ],
)
def test_open_sheet_with_name_or_id(setup_module, sheet, sheet_id, expected_method, expected_arg, description, mocker):
    """Ensure open_sheet() correctly opens by name or ID based on configuration."""
    mock_service_account = mocker.patch("gspread.service_account")
    mock_client = mocker.MagicMock()
    mock_service_account.return_value = mock_client
    mock_client.open.return_value = "MockSheet"
    mock_client.open_by_key.return_value = "MockSheet"

    # Setup module with parameterized values
    feeder = setup_module(
        "gsheet_feeder_db",
        {"service_account": "dummy.json", "sheet": sheet, "sheet_id": sheet_id},
    )
    sheet_result = feeder.open_sheet()
    # Validate the correct method was called
    getattr(mock_client, expected_method).assert_called_once_with(expected_arg), f"Failed: {description}"
    assert sheet_result == "MockSheet", f"Failed: {description}"


@pytest.mark.usefixtures("setup_module")
def test_open_sheet_with_sheet_id(setup_module, mocker):
    """Ensure open_sheet() correctly opens a sheet by ID."""
    mock_service_account = mocker.patch("gspread.service_account")
    mock_client = mocker.MagicMock()
    mock_service_account.return_value = mock_client
    mock_client.open_by_key.return_value = "MockSheet"
    feeder = setup_module(
        "gsheet_feeder_db",
        {"service_account": "dummy.json", "sheet": None, "sheet_id": "ABC123"},
    )
    sheet = feeder.open_sheet()
    mock_client.open_by_key.assert_called_once_with("ABC123")
    assert sheet == "MockSheet"


def test_should_process_sheet(setup_module, mocker):
    mocker.patch("gspread.service_account")
    gdb = setup_module(
        "gsheet_feeder_db",
        {
            "service_account": "dummy.json",
            "sheet": "TestSheet",
            "sheet_id": None,
            "allow_worksheets": {"TestSheet", "Sheet2"},
            "block_worksheets": {"Sheet3"},
        },
    )
    assert gdb.should_process_sheet("TestSheet") is True
    assert gdb.should_process_sheet("Sheet3") is False
    # False if allow_worksheets is set
    assert gdb.should_process_sheet("AnotherSheet") is False


@pytest.mark.skip(reason="Requires a real connection")
class TestGSheetsFeederReal:
    """Testing GsheetsFeeder class"""

    module_name: str = "gsheet_feeder_db"
    feeder: GsheetsFeederDB
    # You must follow the setup process explain in the docs for this to work
    config: dict = {
        "service_account": "secrets/service_account.json",
        "sheet": "test-auto-archiver",
        "sheet_id": None,
        "header": 1,
        "columns": {
            "url": "link",
            "status": "archive status",
            "folder": "destination folder",
            "archive": "archive location",
            "date": "archive date",
            "thumbnail": "thumbnail",
            "timestamp": "upload timestamp",
            "title": "upload title",
            "text": "text content",
            "screenshot": "screenshot",
            "hash": "hash",
            "pdq_hash": "perceptual hashes",
            "wacz": "wacz",
            "replaywebpage": "replaywebpage",
        },
        "allow_worksheets": set(),
        "block_worksheets": set(),
        "use_sheet_names_in_stored_paths": True,
    }

    @pytest.fixture(autouse=True)
    def setup_feeder(self, setup_module):
        assert self.module_name is not None, "self.module_name must be set on the subclass"
        assert self.config is not None, "self.config must be a dict set on the subclass"
        self.feeder: Type[Feeder] = setup_module(self.module_name, self.config)

    def reset_test_sheet(self):
        """Clears test sheet and re-adds headers to ensure consistent test results."""
        client = gspread.service_account(self.config["service_account"])
        sheet = client.open(self.config["sheet"])
        worksheet = sheet.get_worksheet(0)
        worksheet.clear()
        worksheet.append_row(["Link", "Archive Status"])

    def test_setup(self):
        assert hasattr(self.feeder, "gsheets_client")

    def test_open_sheet_real_connection(self):
        """Ensure open_sheet() connects to a real Google Sheets instance."""
        sheet = self.feeder.open_sheet()
        assert sheet is not None, "open_sheet() should return a valid sheet instance"
        assert hasattr(sheet, "worksheets"), "Returned object should have worksheets method"

    def test_iter_yields_metadata_real_data(self):
        """Ensure __iter__() yields Metadata objects for real test sheet data."""
        self.reset_test_sheet()
        client = gspread.service_account(self.config["service_account"])
        sheet = client.open(self.config["sheet"])
        worksheet = sheet.get_worksheet(0)
        # Insert test rows as a temp method
        # Next we will refactor the feeder for better testing
        test_rows = [
            ["https://example.com", ""],
            ["", ""],
            ["https://example.com", "done"],
        ]
        worksheet.append_rows(test_rows)
        metadata_list = list(self.feeder)

        # Validate that only the first row is processed
        assert len(metadata_list) == 1
        assert metadata_list[0].metadata.get("url") == "https://example.com"


# TODO

# Test two sheets
# test two sheets with different columns
# test folder implementation
