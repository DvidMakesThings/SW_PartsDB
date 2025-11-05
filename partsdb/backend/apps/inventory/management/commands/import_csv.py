from django.core.management.base import BaseCommand
from apps.inventory.importers import CSVImporter


class Command(BaseCommand):
    help = 'Import components from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the CSV file')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the import without making changes to the database'
        )
        parser.add_argument(
            '--encoding',
            type=str,
            default='utf-8',
            help='File encoding (default: utf-8)'
        )
        parser.add_argument(
            '--delimiter',
            type=str,
            default=',',
            help='CSV delimiter character (default: ,)'
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        dry_run = options['dry_run']
        encoding = options['encoding']
        delimiter = options['delimiter']
        
        self.stdout.write(self.style.SUCCESS(f'Importing from {file_path}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        
        importer = CSVImporter(file_path, dry_run=dry_run, encoding=encoding, delimiter=delimiter)
        results = importer.import_data()
        
        self.stdout.write(self.style.SUCCESS('Import completed with the following results:'))
        self.stdout.write(f'  Created: {results["created"]}')
        self.stdout.write(f'  Updated: {results["updated"]}')
        self.stdout.write(f'  Skipped: {results["skipped"]}')
        self.stdout.write(f'  Errors: {results["errors"]}')
        
        if results['errors'] > 0 and not dry_run:
            error_file = importer.save_errors()
            if error_file:
                self.stdout.write(
                    self.style.WARNING(f'Error details saved to: {error_file}')
                )