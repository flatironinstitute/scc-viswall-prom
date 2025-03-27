"""
Query Flatiron Prometheus for cluster usage data.

Run this module directly to do a test query.
"""

import warnings
from datetime import datetime, timedelta
from typing import Literal

import requests
import urllib3

PROMETHEUS_URL = {
    'popeye': 'http://popeye-prometheus.flatironinstitute.org:80',
    'rusty': 'http://prometheus.flatironinstitute.org:80',
}

Cluster = Literal['popeye', 'rusty']
Grouping = Literal['account', 'nodes', None]
Resource = Literal['cpus', 'bytes', 'gpus']


def get_max_resource(
    cluster: Cluster,
    days: int,
    step: str = '1h',
    resource: Resource = 'cpus',
) -> dict[list]:
    """
    Queries Prometheus API for the resource capacity in a cluster.
    The result is a dict of list because the value may change as nodes go on- and off-line.

    Args:
        cluster: The name of the cluster to query

    Returns:
        The maximum number of CPUs available in the cluster, keyed by node type.
        The result will also have a 'total' key.
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    query = _capacity_query(resource, by_nodes=True)
    url = PROMETHEUS_URL[cluster.lower()]
    result = _query_range(query, url, start_time, end_time, step)

    if result:
        result = _group_by(result, 'nodes')
        result['total'] = [
            sum(v) for v in zip(*(result[k] for k in result if k != 'timestamps'))
        ]
        return result
    else:
        return {}


def get_usage_by(
    grouping: Grouping,
    cluster: Cluster,
    days: int,
    step: str = '1h',
    resource: Resource = 'cpus',
) -> dict:
    """
    Queries Prometheus API for CPU usage by the given grouping over a specified number of days.

    Args:
        cluster: The name of the cluster to query
        days: The number of days to look back from today

    Returns:
        A dictionary with grouping names as keys and lists of usage values as values.
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    query = _usage_query(grouping, resource)
    url = PROMETHEUS_URL[cluster.lower()]
    result = _query_range(query, url, start_time, end_time, step)

    if result:
        return _group_by(result, grouping)
    else:
        return {}


def _usage_query(grouping: Grouping, resource: Resource) -> str:
    """
    Generates a PromQL query for usage by the given grouping.
    """
    return f'sum by({grouping}) (slurm_job_{resource}{{state="running",job="slurm"}})'


def _capacity_query(resource: Resource, by_nodes: bool = False) -> str:
    """
    Generates a PromQL query for total available in the cluster.
    """
    return f'sum {"by(nodes)" if by_nodes else ""} (slurm_node_{resource}{{state!="drain",state!="down"}})'


def _query_range(
    query: str, url: str, start_time: datetime, end_time: datetime, step: str
) -> dict | None:
    """
    Queries Prometheus API for a range of time and returns the result.

    Args:
        query: The PromQL query string
        start_time: Start time as a datetime object
        end_time: End time as a datetime object
        step: Step between data points (e.g., "1h" for hourly data)
    """
    url = f'{url}/api/v1/query_range'

    params = {
        'query': query,
        'start': start_time.timestamp(),
        'end': end_time.timestamp(),
        'step': step,
    }

    try:
        # Temporarily disable SSL warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, params=params, verify=False)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f'Error querying Prometheus: {e}')
        return None

    try:
        result = response.json()
        if result['status'] != 'success':
            raise ValueError('Query failed')
    except (ValueError, KeyError) as e:
        print(f'Error parsing response: {e}')
        return None

    return result


def _group_by(result: dict, metric: str, missing=0) -> dict:
    """
    Formats Prometheus range query results as a dictionary of lists.
    Each key is a grouping value, and each value is a list of values.
    Ensures all time series are of the same length, filling missing values.
    """

    if not result or 'data' not in result or 'result' not in result['data']:
        return {}

    data_dict = {}
    timestamps = set()

    # First pass: collect all timestamps and create initial group entries
    for series in result['data']['result']:
        if 'metric' in series and metric in series['metric']:
            group = series['metric'][metric]
            data_dict[group] = {}

            # Add all timestamps to our set and associate values with timestamps
            for point in series.get('values', []):
                timestamp = point[0]  # timestamp is the first item
                value = int(point[1])  # value is the second item
                timestamps.add(timestamp)
                data_dict[group][timestamp] = value

    # Convert to sorted list of timestamps for consistent ordering
    sorted_timestamps = sorted(timestamps)

    # Second pass: ensure all groups have values for all timestamps
    for group in data_dict:
        values = []
        for timestamp in sorted_timestamps:
            values.append(data_dict[group].get(timestamp, missing))

        # Replace the timestamp dict with the final list
        data_dict[group] = values

    data_dict['timestamps'] = [datetime.fromtimestamp(ts) for ts in sorted_timestamps]

    return data_dict


if __name__ == '__main__':
    print('rusty cpu')
    print(get_usage_by('account', 'rusty', 7, '1d'))
    print(get_usage_by('nodes', 'rusty', 7, '1d'))
    print(get_max_resource('rusty', 7, '1d'))
    print()

    print('rusty gpus')
    print(get_usage_by('nodes', 'rusty', 7, '1d', 'gpus'))
    print(get_max_resource('rusty', 7, '1d', 'gpus'))
    print()

    print('popeye cpu')
    print(get_usage_by('account', 'popeye', 7, '1d'))
    print(get_usage_by('nodes', 'popeye', 7, '1d'))
    print(get_max_resource('popeye', 7, '1d'))
