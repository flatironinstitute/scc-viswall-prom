# TODO: actually need a global key -> color mapping
# TODO: figure out what to do about oversubscribed colors
# FUTURE: should we plot CPUs or nodes?

from datetime import datetime
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates
import click
import matplotlib.pyplot as plt

import prom

CENTER_COLORS = {
    'cca': '#CE3232',
    'ccb': '#81AD4A',
    'ccm': '#F6862D',
    'ccn': '#007F9D',
    'ccq': '#845B8E',
    'scc': '#8F8F8F',
}

CENTER_COLOR_REGISTRY = {}
NODE_COLOR_REGISTRY = {}

plt.rcParams['font.family'] = 'monospace'


@click.command()
@click.option(
    '--days',
    '-d',
    default=7,
    help='Number of days to look back from today',
)
@click.option(
    '--step',
    '-s',
    default='1h',
    help='Time step for the data points',
)
@click.option(
    '--dpi',
    '-p',
    default=120,
    help='DPI for the output plot',
)
def plot_usage(days: int = 7, step: str = '1h', dpi: int = 120):
    # fmt: off
    # Gather data
    rusty_acct   = prom.get_usage_by("account", "rusty" , days, step)
    rusty_nodes  = prom.get_usage_by("nodes"  , "rusty" , days, step)
    popeye_acct  = prom.get_usage_by("account", "popeye", days, step)
    popeye_nodes = prom.get_usage_by("nodes"  , "popeye", days, step)
    rusty_max  = prom.get_max_cpus("rusty", days, step)
    popeye_max = prom.get_max_cpus("popeye", days, step)
    # fmt: on

    initialize_colors(
        CENTER_COLOR_REGISTRY,
        unique_keys([rusty_acct, popeye_acct]),
        fixed=CENTER_COLORS,
    )
    initialize_colors(NODE_COLOR_REGISTRY, unique_keys([rusty_nodes, popeye_nodes]))

    fig, axes = plt.subplots(
        2, 2, figsize=(1920 // dpi, 1080 // dpi), dpi=dpi, sharex=True, sharey='row'
    )

    _plot_stacked(
        axes,
        (0, 0),
        rusty_acct,
        rusty_max,
        'Rusty Usage by Center',
        CENTER_COLOR_REGISTRY,
    )
    _plot_stacked(
        axes,
        (0, 1),
        rusty_nodes,
        rusty_max,
        'Rusty Usage by Node Type',
        NODE_COLOR_REGISTRY,
    )
    _plot_stacked(
        axes,
        (1, 0),
        popeye_acct,
        popeye_max,
        'Popeye Usage by Center',
        CENTER_COLOR_REGISTRY,
    )
    _plot_stacked(
        axes,
        (1, 1),
        popeye_nodes,
        popeye_max,
        'Popeye Usage by Node Type',
        NODE_COLOR_REGISTRY,
    )

    fig.tight_layout()
    timestamp = datetime.now().strftime(r'%Y-%m-%d_%H%M%S')
    outfn = Path(f'usage_{timestamp}.png')
    fig.savefig(outfn)

    print(f'Saved plot to {outfn}')

    latest = Path('usage-latest.png')
    latest.unlink(missing_ok=True)
    latest.symlink_to(outfn)


def _plot_stacked(
    axes,
    pos: tuple[int, int],
    data: dict,
    max_data: list,
    title: str,
    color_registry: dict,
):
    ax: plt.Axes = axes[pos]
    if not data:
        ax.set_title(f'{title}\nNo Data')
        return
    x_vals = data.pop('timestamps')
    keys = list(data.keys())
    keys.sort(key=lambda k: data[k][-1], reverse=True)
    # Create X values and prepare the stacked data
    stack_data = [data[k] for k in keys]

    ax.stackplot(
        x_vals,
        stack_data,
        labels=keys,
        colors=get_colors(color_registry, keys),
    )
    ax.plot(x_vals, max_data, label='Capacity', color='black', linestyle='-')
    ax.legend(loc='upper left', ncol=2, framealpha=0.95)
    ax.set_xlim(left=min(x_vals), right=max(x_vals))
    ax.set_ylim(top=max(max_data) * 1.1)

    # format x-axis labels as dates
    ax.xaxis.set_major_formatter(date_formatter)
    ax.xaxis.set_major_locator(mpl.dates.DayLocator(interval=1))

    ax.tick_params(
        axis='both',
        which='both',
        left=True,
        right=True,
        top=True,
        bottom=True,
    )

    if pos[0] == 1:
        ax.set_xlabel('Time')
    if pos[1] == 0:
        ax.set_ylabel('CPU Cores')
    if pos[1] == 1:
        ax.tick_params(
            axis='y',
            which='both',
            labelleft=False,
            labelright=True,
            right=True,
        )

    ax.text(
        0.98,
        0.98,
        title,
        transform=ax.transAxes,
        fontsize='larger',
        fontweight='bold',
        verticalalignment='top',
        horizontalalignment='right',
    )

    ax.yaxis.set_major_formatter(
        mpl.ticker.FuncFormatter(
            lambda x, pos: f'{x / 1_000:.0f} K' if x >= 1_000 else f'{x:.0f}'
        )
    )


def date_formatter(ts: float, pos=None) -> str:
    dt: datetime = mpl.dates.num2date(ts)
    month = dt.strftime('%b')
    day = dt.strftime('%d')

    return f'{month}{"." if month != "May" else ""} {day}'


def unique_keys(dicts: list[dict]) -> set[str]:
    """Get a set of unique keys from a list of dictionaries"""
    keys = set()
    for d in dicts:
        keys.update(d.keys())
    return keys


def get_colors(registry, keys: list[str]) -> list[str]:
    """Get colors for the given keys using the global KEY_TO_COLOR mapping."""
    return [registry[key] for key in keys]


def initialize_colors(
    registry: dict, keys: set[str], fixed=None, fallback_cmap='tab10'
):
    """Initialize global color mapping for all keys across all subplots"""

    if fixed:
        for key in keys:
            if key.lower() in fixed:
                registry[key] = fixed[key.lower()]

    # Then, assign tab10 colors to remaining keys (sorted alphabetically)
    fallback_cmap = mpl.colormaps[fallback_cmap]
    remaining_keys = sorted([k for k in keys if k not in registry])

    for idx, key in enumerate(remaining_keys):
        registry[key] = fallback_cmap(idx % len(fallback_cmap.colors))


if __name__ == '__main__':
    plot_usage()
