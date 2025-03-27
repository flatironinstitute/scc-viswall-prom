# TODO: actually need a global key -> color mapping
# TODO: figure out what to do about oversubscribed colors
# FUTURE: should we plot CPUs or nodes?

from datetime import datetime
from pathlib import Path

import click
import matplotlib.pyplot as plt
from matplotlib import dates as mdates
from matplotlib.ticker import FuncFormatter

import prom

CENTER_COLORS = {
    'cca': '#CE3232',
    'ccb': '#81AD4A',
    'ccm': '#F6862D',
    'ccn': '#007F9D',
    'ccq': '#845B8E',
    'scc': '#8F8F8F',
}

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

    fig, axes = plt.subplots(
        2, 2, figsize=(1920 // dpi, 1080 // dpi), dpi=dpi, sharex=True, sharey='row'
    )

    _plot_stacked(axes, (0, 0), rusty_acct  , rusty_max , 'Rusty Usage by Center')
    _plot_stacked(axes, (0, 1), rusty_nodes , rusty_max , 'Rusty Usage by Node Type')
    _plot_stacked(axes, (1, 0), popeye_acct , popeye_max, 'Popeye Usage by Center')
    _plot_stacked(axes, (1, 1), popeye_nodes, popeye_max, 'Popeye Usage by Node Type')
    # fmt: on

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
        colors=get_colors(keys, centers=pos[1] == 0),
    )
    ax.plot(x_vals, max_data, label='Capacity', color='black', linestyle='-')
    ax.legend(loc='upper left', ncol=2, framealpha=0.9)
    ax.set_xlim(left=min(x_vals), right=max(x_vals))
    ax.set_ylim(top=max(max_data) * 1.1)

    # format x-axis labels as dates
    ax.xaxis.set_major_formatter(date_formatter)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))

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
            left=False,
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
        FuncFormatter(lambda x, pos: f'{x / 1_000:.0f} K' if x >= 1_000 else f'{x:.0f}')
    )


def get_colors(keys: list[str], centers: bool = False) -> list[str]:
    """
    Get colors for the given keys.
    If a key is not in CENTER_COLORS, cycle through the default colors
    in alphabetical key order (to preserve consistency across runs).
    """
    # Get default colors from matplotlib
    default_colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

    colors = {}
    default_idx = 0

    for key in keys:
        if centers and key.lower() in CENTER_COLORS:
            colors[key] = CENTER_COLORS[key.lower()]
        else:
            colors[key] = default_colors[default_idx % len(default_colors)]
            default_idx += 1

    colors = [colors[key] for key in keys]
    return colors


def date_formatter(ts: float, pos=None) -> str:
    dt: datetime = mdates.num2date(ts)
    month = dt.strftime('%b')
    day = dt.strftime('%d')

    return f'{month}{"." if month != "May" else ""} {day}'


if __name__ == '__main__':
    plot_usage()
