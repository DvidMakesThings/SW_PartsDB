from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def health(request):
    """
    Simple health check endpoint
    Returns 200 OK with {"ok": true} always
    """
    return Response({"ok": True})