import datetime


def month_number_to_written_month(month):
    return datetime.datetime.strptime(str(month), "%m").strftime("%B")


def list_archive_date(date):
    if type(date) is str and "." in date:
        date = date.replace(" ", "T")
        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f")
    elif type(date) is str:
        date = date.replace(" ", "T")
        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S-00:00")

    return date


def long_date(date):
    return list_archive_date(date).strftime("%B %d, %Y")


def date_to_xml_string(date):
    return list_archive_date(date).strftime("%Y-%m-%dT%H:%M:%S")


def archive_date(date):
    return list_archive_date(date).strftime("%Y/%m")
