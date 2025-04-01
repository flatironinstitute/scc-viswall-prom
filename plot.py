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
    rusty_max      = prom.get_max_resource("rusty", days, step)
    rusty_max_gpus = prom.get_max_resource("rusty", days, step, "gpus")
    popeye_max     = prom.get_max_resource("popeye", days, step)
    # fmt: on

    initialize_colors(
        CENTER_COLOR_REGISTRY,
        unique_keys([rusty_acct, popeye_acct]),
        fixed=CENTER_COLORS,
    )
    initialize_colors(NODE_COLOR_REGISTRY, unique_keys([rusty_nodes, popeye_nodes]))

    fig, axes = plt.subplots(
        2,
        3,
        figsize=(1920 // dpi, 1080 // dpi),
        dpi=dpi,
        sharex=False,
        sharey=False,
        width_ratios=[8, 5, 2],
        layout='constrained',
    )

    _plot_stacked(
        axes,
        (0, 0),
        rusty_acct,
        rusty_max,
        'Rusty CPU Usage by Center',
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
        'Rusty GPUs',
        NODE_COLOR_REGISTRY,
    )
    _plot_stacked(
        axes,
        (1, 0),
        popeye_acct,
        popeye_max,
        'Popeye CPU Usage by Center',
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
    _logo_plot(
        axes,
        (1, 2),
    )

    if not outfn:
        timestamp = datetime.now().strftime(r'%Y-%m-%d_%H%M%S')
        outfn = Path(f'usage_{timestamp}.png')

        latest = outfn.with_stem('usage-latest')
        latest.unlink(missing_ok=True)
        latest.symlink_to(outfn)
    else:
        outfn = Path(outfn)
    fig.savefig(outfn)

    print(f'Saved plot to {outfn}')


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
    """Plot an (unstacked) bar chart of one bar per node type, showing current CPUs
    allocated. In other words, this is a snapshot of the latest cluster state, not a
    timeline. The capacity is shown as a hollow bar on top of the solid bars.
    """
    ax: plt.Axes = axes[pos]
    if not data:
        ax_no_data(ax, title)
        return
    data.pop('timestamps')
    keys = list(data.keys())

    # remove keys with zero max
    keys = [k for k in keys if max_data[k][-1] > 0]

    keys.sort()
    max_bar_data = [max_data[k][-1] for k in keys]

    bar_data = [data[k][-1] for k in keys]

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


def _logo_plot(axes, pos: tuple[int, int]):
    ax: plt.Axes = axes[pos]
    ax.set_axis_off()

    # Get figure and axes dimensions
    fig = ax.get_figure()
    fig.canvas.draw()
    ax_bbox = ax.get_position()

    # Load the image
    img = Image.open('scc_icon.png')

    # Calculate image dimensions and position in figure coordinates
    ratio = 0.05
    img_aspect = img.width / img.height

    # Resize the image
    display_height = int(fig.bbox.height * ratio)
    display_width = int(display_height * img_aspect)
    img_resized = img.resize((display_width, display_height), Image.Resampling.LANCZOS)

    # Position in figure coordinates (center of axes + vertical offset)
    yoff = 0.0
    x_center = (ax_bbox.x0 + ax_bbox.width / 2) * fig.bbox.width
    y_center = (ax_bbox.y0 + ax_bbox.height / 2 + yoff) * fig.bbox.height

    # Convert image to array and display
    fig.figimage(
        np.array(img_resized), xo=x_center - img_resized.width / 2, yo=y_center - img_resized.height / 2, origin='upper'
    )

    # text above the logo
    text_yoff = 0.05
    fig.text(
        x_center / fig.bbox.width,
        y_center / fig.bbox.height + text_yoff,
        'Made by\nyour friends\nin SCC',
        transform=fig.transFigure,
        fontweight='bold',
        verticalalignment='bottom',
        horizontalalignment='center',
        fontsize='larger',
        color='black',
    )

    datetext = datetime.now().strftime(r'%Y-%m-%d')
    timetext = datetime.now().strftime(r'%-I:%M %p ET')

    # timestamp below the logo
    fig.text(
        x_center / fig.bbox.width,
        y_center / fig.bbox.height - text_yoff,
        f'Last updated:\n{timetext}\n{datetext}',
        transform=fig.transFigure,
        fontweight='bold',
        verticalalignment='top',
        horizontalalignment='center',
        fontsize='larger',
        color='black',
    )


def add_subplot_title(ax: plt.Axes, title: str):
    ax.annotate(
        title,
        xy=(1, 1),
        xycoords='axes fraction',
        xytext=(-0.5, -0.5),
        textcoords='offset fontsize',
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
