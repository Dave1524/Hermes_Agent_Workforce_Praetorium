# Fixture runbook

## Job wiring

| unit | when | runner |
|---|---|---|
| alpha | Sun 09:00 | bin/run_alpha_cc.sh |
| beta | Mon-Fri 06:00 | bin/run_beta_cc.sh |
| gamma | Tue 03:00 / Sat 22:00 | bin/run_gamma_cc.sh |
