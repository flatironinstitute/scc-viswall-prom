# FUTURE: should we plot CPUs or nodes?

from datetime import datetime
from pathlib import Path

import click
import matplotlib as mpl
import matplotlib.dates
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

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
@click.option(
    '--outfn',
    '-o',
    default=None,
    help='Output filename for the plot (default: usage_<timestamp>.png)',
)
def plot_usage(
    outfn: str | None = None, days: int = 7, step: str = '1h', dpi: int = 144
):
    # fmt: off
    # Gather data
    rusty_acct   = prom.get_usage_by("account", "rusty" , days, step)
    rusty_nodes  = prom.get_usage_by("nodes"  , "rusty" , days, step)
    rusty_gpus   = prom.get_usage_by("nodes"  , "rusty" , days, step, "gpus")
    popeye_acct  = prom.get_usage_by("account", "popeye", days, step)
    popeye_nodes = prom.get_usage_by("nodes"  , "popeye", days, step)
    popeye_gpus = prom.get_usage_by("nodes"  , "popeye" , days, step, "gpus")
    rusty_max  = prom.get_max_resource("rusty", days, step)
    rusty_max_gpus = prom.get_max_resource("rusty", days, step, "gpus")
    popeye_max = prom.get_max_resource("popeye", days, step)
    popeye_max_gpus = prom.get_max_resource("popeye", days, step, "gpus")
    # fmt: on

    initialize_colors(
        CENTER_COLOR_REGISTRY,
        unique_keys([rusty_acct, popeye_acct]),
        fixed=CENTER_COLORS,
    )
    initialize_colors(
        NODE_COLOR_REGISTRY, unique_keys([rusty_nodes, popeye_nodes])
    )

    fig, axes = plt.subplots(
        2,
        3,
        figsize=(1920 // dpi, 1080 // dpi),
        dpi=dpi,
        sharex=False,
        sharey=False,
        width_ratios=[7, 4, 2],
        layout='constrained',
    )
    layout_engine = fig.get_layout_engine()
    layout_params = layout_engine.get()
    rect = list(layout_params['rect'])
    rect[1] = 0.01  # bottom
    rect[3] = 0.99  # top
    layout_engine.set(rect=rect)

    _plot_stacked(
        axes,
        (0, 0),
        rusty_acct,
        rusty_max,
        'Rusty Usage by Center',
        CENTER_COLOR_REGISTRY,
    )
    _plot_bar_chart(
        axes,
        (0, 1),
        rusty_nodes,
        rusty_max,
        'Rusty Current CPU Usage',
        NODE_COLOR_REGISTRY,
    )
    _plot_bar_chart(
        axes,
        (0, 2),
        rusty_gpus,
        rusty_max_gpus,
        'Rusty Current GPUs',
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
    _plot_bar_chart(
        axes,
        (1, 1),
        popeye_nodes,
        popeye_max,
        'Popeye Current CPU Usage',
        NODE_COLOR_REGISTRY,
    )
    _plot_bar_chart(
        axes,
        (1, 2),
        popeye_gpus,
        popeye_max_gpus,
        'Popeye Current GPUs',
        NODE_COLOR_REGISTRY,
    )

    add_author(fig)
    add_timestamp(fig)

    if not outfn:
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
        ax_no_data(ax, title)
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
    ax.plot(x_vals, max_data['total'], label='Capacity', color='black', linestyle='-')
    ax.legend(loc='upper left', ncol=2, framealpha=0.95)
    ax.set_xlim(left=min(x_vals), right=max(x_vals))
    ax.set_ylim(top=max(max_data['total']) * 1.1)

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

    if pos[0] >= 1:
        ax.set_xlabel('Time')
    if pos[1] == 0:
        ax.set_ylabel('CPU Cores')
    if pos[1] >= 1:
        ax.tick_params(
            axis='y',
            which='both',
            labelleft=False,
            labelright=True,
            right=True,
        )

    add_subplot_title(ax, title)

    ax.yaxis.set_major_formatter(
        mpl.ticker.FuncFormatter(
            lambda x, pos: f'{x / 1_000:.0f} K' if x >= 1_000 else f'{x:.0f}'
        )
    )


def _plot_bar_chart(
    axes,
    pos: tuple[int, int],
    data: dict,
    max_data: list,
    title: str,
    color_registry: dict,
):
    """Plot an (unstacked) bar chart of one bar per node type, showing current CPUs allocated.
    In other words, this is a snapshot of the latest cluster state, not a timeline. The x values
    will be the node types, and the y values will be the number of CPUs allocated to each node type.
    Mark the max number of CPUs per node type as well.
    """
    ax: plt.Axes = axes[pos]
    if not data:
        ax_no_data(ax, title)
        return
    data.pop('timestamps')
    keys = list(data.keys())
    keys.sort()
    bar_data = [data[k][-1] for k in keys]
    max_bar_data = [max_data[k][-1] for k in keys]

    ax.set_ylim(top=max(max_bar_data) * 1.1)

    ax.bar(
        keys,
        bar_data,
        color=get_colors(color_registry, keys),
        label=keys,
    )

    # for capacity, draw a hollow bar
    ax.bar(
        keys,
        max_bar_data,
        color='none',
        # edgecolor=get_colors(color_registry, keys),
        edgecolor='black',
        linewidth=1.5,
        label='Capacity',
    )

    ax.tick_params(
        axis='both',
        which='both',
        left=True,
        right=True,
        top=True,
        bottom=True,
    )

    if pos[1] == 0:
        ax.set_ylabel('CPU Cores')
    if pos[1] >= 1:
        ax.tick_params(
            axis='y',
            which='both',
            labelleft=False,
            labelright=True,
            right=True,
        )

    add_subplot_title(ax, title)

    ax.yaxis.set_major_formatter(
        mpl.ticker.FuncFormatter(
            lambda x, pos: f'{x / 1_000:.0f} K' if x >= 1_000 else f'{x:.0f}'
        )
    )

def add_subplot_title(ax: plt.Axes, title: str):
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

def date_formatter(ts: float, pos=None) -> str:
    dt: datetime = mpl.dates.num2date(ts)
    month = dt.strftime('%b')
    day = dt.strftime('%d')

    return f'{month}{"." if month != "May" else ""} {day}'


def add_author(fig: plt.Figure):
    # Add text
    fig.text(
        0.976,
        0.01,
        'Made by your friends in SCC',
        fontweight='bold',
        verticalalignment='bottom',
        horizontalalignment='right',
    )

    img = Image.open('scc_icon.png')

    # Set a small height in pixels for the logo (similar to text height)
    height = 16
    width = int(height * (img.width / img.height))

    img_resized = img.resize((width, height), Image.Resampling.LANCZOS)
    logo_array = np.array(img_resized)

    x_position = fig.bbox.xmax - width - 14
    y_position = fig.bbox.ymin + 14

    fig.figimage(logo_array, x_position, y_position, zorder=10)


def add_timestamp(fig: plt.Figure):
    fig.text(
        0.01,
        0.01,
        datetime.now().strftime(r'%Y-%m-%d %-I:%M %p ET'),
        fontweight='bold',
        verticalalignment='bottom',
        horizontalalignment='left',
    )

def ax_no_data(ax: plt.Axes, title: str):
    ax.tick_params(
            left=False,
            bottom=False,
            labelleft=False,
            labelbottom=False,
        )
    add_subplot_title(ax, f'{title}\nNo Data')

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
