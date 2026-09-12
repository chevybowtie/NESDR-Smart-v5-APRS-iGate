
```
make setup
source .venv/bin/activate
neo-rx --version
neo-rx aprs setup
```

During setup, configure the radio frequency as the actual APRS frequency you want to monitor—normally 144.390 MHz. Then validate:

```
neo-rx aprs diagnostics --verbose
```

Start decoding without sending anything to APRS-IS:

```
neo-rx aprs listen --no-aprsis
```

For a one-packet test:

```
neo-rx aprs listen --no-aprsis --once
```

Decoded frames are printed to the terminal and logged under:
```
~/.local/share/neo-rx/logs/aprs/neo-rx.log
```

Before starting, stop any other program using the dongle. 