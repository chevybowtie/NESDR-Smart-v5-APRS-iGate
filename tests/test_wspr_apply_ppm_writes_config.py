import tempfile
from pathlib import Path

from neo_rx import config as config_module
from neo_rx.wspr.calibrate import persist_ppm_to_config


def make_sample_config(tmp_path: Path) -> Path:
    cfg = config_module.StationConfig(
        callsign="TEST",
        passcode="12345",
        passcode_in_keyring=False,
    )
    p = tmp_path / "config.toml"
    config_module.save_config(cfg, p)
    return p


def test_apply_ppm_writes_config(tmp_path):
    cfg_path = make_sample_config(tmp_path)
    # Persist a ppm (float) into config
    persist_ppm_to_config(12.7, config_path=str(cfg_path))
    # Reload config and check ppm_correction stored (rounded)
    loaded = config_module.load_config(cfg_path)
    assert loaded.ppm_correction == 13
