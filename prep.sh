#!/bin/bash

# Activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Run neo-rx command
neo-rx adsb listen