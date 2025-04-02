# viswall-prom

Generate plots of cluster usage data for the viswall by scraping Prometheus.

## Usage
To check that the Prometheus query is working:

```console
uv run -m viswall_prom.prom
```

To make the image with the plots:
```console
uv run -m viswall_prom.plot
```

## License
Apache-2.0
