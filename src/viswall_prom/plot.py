# FUTURE: should we plot CPUs or nodes?

from datetime import datetime
from importlib.resources import files
from pathlib import Path

import matplotlib as mpl

mpl.use('Agg')

import click
import matplotlib.colors
import matplotlib.dates
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from . import prom

CPU_PERCENT_THRESHOLD = 0.1

CENTER_COLORS = {
    'cca': '#CE3232',
    'ccb': '#81AD4A',
    'ccm': '#F6862D',
    'ccn': '#007F9D',
    'ccq': '#845B8E',
    'scc': '#8F8F8F',
    'Others': '#537EBA',
    'flatiron': '#537EBA',
}

CYCLE_OTHERS = matplotlib.colors.ListedColormap(
    ['#5A6D5A', '#A7856A', '#6B879F', '#AA9F8A', '#6B5F90']
)

HIDE_CPU = {
    'eval',
    'gpu',
    'gpuxl',
    'mem',
}

HIDE_GPU = {
    'v100-sxm2-32gb',
}

NICKNAME = {
    'a100-sxm4-80gb': 'a100-80gb',
    'a100-sxm4-40gb': 'a100-40gb',
}

AXIS_LABEL_FONT = {'fontweight': 'bold'}

plt.rcParams['font.family'] = 'monospace'

