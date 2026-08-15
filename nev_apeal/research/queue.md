# Research Queue

Queue is the Agent's prioritized unresolved-question list. Each round should select one highest-priority `open` item, execute the smallest sufficient analysis, append evidence, and update state.

Use:

```bash
python nev_apeal/cli.py research next --topic topic_x
python nev_apeal/cli.py research stop-check --topic topic_x
```
