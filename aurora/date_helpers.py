import datetime

import dateutil.parser


def month_number_to_written_month(month):
    return datetime.datetime.strptime(str(month), "%m").strftime("%B")


def list_archive_date(date):
    if isinstance(date, str):
        date = dateutil.parser.parse(date)

    return date


def long_date(date):
    return list_archive_date(date).strftime("%B %d, %Y")


def date_to_xml_string(date):
    return list_archive_date(date).strftime("%Y-%m-%dT%H:%M:%S")


def archive_date(date):
    return list_archive_date(date).strftime("%Y/%m")


def year(date):
    return list_archive_date(date).strftime("%Y")
