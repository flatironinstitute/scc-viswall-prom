import warnings
from datetime import datetime, timedelta

import requests
import urllib3

PROMETHEUS_URL = {
    "popeye": "http://popeye-prometheus.flatironinstitute.org:80",
    "rusty": "http://prometheus.flatironinstitute.org:80",
}


def get_max_cpus(cluster: str, days: int, step: str = "1h") -> list:
    """
    Queries Prometheus API for the total number of CPUs available in a cluster.
    The result is a list because the value may change as nodes go on- and off-line.

    Args:
        cluster: The name of the cluster to query

    Returns:
        The maximum number of CPUs available in the cluster.
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    query = _max_cpus_query()
    url = PROMETHEUS_URL[cluster.lower()]
    result = _query_range(query, url, start_time, end_time, step)

    if result:
        if result["data"]["result"]:
            series = result["data"]["result"][0]
            if "values" in series:
                # Extract just the values (second item in each time-value pair)
                values = [int(point[1]) for point in series["values"]]
                return values
    return []


def get_usage_by_account(cluster: str, days: int, step: str = "1h") -> dict:
    """
    Queries Prometheus API for CPU usage by account over a specified number of days.

    Args:
        cluster: The name of the cluster to query
        days: The number of days to look back from today

    Returns:
        A dictionary with account names as keys and lists of usage values as values.
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    # Query for CPU usage by account over the last 'days' days
    query = _usage_query()
    url = PROMETHEUS_URL[cluster.lower()]
    result = _query_range(query, url, start_time, end_time, step)

    if result:
        return _group_by(result, "account")
    else:
        return {}


def _usage_query():
    """
    Generates a PromQL query for CPU usage by account.
    """
    return 'sum by(account) (slurm_job_cpus{state="running",job="slurm"})'


def _max_cpus_query():
    """
    Generates a PromQL query for total CPUs available in the cluster.
    """
    return 'sum (slurm_node_cpus{state!="drain",state!="down"})'


def _query_range(
    query: str, url: str, start_time: datetime, end_time: datetime, step: str
) -> dict:
    """
    Queries Prometheus API for a range of time and returns the result.

    Args:
        query: The PromQL query string
        start_time: Start time as a datetime object
        end_time: End time as a datetime object
        step: Step between data points (e.g., "1h" for hourly data)
    """
    url = f"{url}/api/v1/query_range"

    params = {
        "query": query,
        "start": start_time.timestamp(),
        "end": end_time.timestamp(),
        "step": step,
    }

    try:
        # Temporarily disable SSL warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, params=params, verify=False)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error querying Prometheus: {e}")
        return None

    try:
        result = response.json()
        if result["status"] != "success":
            raise ValueError("Query failed")
    except (ValueError, KeyError) as e:
        print(f"Error parsing response: {e}")
        return None

    return result


def _group_by(result: dict, metric: str) -> dict:
    """
    Formats Prometheus range query results as a dictionary of lists.
    Each key is an account name, and each value is a list of values.
    """
    if not result or "data" not in result or "result" not in result["data"]:
        return {}

    data_dict = {}

    for series in result["data"]["result"]:
        if "metric" in series and metric in series["metric"]:
            account = series["metric"][metric]
            # Extract just the values (second item in each time-value pair)
            values = [int(point[1]) for point in series.get("values", [])]
            data_dict[account] = values

    return data_dict


if __name__ == "__main__":
    print(get_usage_by_account("rusty", 7, "1d"))
    print(get_max_cpus("rusty", 7, "1d"))

    print(get_usage_by_account("popeye", 7, "1d"))
    print(get_max_cpus("popeye", 7, "1d"))
