# vizwall-prom

Generate plots of cluster usage data for the vizwall by scraping Prometheus.

## Usage
To check that the Prometheus query is working:

```console
uv run prom.py
```

To make the image with the plots:
```
uv run plot.py
```
