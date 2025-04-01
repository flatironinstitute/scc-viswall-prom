# viswall-prom

Generate plots of cluster usage data for the viswall by scraping Prometheus.

## Usage
To check that the Prometheus query is working:

```console
uv run prom.py
```

To make the image with the plots:
```
uv run plot.py
```

## License
Apache-2.0
