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


def test_persist_creates_backup(tmp_path: Path):
    cfg_path = make_sample_config(tmp_path)
    # ensure initial file exists
    assert cfg_path.exists()

    persist_ppm_to_config(5.5, config_path=str(cfg_path))

    # original file should still exist and have updated ppm
    loaded = config_module.load_config(cfg_path)
    assert loaded.ppm_correction == 6

    # There should be a backup file in the `backups/` directory with .bak- timestamp suffix
    backups_dir = cfg_path.parent / "backups"
    backups = list(backups_dir.glob(cfg_path.name + ".bak-*") )
    assert len(backups) >= 1
    # backup file should be non-empty
    assert backups[0].stat().st_size > 0
