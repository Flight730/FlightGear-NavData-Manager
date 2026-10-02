import pytest

from flightgear_navdata_manager.domain.dme_channels import paired_vhf_mhz


@pytest.mark.parametrize(
    "channel, expected",
    [
        ("17X", 108.00), ("17Y", 108.05), ("59X", 112.20), ("59Y", 112.25),
        ("70X", 112.30), ("126Y", 117.95),
        # verified against FAA NAV.txt rows that list both channel and frequency
        ("88X", 114.10), ("78Y", 113.15), ("114Y", 116.75), ("77X", 113.00),
        (" 87x ", 114.00),
    ],
)
def test_paired_channels(channel, expected):
    assert paired_vhf_mhz(channel) == expected


@pytest.mark.parametrize("channel", ["1X", "16Y", "60X", "69Y", "127X", "0X", "88", "88Z", "", "ABC"])
def test_unpaired_or_invalid_channels_return_none(channel):
    assert paired_vhf_mhz(channel) is None
