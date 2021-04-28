"""
Base classes for import_* commands
"""

from io import open
import csv
from django.core.management.base import BaseCommand


class ImportFromCSVCommand(BaseCommand):
    """
    Base class for commands for importing data from CSV files (via stdin)
    """

    input = 0
    encoding = 'cp1252'

    def handle_row(self, row):
        """
        Given a row (a dictionary),
        probably creates an object and saves it in the database
        """
        raise NotImplementedError

    @staticmethod
    def process_rows(rows):
        return rows

    def handle_rows(self, rows):
        for row in self.process_rows(rows):
            self.handle_row(row)

    def handle(self, *args, **options):
        """
        Runs when the command is executed
        """
        with open(self.input, encoding=self.encoding) as input:
            rows = csv.DictReader(input)
            self.handle_rows(rows)