CENTER_COLOR_REGISTRY = {}
NODE_COLOR_REGISTRY = {}


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
    rusty_gpus   = prom.get_usage_by("gputype"  , "rusty" , 0, '', "gpus")
    popeye_acct  = prom.get_usage_by("account", "popeye", days, step)
    popeye_nodes = prom.get_usage_by("nodes"  , "popeye", days, step)
    rusty_max      = prom.get_max_resource("rusty", days, step)
    rusty_max_gpus = prom.get_max_resource("rusty", 0, '', "gpus", "gputype")
    popeye_max     = prom.get_max_resource("popeye", days, step)
    # fmt: on

    initialize_colors(
        CENTER_COLOR_REGISTRY,
        unique_keys([rusty_acct, popeye_acct]),
        fixed=CENTER_COLORS,
    )
    initialize_colors(
        NODE_COLOR_REGISTRY, unique_keys([rusty_nodes, popeye_nodes, rusty_max_gpus])
    )
    # node_colors = NODE_COLOR_REGISTRY
    node_colors = CENTER_COLORS['flatiron']

    fig, axes = plt.subplots(
        2,
        3,
        figsize=(1920 // dpi, 1080 // dpi),
        dpi=dpi,
        sharex=False,
        sharey=False,
        width_ratios=[12, 4, 4],
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
        select_last(rusty_nodes),
        select_last(rusty_max),
        'Rusty Current CPU Usage',
        node_colors,
        hide=HIDE_CPU,
        legend=False,  # do we need a legend for the bar charts?
    )
    _plot_bar_chart(
        axes,
        (0, 2),
        rusty_gpus,
        rusty_max_gpus,
        'Rusty Current GPU Usage',
        stagger_xlabels=True,
        colors=node_colors,
        hide=HIDE_GPU,
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
        select_last(popeye_nodes),
        select_last(popeye_max),
        'Popeye Current CPU Usage',
        node_colors,
        hide=HIDE_CPU,
    )
    _logo_plot(
        axes,
        (1, 2),
    )

    if not outfn:
        timestamp = datetime.now().strftime(r'%Y-%m-%d_%H%M%S')
        outfn = Path(f'usage_{timestamp}.png')
    else:
        outfn = Path(outfn)

    # Freeze the layout, then add the xlabel
    # Couldn't figure out how otherwise exclude the xlabel from the spacing calculation
    fig.canvas.draw()
    fig.set_layout_engine('none')
    axes[0, 2].set_xlabel('GPU Type', fontweight='bold')

    fig.savefig(outfn)

    print(f'Saved plot to {outfn}')


def _plot_stacked(
    axes,
    pos: tuple[int, int],
    data: dict,
    max_data: list,
    title: str,
    color_registry: dict,
    cdf_threshold: float = CPU_PERCENT_THRESHOLD,
):
    ax: plt.Axes = axes[pos]
    if not data:
        ax_no_data(ax, title)
        return
    x_vals = data.pop('timestamps')
    data = sort_and_group(data, cdf_threshold)
    keys = list(data.keys())
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
        ax.set_xlabel('Time', **AXIS_LABEL_FONT)
    if pos[1] == 0:
        ax.set_ylabel('CPU Cores', **AXIS_LABEL_FONT)
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
    colors: dict | str | None = None,
    hide: set = None,
    stagger_xlabels: bool = False,
    legend: bool = False,
):
    """Plot an (unstacked) bar chart of one bar per node type, showing current CPUs
    allocated. In other words, this is a snapshot of the latest cluster state, not a
    timeline. The capacity is shown as a hollow bar on top of the solid bars.
    """
    ax: plt.Axes = axes[pos]
    if not data:
        ax_no_data(ax, title)
        return
    data.pop('timestamps', None)
    keys = list(data.keys())

    # remove keys with zero max
    keys = [k for k in keys if max_data[k] > 0]

    # remove keys that are hidden
    if hide:
        keys = [k for k in keys if k not in hide]

    keys.sort()

    max_data = [max_data[k] for k in keys]
    data = [data[k] for k in keys]

    ax.set_ylim(top=max(max_data) * 1.1)

    if isinstance(colors, dict):
        colors = get_colors(colors, keys)

    keylabels = [NICKNAME.get(k, k) for k in keys]

    ax.bar(
        keys,
        data,
        color=colors,
        tick_label=keylabels,
        label='Usage',
    )

    # for capacity, draw a hollow bar
    ax.bar(
        keys,
        max_data,
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
        ax.set_ylabel('CPU Cores', **AXIS_LABEL_FONT)
    if pos[1] == 1:
        # Sadly constrained layout doesn't seem to be aware of the right-side label,
        # hence the need for labelpad
        ax.set_ylabel('CPU Cores', rotation=270, labelpad=15, **AXIS_LABEL_FONT)
        ax.yaxis.set_label_position('right')
    if pos[1] == 2:
        ax.set_ylabel('GPUs', rotation=270, labelpad=15, **AXIS_LABEL_FONT)
        ax.yaxis.set_label_position('right')
    if pos[1] >= 1:
        ax.tick_params(
            axis='y',
            which='both',
            labelleft=False,
            labelright=True,
            right=True,
        )
    if pos[1] == 1 and pos[0] == len(axes) - 1:
        ax.set_xlabel('CPU Type', fontweight='bold')
    if pos[1] == 2:
        # This is deferred to later
        # ax.set_xlabel('GPU Type', fontweight='bold')
        pass
    add_subplot_title(ax, title)

    if legend:
        ax.legend()

    ax.yaxis.set_major_formatter(
        mpl.ticker.FuncFormatter(
            lambda x, pos: f'{x / 1_000:.0f} K' if x >= 1_000 else f'{x:.0f}'
        )
    )

    if stagger_xlabels:
        labels = [label.get_text() for label in ax.get_xticklabels()]
        new_labels = ['\n' + L if i % 2 else L for i, L in enumerate(labels)]
        ax.set_xticklabels(new_labels)


def _logo_plot(axes, pos: tuple[int, int]):
    ax: plt.Axes = axes[pos]
    ax.set_axis_off()

    # Get figure and axes dimensions
    fig = ax.get_figure()
    fig.canvas.draw()
    ax_bbox = ax.get_position()

    # Load the QR code background image
    qr_img = Image.open(files('viswall_prom').joinpath('grafana_qr.png'))
    
    # Load the SCC icon (foreground)
    scc_img = Image.open(files('viswall_prom').joinpath('scc_icon.png')).convert('RGB')

    # Calculate QR code dimensions and position in figure coordinates
    qr_ratio = 0.22
    qr_aspect = qr_img.width / qr_img.height

    # Resize the QR code image
    qr_display_height = int(fig.bbox.height * qr_ratio)
    qr_display_width = int(qr_display_height * qr_aspect)
    qr_resized = qr_img.resize((qr_display_width, qr_display_height), Image.Resampling.NEAREST)

    # Position QR code in figure coordinates (center of axes + vertical offset)
    yoff = 0.0
    x_center = (ax_bbox.x0 + ax_bbox.width / 2) * fig.bbox.width
    y_center = (ax_bbox.y0 + ax_bbox.height / 2 + yoff) * fig.bbox.height

    # Display QR code
    fig.figimage(
        np.asarray(qr_resized),
        xo=x_center - qr_resized.width / 2,
        yo=y_center - qr_resized.height / 2,
        origin='upper',
        cmap='gray',
    )

    # Calculate SCC icon dimensions (smaller than QR code)
    scc_ratio = 0.03
    scc_aspect = scc_img.width / scc_img.height

    # Resize the SCC icon
    scc_display_height = int(fig.bbox.height * scc_ratio)
    scc_display_width = int(scc_display_height * scc_aspect)
    scc_resized = scc_img.resize((scc_display_width, scc_display_height), Image.Resampling.LANCZOS)

    # Create a white background for the SCC logo
    bg_padding = 10  # pixels of padding around the logo
    bg_width = scc_resized.width + 2 * bg_padding
    bg_height = scc_resized.height + 2 * bg_padding
    white_bg = Image.new('RGB', (bg_width, bg_height), (255, 255, 255))
    white_bg.paste(scc_resized, (bg_padding, bg_padding))
    scc_with_bg = white_bg

    # Display SCC icon centered over QR code
    fig.figimage(
        np.asarray(scc_with_bg),
        xo=x_center - scc_with_bg.width / 2,
        yo=y_center - scc_with_bg.height / 2,
        origin='upper',
    )

    # text above the images
    text_yoff = 0.11
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

    # timestamp below the images
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
    registry: dict, keys: set[str], fixed=None, fallback_cmap=CYCLE_OTHERS
):
    """Initialize global color mapping for all keys across all subplots"""

    if fixed:
        registry.update(fixed)

    # Then, assign fallback colors to remaining keys (sorted alphabetically)
    if type(fallback_cmap) is str:
        fallback_cmap = mpl.colormaps[fallback_cmap]
    remaining_keys = sorted([k for k in keys if k not in registry])

    for idx, key in enumerate(remaining_keys):
        registry[key] = fallback_cmap(idx % len(fallback_cmap.colors))


def select_last(data):
    return {k: data[k][-1] for k in data}


def sort_and_group(data: dict, threshold: float) -> dict:
    """Group together any centers whose cumulative fractional CPU usage is less than
    `threshold` at all times. Sort the rest in decreasing order on the most recent value.
    """
    # The algorithm: sum up the total usage for each center across all times.
    # Flag any center below the cumulative threshold as eligible for grouping.
    # At the end, group those centers into an "Others" category.

    data = {
        k: v for (k, v) in sorted(data.items(), key=lambda kv: kv[1][-1], reverse=True)
    }

    total_by_center = {k: sum(v) for k, v in data.items()}
    total_by_center = {
        k: v for (k, v) in sorted(total_by_center.items(), key=lambda kv: kv[1])
    }
    total = sum(total_by_center.values())

    small_centers = set()
    others_sum = 0
    for center, usage in total_by_center.items():
        if (others_sum + usage) / total > threshold:
            break
        others_sum += usage
        small_centers.add(center)

    if not small_centers:
        return data

    new_data = {k: v for (k, v) in data.items() if k not in small_centers}
    new_data['Others'] = np.sum([data[k] for k in small_centers], axis=0)

    return new_data


if __name__ == '__main__':
    plot_usage()
