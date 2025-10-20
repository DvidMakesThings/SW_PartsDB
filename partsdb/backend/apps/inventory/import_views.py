from django.core.files.uploadedfile import InMemoryUploadedFile
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

import tempfile
import os

from .importers import CSVImporter


class ImportCSVView(APIView):
    """
    API view for importing CSV files
    """
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        dry_run = request.data.get('dry_run', 'false').lower() in ('true', '1', 'yes')
        encoding = request.data.get('encoding', 'utf-8')
        delimiter = request.data.get('delimiter', ',')
        
        if not file_obj:
            return JsonResponse(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_file:
            for chunk in file_obj.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        
        try:
            # Import data from the CSV
            importer = CSVImporter(temp_file_path, dry_run=dry_run, encoding=encoding, delimiter=delimiter)
            results = importer.import_data()
            
            # Include error rows in the response if there are any
            response_data = {
                'created': results['created'],
                'updated': results['updated'],
                'skipped': results['skipped'],
                'errors': results['errors'],
            }
            
            if results['error_rows']:
                response_data['error_rows'] = [
                    {"row": row['row'], "error": row['error']} 
                    for row in results['error_rows']
                ]
            
            return JsonResponse(response_data)
        
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)