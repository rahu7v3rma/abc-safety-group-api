import datetime


def check_overlap(schedule1, schedule2) -> bool:
    """Function to compare if two schedule times overlap

    Args:
        schedule1 (str): Time 1 to be compared to Time 2
        schedule2 (str): Time 1 to be compared to Time 2

    Returns:
        bool: True or false if overlapping in dates occurs
    """

    start_time = datetime.datetime.strptime(
        schedule1["startTime"],
        "%m/%d/%Y  %I:%M %p",
    )
    end_time = datetime.datetime.strptime(
        schedule1["endTime"],
        "%m/%d/%Y %I:%M %p",
    )
    start_time_2 = datetime.datetime.strptime(
        schedule2["startTime"],
        "%m/%d/%Y %I:%M %p",
    )
    end_time_2 = datetime.datetime.strptime(
        schedule2["endTime"],
        "%m/%d/%Y %I:%M %p",
    )
    return start_time < end_time_2 and end_time > start_time_2
